"""Esquemas de autenticación."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.user import UserRole

# Formato de email sin rechazar dominios special-use (.test, .local) en dev/tests
EmailLike = Annotated[
    str,
    StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320),
]


class LoginStudentRequest(BaseModel):
    course_code: str = Field(min_length=1, max_length=16)
    identifier: str = Field(min_length=1, max_length=100)
    pin: str = Field(min_length=6, max_length=64, pattern=r"^\d{6,}$")


class LoginStaffRequest(BaseModel):
    email: EmailLike
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    """Login/refresh: el refresh token vive solo en la cookie httponly."""

    access_token: str
    token_type: str = Field(default="bearer")
    must_change_credentials: bool


class StaffLoginResponse(TokenResponse):
    """Login staff; para super_admin devuelve el reto 2FA en vez de tokens.

    En el reto `access_token` queda vacío (nunca hay sesión sin el segundo
    factor) y `mfa_token` es un JWT corto de propósito único.
    """

    access_token: str = ""
    mfa_required: bool = False
    mfa_token: str | None = None
    mfa_enrolled: bool = False


class MfaSetupRequest(BaseModel):
    """Genera el secreto TOTP pendiente (flujo de login o con sesión propia)."""

    mfa_token: str | None = Field(default=None, max_length=2048)


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    mfa_enabled: bool = False


class MfaVerifyRequest(BaseModel):
    """Confirma el primer código (activa) o valida el habitual.

    Con `mfa_token` emite los tokens de sesión; con sesión propia solo
    confirma/desactiva el factor.
    """

    mfa_token: str | None = Field(default=None, max_length=2048)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MfaVerifyResponse(BaseModel):
    """Tokens solo cuando venían de un `mfa_token` de login."""

    mfa_enabled: bool
    access_token: str | None = None
    token_type: str = Field(default="bearer")
    must_change_credentials: bool | None = None


class MfaDisableRequest(BaseModel):
    """Desactivar el 2FA exige un código vigente (no basta la sesión)."""

    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ChangeCredentialsRequest(BaseModel):
    """Cambio obligatorio en primer acceso (PIN de estudiante o contraseña staff)."""

    current_secret: str = Field(min_length=6, max_length=128)
    new_secret: str = Field(min_length=6, max_length=128)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None
    username: str | None
    role: UserRole
    is_active: bool
    must_change_credentials: bool
    mfa_enabled: bool = False
    created_at: datetime


class ProfileUpdateRequest(BaseModel):
    """Actualización de perfil propio (nombre y/o email)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
