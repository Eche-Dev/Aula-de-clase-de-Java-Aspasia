"""Modelos de curso: courses, asientos, matrículas, secciones, profesores."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.scale import Cohort, CourseCategory
    from app.models.user import User

try:  # JSONB en PostgreSQL, JSON en SQLite (tests locales)
    from sqlalchemy.dialects.postgresql import JSONB

    JsonType = JSON().with_variant(JSONB(), "postgresql")
except ImportError:  # pragma: no cover
    JsonType = JSON()


class CourseStatus(StrEnum):
    active = "active"
    archived = "archived"


class SectionKind(StrEnum):
    content = "content"
    external = "external"


class EnrollmentStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class Course(Base):
    __tablename__ = "courses"
    # Fase C: code único POR organización (cada centro puede repetir códigos)
    __table_args__ = (UniqueConstraint("code", "organization_id", name="uq_courses_code_org"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[CourseStatus] = mapped_column(
        nullable=False, default=CourseStatus.active, index=True
    )
    layout_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    layout_cols: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict, server_default="{}"
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cohort_id: Mapped[int | None] = mapped_column(
        ForeignKey("cohorts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    category: Mapped["CourseCategory | None"] = relationship(
        back_populates="courses",
        lazy="joined",
    )
    cohort: Mapped["Cohort | None"] = relationship(lazy="joined")

    seats: Mapped[list["Seat"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Seat.row, Seat.col",
    )
    teachers: Mapped[list["CourseTeacher"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CourseTeacher(Base):
    __tablename__ = "course_teachers"
    __table_args__ = (UniqueConstraint("course_id", "teacher_id", name="uq_course_teachers"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    course: Mapped[Course] = relationship(back_populates="teachers")
    teacher: Mapped["User"] = relationship(lazy="joined")


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("course_id", "row", "col", name="uq_seats_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    col: Mapped[int] = mapped_column(Integer, nullable=False)

    course: Mapped[Course] = relationship(back_populates="seats")
    enrollment: Mapped["Enrollment | None"] = relationship(
        back_populates="seat",
        uselist=False,
        lazy="selectin",
    )


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", name="uq_enrollment_student"),
        UniqueConstraint("course_id", "seat_id", name="uq_enrollment_seat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seat_id: Mapped[int | None] = mapped_column(
        ForeignKey("seats.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        nullable=False, default=EnrollmentStatus.active, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    course: Mapped[Course] = relationship(lazy="joined")
    student: Mapped["User"] = relationship(
        back_populates="enrollments",
        lazy="joined",
    )
    seat: Mapped[Seat | None] = relationship(back_populates="enrollment", lazy="joined")


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("course_id", "slug", name="uq_sections_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    kind: Mapped[SectionKind] = mapped_column(nullable=False, default=SectionKind.content)
    body_markdown: Mapped[str | None] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(String(500))

    course: Mapped[Course] = relationship(lazy="joined")
