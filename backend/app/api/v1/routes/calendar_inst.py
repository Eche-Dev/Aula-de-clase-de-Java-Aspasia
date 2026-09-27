"""Calendario institucional: eventos de todos los cursos visibles."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Announcement,
    Assignment,
    Course,
    CourseTeacher,
    Enrollment,
    EnrollmentStatus,
    User,
    UserRole,
)
from app.schemas.phase_c import InstitutionalCalendarItem
from app.security.policies import CurrentUser, DbSession

router = APIRouter(tags=["calendar"])


def _visible_course_ids(db: Session, user: User) -> list[int]:
    if user.role is UserRole.org_admin:
        # Fase C: solo cursos de su organización
        return list(
            db.scalars(
                select(Course.id).where(Course.organization_id == user.organization_id)
            ).all()
        )
    if user.role is UserRole.teacher:
        return list(
            db.scalars(
                select(CourseTeacher.course_id).where(CourseTeacher.teacher_id == user.id)
            ).all()
        )
    return list(
        db.scalars(
            select(Enrollment.course_id).where(
                Enrollment.student_id == user.id,
                Enrollment.status == EnrollmentStatus.active,
            )
        ).all()
    )


@router.get("/calendar/institutional", response_model=list[InstitutionalCalendarItem])
def institutional_calendar(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[InstitutionalCalendarItem]:
    course_ids = _visible_course_ids(db, user)
    if not course_ids:
        return []
    courses = {c.id: c for c in db.scalars(select(Course).where(Course.id.in_(course_ids))).all()}
    items: list[InstitutionalCalendarItem] = []

    for a in db.scalars(
        select(Assignment)
        .where(Assignment.course_id.in_(course_ids), Assignment.due_at.is_not(None))
        .order_by(Assignment.due_at)
    ).all():
        course = courses.get(a.course_id)
        if course is None:
            continue
        items.append(
            InstitutionalCalendarItem(
                kind="assignment",
                id=a.id,
                title=a.title,
                course_id=course.id,
                course_name=course.name,
                course_code=course.code,
                ends_at=a.due_at,
            )
        )

    for ann in db.scalars(
        select(Announcement)
        .where(Announcement.course_id.in_(course_ids))
        .order_by(Announcement.created_at.desc())
        .limit(100)
    ).all():
        course = courses.get(ann.course_id)
        if course is None:
            continue
        items.append(
            InstitutionalCalendarItem(
                kind="announcement",
                id=ann.id,
                title=ann.title,
                course_id=course.id,
                course_name=course.name,
                course_code=course.code,
                starts_at=ann.created_at,
            )
        )

    def sort_key(item: InstitutionalCalendarItem) -> str:
        when = item.ends_at or item.starts_at
        return when.isoformat() if when else "9999-12-31"

    items.sort(key=sort_key)
    return items
