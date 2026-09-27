"""Endpoints de autenticación."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.models import User, UserRole
from app.schemas.auth import (
    ChangeCredentialsRequest,
    LoginStaffRequest,
    LoginStudentRequest,
    LogoutRequest,
    MfaDisableRequest,
    MfaSetupRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    MfaVerifyResponse,
    ProfileUpdateRequest,
    RefreshRequest,
    StaffLoginResponse,
    TokenResponse,
    UserPublic,
)
from app.schemas.public import ActivationInfoResponse, ActivationRequest, ActivationResponse
from app.security.policies import (
    CurrentUser,
    CurrentUserWithPendingChange,
    DbSession,
    OptionalSessionUser,
    current_user_from_token,
    require_super_admin,
)
from app.services import auth_service
from app.services.activation import ActivationError, activate_account, find_user_by_activation_token
from app.services.auth_service import REFRESH_COOKIE_PATH, AuthError

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    secure = settings_secure()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        samesite="strict",
        secure=secure,
        path=REFRESH_COOKIE_PATH,
        max_age=60 * 60 * 24 * 14,
    )


def settings_secure() -> bool:
    from app.core.config import settings

    return settings.environment == "production"


def _handle_auth_error(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _token_response(tokens: dict[str, object], response: Response) -> StaffLoginResponse:
    """El refresh token viaja SOLO en la cookie httponly, nunca en el body.

    En el reto 2FA de super_admin no hay refresh: solo el `mfa_token` de 5 min.
    """
    if bool(tokens.get("mfa_required")):
        return StaffLoginResponse(
            token_type=str(tokens["token_type"]),
            must_change_credentials=bool(tokens["must_change_credentials"]),
            mfa_required=True,
            mfa_token=str(tokens["mfa_token"]),
            mfa_enrolled=bool(tokens["mfa_enrolled"]),
        )
    _set_refresh_cookie(response, str(tokens["refresh_token"]))
    return StaffLoginResponse(
        access_token=str(tokens["access_token"]),
        token_type=str(tokens["token_type"]),
        must_change_credentials=bool(tokens["must_change_credentials"]),
    )


@router.post("/login/student", response_model=TokenResponse)
def login_student(
    body: LoginStudentRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    ip = request.client.host if request.client else None
    try:
        _user, tokens = auth_service.login_student(
            db,
            course_code=body.course_code,
            identifier=body.identifier,
            pin=body.pin,
            ip=ip,
        )
    except AuthError as exc:
        raise _handle_auth_error(exc) from exc
    return _token_response(tokens, response)


@router.post("/login/staff", response_model=StaffLoginResponse)
def login_staff(
    body: LoginStaffRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> StaffLoginResponse:
    """Staff normal → tokens; super_admin → reto 2FA (sin tokens hasta verify)."""
    ip = request.client.host if request.client else None
    try:
        _user, tokens = auth_service.login_staff(
            db, email=str(body.email), password=body.password, ip=ip
        )
    except AuthError as exc:
        raise _handle_auth_error(exc) from exc
    return _token_response(tokens, response)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    body: RefreshRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    token = body.refresh_token or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        _user, tokens = auth_service.refresh_tokens(db, refresh_token=token)
    except AuthError as exc:
        raise _handle_auth_error(exc) from exc
    return _token_response(tokens, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    body: LogoutRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> Response:
    token = body.refresh_token or request.cookies.get(REFRESH_COOKIE)
    user = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            user = current_user_from_token(db, auth_header.removeprefix("Bearer ").strip())
        except HTTPException:
            user = None
    auth_service.logout(db, refresh_token=token, user=user)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserPublic)
def me(user: Annotated[object, Depends(CurrentUser)]) -> UserPublic:
    from app.models import User

    assert isinstance(user, User)
    return UserPublic.model_validate(user)


@router.patch("/me", response_model=UserPublic)
def update_profile(
    body: ProfileUpdateRequest,
    db: DbSession,
    user: Annotated[object, Depends(CurrentUser)],
) -> UserPublic:
    from sqlalchemy import select

    from app.models import User

    assert isinstance(user, User)
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        if body.email != user.email:
            existing = db.scalar(select(User).where(User.email == body.email, User.id != user.id))
            if existing is not None:
                raise HTTPException(status_code=409, detail="Email already exists")
        user.email = body.email
    db.commit()
    db.refresh(user)
    return UserPublic.model_validate(user)


@router.patch("/change-credentials", response_model=UserPublic)
def change_credentials(
    body: ChangeCredentialsRequest,
    request: Request,
    db: DbSession,
    user: Annotated[object, Depends(CurrentUserWithPendingChange)],
) -> UserPublic:
    from app.models import User

    assert isinstance(user, User)
    if user.role is UserRole.student:
        raise HTTPException(
            status_code=403,
            detail="Students cannot change their own PIN; ask your teacher to reset it",
        )
    ip = request.client.host if request.client else None
    try:
        updated = auth_service.change_credentials(
            db,
            user=user,
            current_secret=body.current_secret,
            new_secret=body.new_secret,
            ip=ip,
        )
    except AuthError as exc:
        raise _handle_auth_error(exc) from exc
    return UserPublic.model_validate(updated)


@router.get("/activate", response_model=ActivationInfoResponse)
def activation_info(token: str, db: DbSession) -> ActivationInfoResponse:
    """Valida el token de activación (email de alta) para mostrar la pantalla."""
    user = find_user_by_activation_token(db, token)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired activation token")
    return ActivationInfoResponse(
        email=user.email or "",
        expires_at=user.activation_token_expires_at,
    )


@router.post("/activate", response_model=ActivationResponse)
def activation(body: ActivationRequest, db: DbSession) -> ActivationResponse:
    """Crea la contraseña de la cuenta de organización (token de un solo uso)."""
    try:
        user = activate_account(db, token=body.token, password=body.password)
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    return ActivationResponse(status="activated", email=user.email or "")


# --- 2FA TOTP (Fase D, exclusivo de super_admin) ---


def _resolve_mfa_user(
    db: DbSession,
    mfa_token: str | None,
    session_user: User | None,
) -> User:
    """Quién está detrás de una llamada MFA: el reto de login o la sesión."""
    if mfa_token:
        try:
            return auth_service.user_from_mfa_token(db, mfa_token)
        except AuthError as exc:
            raise _handle_auth_error(exc) from exc
    if session_user is not None:
        if session_user.role is not UserRole.super_admin:
            raise HTTPException(status_code=403, detail="Super admin access required")
        return session_user
    raise HTTPException(status_code=401, detail="Not authenticated")


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(
    body: MfaSetupRequest,
    db: DbSession,
    session_user: Annotated[User | None, Depends(OptionalSessionUser)],
) -> MfaSetupResponse:
    """Genera el secreto TOTP pendiente (flujo de login o sesión propia)."""
    user = _resolve_mfa_user(db, body.mfa_token, session_user)
    try:
        secret, url = auth_service.mfa_begin_setup(db, user)
    except AuthError as exc:
        raise _handle_auth_error(exc) from exc
    return MfaSetupResponse(secret=secret, otpauth_url=url, mfa_enabled=user.mfa_enabled)


@router.post("/mfa/verify", response_model=MfaVerifyResponse)
def mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: DbSession,
    session_user: Annotated[User | None, Depends(OptionalSessionUser)],
) -> MfaVerifyResponse:
    """Confirma el primer código (activa) o valida el habitual.

    Viniendo de un `mfa_token` de login emite los tokens reales de sesión.
    """
    from_login = body.mfa_token is not None
    user = _resolve_mfa_user(db, body.mfa_token, session_user)
    ip = request.client.host if request.client else None
    try:
        tokens = auth_service.mfa_verify(
            db, user=user, code=body.code, ip=ip, issue_tokens_flag=from_login
        )
    except AuthError as exc:
        raise _handle_auth_error(exc) from exc
    if tokens is not None:
        _set_refresh_cookie(response, str(tokens["refresh_token"]))
        return MfaVerifyResponse(
            mfa_enabled=True,
            access_token=str(tokens["access_token"]),
            token_type=str(tokens["token_type"]),
            must_change_credentials=bool(tokens["must_change_credentials"]),
        )
    return MfaVerifyResponse(mfa_enabled=user.mfa_enabled)


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(
    body: MfaDisableRequest,
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(require_super_admin)],
) -> Response:
    """Desactiva el 2FA con un código vigente (exige sesión propia)."""
    ip = request.client.host if request.client else None
    try:
        auth_service.mfa_disable(db, user=user, code=body.code, ip=ip)
    except AuthError as exc:
        raise _handle_auth_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
