"""Fase D: categorías, cohorts, roles personalizados (escala)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User

try:  # JSONB en PostgreSQL, JSON en SQLite (tests locales)
    from sqlalchemy.dialects.postgresql import JSONB

    JsonType = JSON().with_variant(JSONB(), "postgresql")
except ImportError:  # pragma: no cover
    JsonType = JSON()


class CourseCategory(Base):
    __tablename__ = "course_categories"
    # Fase C: slug único POR organización (aislamiento multi-tenant)
    __table_args__ = (
        UniqueConstraint("slug", "organization_id", name="uq_course_categories_slug_org"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        default=1,
        server_default="1",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    courses: Mapped[list["Course"]] = relationship(
        back_populates="category",
        lazy="selectin",
        passive_deletes=True,
    )


class Cohort(Base):
    __tablename__ = "cohorts"
    # Fase C: code único POR organización
    __table_args__ = (UniqueConstraint("code", "organization_id", name="uq_cohorts_code_org"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        default=1,
        server_default="1",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    category: Mapped[CourseCategory | None] = relationship(lazy="joined")
    memberships: Mapped[list["CohortMembership"]] = relationship(
        back_populates="cohort",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CohortMembership(Base):
    __tablename__ = "cohort_members"
    __table_args__ = (UniqueConstraint("cohort_id", "student_id", name="uq_cohort_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_id: Mapped[int] = mapped_column(
        ForeignKey("cohorts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    cohort: Mapped[Cohort] = relationship(back_populates="memberships")
    student: Mapped["User"] = relationship(lazy="joined")


class CustomRole(Base):
    __tablename__ = "custom_roles"
    # Fase C: nombre único POR organización
    __table_args__ = (UniqueConstraint("name", "organization_id", name="uq_custom_roles_name_org"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # Lista de permisos conocidos, p. ej. ["reports.view", "settings.manage"]
    permissions: Mapped[list[str]] = mapped_column(
        JsonType, nullable=False, default=list, server_default="[]"
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
        default=1,
        server_default="1",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="custom_role",
        lazy="selectin",
        passive_deletes=True,
    )
