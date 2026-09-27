"""Dependencias de autenticación y políticas de permisos reutilizables.

Toda comprobación de acceso (matriz de permisos) vive aquí; los endpoints
solo declaran la dependencia correspondiente.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request, status
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import (
    Course,
    CourseTeacher,
    Enrollment,
    EnrollmentStatus,
    Submission,
    User,
    UserRole,
)

DbSession = Annotated[Session, Depends(get_db)]

__all__ = [
    "CurrentCourse",
    "CurrentUser",
    "DbSession",
    "OptionalSessionUser",
    "current_user_from_token",
    "ensure_same_org",
    "get_bearer_token",
    "get_course_or_404",
    "require_admin",
    "require_enrolled",
    "require_permission",
    "require_staff_of_course",
    "require_super_admin",
    "require_teacher_of_course",
    "user_permissions",
]


def get_bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth.removeprefix("Bearer ").strip()


def current_user_from_token(
    db: Session,
    token: str,
    *,
    require_change_ok: bool = True,
) -> User:
    try:
        payload = decode_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    sub = payload.get("sub")
    if not sub or not str(sub).isdigit():
        raise HTTPException(status_code=401, detail="Invalid token subject")
    user = db.get(User, int(sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive or not found")
    if require_change_ok and user.must_change_credentials:
        raise HTTPException(status_code=403, detail="Must change credentials first")
    return user


def CurrentUser(
    db: DbSession,
    token: Annotated[str, Depends(get_bearer_token)],
) -> User:
    return current_user_from_token(db, token)


def CurrentUserWithPendingChange(
    db: DbSession,
    token: Annotated[str, Depends(get_bearer_token)],
) -> User:
    """Como CurrentUser pero permite `must_change_credentials` (para el endpoint)."""
    return current_user_from_token(db, token, require_change_ok=False)


def OptionalSessionUser(request: Request, db: DbSession) -> User | None:
    """Usuario si hay Bearer válido; None si no hay cabecera o no decodifica.

    Para endpoints que aceptan **o** token de sesión **o** un token de flujo
    (p. ej. el `mfa_token` del 2FA); quien resuelve decide qué vía usar.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return current_user_from_token(
            db, auth.removeprefix("Bearer ").strip(), require_change_ok=False
        )
    except HTTPException:
        return None


def require_admin(user: Annotated[User, Depends(CurrentUser)]) -> User:
    if user.role is not UserRole.org_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_super_admin(user: Annotated[User, Depends(CurrentUser)]) -> User:
    """Solo la cuenta dueña de la plataforma (rutas /superadmin/*)."""
    if user.role is not UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user


def ensure_same_org(user: User, resource_org_id: int | None, detail: str = "Not found") -> None:
    """404 si el recurso pertenece a otra organización (nunca 403: no filtrar existencia ajena)."""
    if user.organization_id is None:
        return  # super_admin no llega por aquí; lo bloquean los deps de rol
    if resource_org_id != user.organization_id:
        raise HTTPException(status_code=404, detail=detail)


def _ensure_course_org(user: User, course: Course) -> None:
    """Aislamiento multi-tenant: curso de otra organización → 404."""
    ensure_same_org(user, course.organization_id, detail="Course not found")


def user_permissions(user: User) -> list[str]:
    """Permisos efectivos: org_admin → todos; resto → su rol personalizado.

    super_admin queda fuera a propósito: no toca datos académicos (Fase C tendrá
    sus propias rutas /superadmin/*).
    """
    from app.schemas.scale import KNOWN_PERMISSIONS

    if user.role is UserRole.org_admin:
        return list(KNOWN_PERMISSIONS)
    if user.custom_role is not None:
        perms = user.custom_role.permissions or []
        return [p for p in perms if p in KNOWN_PERMISSIONS]
    return []


def require_permission(perm: str) -> Callable[[Annotated[User, Depends(CurrentUser)]], User]:
    """Dependency factory: admin o usuario con rol personalizado que incluya `perm`."""

    def dependency(user: Annotated[User, Depends(CurrentUser)]) -> User:
        if perm in user_permissions(user):
            return user
        raise HTTPException(status_code=403, detail="Permission required")

    return dependency


def get_course_or_404(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    course_id: Annotated[int, Path(..., ge=1)],
) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        # 404 en vez de 403 para no filtrar existencia ajenas (invariante 3/4)
        raise HTTPException(status_code=404, detail="Course not found")
    # Aislamiento multi-tenant: curso de otra organización → 404 (Fase C)
    _ensure_course_org(user, course)
    return course


CurrentCourse = Annotated[Course, Depends(get_course_or_404)]


def require_staff_of_course(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    course: CurrentCourse,
) -> tuple[User, Course]:
    """Org_admin siempre (de SU organización); teacher solo si es de `course_teachers`."""
    _ensure_course_org(user, course)
    if user.role is UserRole.org_admin:
        return user, course
    if user.role is UserRole.teacher:
        link = db.scalar(
            select(CourseTeacher).where(
                CourseTeacher.course_id == course.id,
                CourseTeacher.teacher_id == user.id,
            )
        )
        if link is None:
            raise HTTPException(status_code=404, detail="Course not found")
        return user, course
    raise HTTPException(status_code=403, detail="Staff access required")


def require_teacher_of_course(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    course: CurrentCourse,
) -> tuple[User, Course]:
    """Solo teachers asignados (o org_admin); estudiantes nunca evalúan."""
    if user.role is UserRole.student:
        raise HTTPException(status_code=403, detail="Teacher access required")
    return require_staff_of_course(db, user, course)


def require_enrolled(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    course: CurrentCourse,
) -> tuple[User, Course, Enrollment | None]:
    """Student: matrícula activa. Teacher/org_admin del curso: enrollment None."""
    _ensure_course_org(user, course)
    if user.role in (UserRole.org_admin, UserRole.teacher):
        u, c = require_staff_of_course(db, user, course)
        return u, c, None
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course.id,
            Enrollment.student_id == user.id,
            Enrollment.status == EnrollmentStatus.active,
        )
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return user, course, enrollment


def can_read_submission(db: Session, user: User, submission: Submission) -> bool:
    """Matriz: dueño, staff del curso, o peer con visibility=class (sin evals)."""
    if user.role is UserRole.org_admin:
        # Solo entregas de cursos de SU organización (Fase C); los callers
        # convierten False en 404, así que nunca se filtra existencia ajena.
        course = db.get(Course, submission.course_id)
        if course is None or user.organization_id is None:
            return False
        return course.organization_id == user.organization_id
    if submission.student_id == user.id:
        return True
    if user.role is UserRole.teacher:
        link = db.scalar(
            select(CourseTeacher).where(
                CourseTeacher.course_id == submission.course_id,
                CourseTeacher.teacher_id == user.id,
            )
        )
        return link is not None
    if user.role is UserRole.student:
        enrolled = db.scalar(
            select(Enrollment).where(
                Enrollment.course_id == submission.course_id,
                Enrollment.student_id == user.id,
                Enrollment.status == EnrollmentStatus.active,
            )
        )
        if enrolled is None:
            return False
        if submission.assignment is None:
            return False
        return submission.assignment.visibility.value == "class"
    # super_admin: sin lectura de datos académicos (compromiso de producto)
    return False


def can_write_submission(user: User, submission: Submission) -> bool:
    return user.role is UserRole.student and submission.student_id == user.id
