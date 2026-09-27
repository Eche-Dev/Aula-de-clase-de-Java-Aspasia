"""Modelos de identidad: usuarios y refresh tokens."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Enrollment
    from app.models.organization import Organization
    from app.models.scale import CustomRole


class UserRole(StrEnum):
    super_admin = "super_admin"
    org_admin = "org_admin"
    teacher = "teacher"
    student = "student"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Invariante multi-tenant: solo super_admin carece de organización
        CheckConstraint(
            "(role = 'super_admin' AND organization_id IS NULL) "
            "OR (role <> 'super_admin' AND organization_id IS NOT NULL)",
            name="org_by_role",
        ),
        # Dominio cerrado de roles (SQLite no valida el tipo Enum a nivel BD)
        CheckConstraint(
            "role IN ('super_admin', 'org_admin', 'teacher', 'student')",
            name="role_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    role: Mapped[UserRole] = mapped_column(nullable=False, index=True)
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # NULL únicamente para super_admin; obligatorio para los otros tres roles
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )
    # Solo para org_admin recién creado (Fase B: alta con activación por email)
    activation_token_hash: Mapped[str | None] = mapped_column(String(255))
    activation_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    custom_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_roles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 2FA TOTP (Fase D): solo para super_admin. El secreto se guarda en claro
    # porque la verificación TOTP lo necesita; `mfa_enabled` solo es true
    # tras confirmar el primer código.
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    custom_role: Mapped["CustomRole | None"] = relationship(lazy="joined")
    organization: Mapped["Organization | None"] = relationship(lazy="selectin")
    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(lazy="joined")
