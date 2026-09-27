"""Chat global por curso: sala compartida para miembros del curso."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Course,
    CourseMessage,
    CourseMessageRead,
    CourseTeacher,
    Enrollment,
    EnrollmentStatus,
    User,
    UserRole,
)
from app.schemas.course_message import (
    CourseChatPage,
    CourseChatRoomSummary,
    CourseMessageCreate,
    CourseMessagePublic,
)
from app.security.policies import CurrentUser, DbSession, ensure_same_org
from app.services.audit import log_action

router = APIRouter(tags=["course-chat"])


def _assert_course_member(db: Session, user: User, course: Course) -> None:
    """404 si el usuario no es miembro (multi-tenant sin filtrar existencia)."""
    ensure_same_org(user, course.organization_id, detail="Course not found")
    if user.role is UserRole.org_admin:
        return
    if user.role is UserRole.teacher:
        link = db.scalar(
            select(CourseTeacher.id).where(
                CourseTeacher.course_id == course.id,
                CourseTeacher.teacher_id == user.id,
            )
        )
        if link is None:
            raise HTTPException(status_code=404, detail="Course not found")
        return
    enrollment = db.scalar(
        select(Enrollment.id).where(
            Enrollment.course_id == course.id,
            Enrollment.student_id == user.id,
            Enrollment.status == EnrollmentStatus.active,
        )
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Course not found")


def _message_public(m: CourseMessage) -> CourseMessagePublic:
    return CourseMessagePublic(
        id=m.id,
        course_id=m.course_id,
        sender_id=m.sender_id,
        body=m.body,
        created_at=m.created_at,
        sender_name=m.sender.name if m.sender else None,
        sender_role=m.sender.role.value if m.sender else None,
    )


def _last_read_id(db: Session, user_id: int, course_id: int) -> int:
    row = db.scalar(
        select(CourseMessageRead).where(
            CourseMessageRead.user_id == user_id,
            CourseMessageRead.course_id == course_id,
        )
    )
    return row.last_read_id if row else 0


def _unread_for(db: Session, user_id: int, course_id: int) -> int:
    last = _last_read_id(db, user_id, course_id)
    return int(
        db.scalar(
            select(func.count())
            .select_from(CourseMessage)
            .where(
                CourseMessage.course_id == course_id,
                CourseMessage.id > last,
                CourseMessage.sender_id != user_id,
            )
        )
        or 0
    )


def _visible_course_ids(db: Session, user: User) -> list[int]:
    if user.role is UserRole.org_admin:
        return list(db.scalars(select(Course.id)).all())
    if user.role is UserRole.teacher:
        rows = db.scalars(
            select(CourseTeacher.course_id).where(CourseTeacher.teacher_id == user.id)
        ).all()
        return list(rows)
    return list(
        db.scalars(
            select(Enrollment.course_id).where(
                Enrollment.student_id == user.id,
                Enrollment.status == EnrollmentStatus.active,
            )
        ).all()
    )


@router.get("/courses/{course_id}/chat", response_model=CourseChatPage)
def list_course_chat(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    limit: int = Query(default=200, ge=1, le=500),
) -> CourseChatPage:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    _assert_course_member(db, user, course)

    total = int(
        db.scalar(
            select(func.count())
            .select_from(CourseMessage)
            .where(CourseMessage.course_id == course_id)
        )
        or 0
    )
    rows = db.scalars(
        select(CourseMessage)
        .where(CourseMessage.course_id == course_id)
        .order_by(CourseMessage.created_at.desc(), CourseMessage.id.desc())
        .limit(limit)
    ).all()
    items = [_message_public(m) for m in reversed(rows)]
    return CourseChatPage(total=total, unread=_unread_for(db, user.id, course_id), items=items)


@router.post("/courses/{course_id}/chat", response_model=CourseMessagePublic, status_code=201)
def post_course_chat(
    course_id: int,
    body: CourseMessageCreate,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    request: Request,
) -> CourseMessagePublic:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    _assert_course_member(db, user, course)

    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Empty message")

    msg = CourseMessage(course_id=course.id, sender_id=user.id, body=text)
    db.add(msg)
    db.flush()
    # el autor lo da por leído
    _touch_read(db, user.id, course.id, msg.id)
    log_action(
        db,
        action="course_chat.sent",
        actor_id=user.id,
        entity_type="course_message",
        entity_id=str(msg.id),
        course_id=course.id,
        payload={},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(msg)
    return _message_public(msg)


@router.post("/courses/{course_id}/chat/read", status_code=204)
def mark_course_chat_read(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    last_id: int = Query(default=0, ge=0),
) -> None:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    _assert_course_member(db, user, course)

    if last_id <= 0:
        last_id = int(
            db.scalar(
                select(func.max(CourseMessage.id)).where(CourseMessage.course_id == course_id)
            )
            or 0
        )
    _touch_read(db, user.id, course_id, last_id)
    db.commit()


@router.get("/me/course-chats", response_model=list[CourseChatRoomSummary])
def list_my_course_chats(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[CourseChatRoomSummary]:
    """Salas de chat del usuario con no leídos y último mensaje (para la nav/lista)."""
    course_ids = _visible_course_ids(db, user)
    if not course_ids:
        return []

    courses = {c.id: c for c in db.scalars(select(Course).where(Course.id.in_(course_ids))).all()}
    out: list[CourseChatRoomSummary] = []
    for cid, course in courses.items():
        last = db.scalar(
            select(CourseMessage)
            .where(CourseMessage.course_id == cid)
            .order_by(CourseMessage.created_at.desc(), CourseMessage.id.desc())
            .limit(1)
        )
        unread = _unread_for(db, user.id, cid)
        out.append(
            CourseChatRoomSummary(
                course_id=cid,
                course_name=course.name,
                course_code=course.code,
                unread=unread,
                last_message=last.body[:200] if last else None,
                last_at=last.created_at if last else None,
                last_sender_name=last.sender.name if last and last.sender else None,
            )
        )
    out.sort(key=lambda r: r.last_at or r.course_name, reverse=True)
    return out


def _touch_read(db: Session, user_id: int, course_id: int, last_id: int) -> None:
    row = db.scalar(
        select(CourseMessageRead).where(
            CourseMessageRead.user_id == user_id,
            CourseMessageRead.course_id == course_id,
        )
    )
    if row is None:
        db.add(
            CourseMessageRead(
                user_id=user_id,
                course_id=course_id,
                last_read_id=last_id,
            )
        )
    elif last_id > row.last_read_id:
        row.last_read_id = last_id
