"""Chat 1:1: conversaciones, directorio messageable y envío."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Course, CourseTeacher, Enrollment, EnrollmentStatus, Message, User, UserRole
from app.schemas.message import (
    ConversationSummary,
    MessageCreate,
    MessageDirectoryEntry,
    MessagePublic,
    UnreadCountResponse,
    build_unread_count,
)
from app.security.policies import CurrentUser, DbSession
from app.services.audit import log_action

router = APIRouter(prefix="/messages", tags=["messages"])


def _message_public(m: Message) -> MessagePublic:
    return MessagePublic(
        id=m.id,
        sender_id=m.sender_id,
        recipient_id=m.recipient_id,
        course_id=m.course_id,
        body=m.body,
        read_at=m.read_at,
        created_at=m.created_at,
        sender_name=m.sender.name if m.sender else None,
        recipient_name=m.recipient.name if m.recipient else None,
    )


def _shared_active_course_ids(db: Session, a_id: int, b_id: int) -> list[int]:
    """Cursos donde ambos están activos (matriculado o staff)."""
    rows = db.execute(
        select(Enrollment.course_id)
        .join(CourseTeacher, CourseTeacher.course_id == Enrollment.course_id)
        .where(
            CourseTeacher.teacher_id == b_id,
            Enrollment.student_id == a_id,
            Enrollment.status == EnrollmentStatus.active,
        )
    ).scalars()
    return list(rows)


def _classmate_course_ids(db: Session, student_id: int) -> list[int]:
    """Cursos donde el estudiante está matriculado activamente."""
    return list(
        db.scalars(
            select(Enrollment.course_id).where(
                Enrollment.student_id == student_id,
                Enrollment.status == EnrollmentStatus.active,
            )
        ).all()
    )


def _shares_course_as_students(db: Session, a_id: int, b_id: int) -> bool:
    """Ambos matriculados en al menos un curso en común."""
    a_courses = set(_classmate_course_ids(db, a_id))
    if not a_courses:
        return False
    b_courses = set(_classmate_course_ids(db, b_id))
    return bool(a_courses & b_courses)


def _can_message(db: Session, sender: User, recipient: User) -> None:
    if recipient.id == sender.id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")
    if not recipient.is_active:
        raise HTTPException(status_code=404, detail="Recipient not found")
    # Fase C: nunca mensajear fuera de la propia organización (404, no 403)
    if sender.organization_id is not None and (recipient.organization_id != sender.organization_id):
        raise HTTPException(status_code=404, detail="Recipient not found")

    if sender.role is UserRole.org_admin:
        return

    if sender.role is UserRole.teacher:
        if recipient.role is UserRole.org_admin:
            return
        if recipient.role is UserRole.student:
            if _shared_active_course_ids(db, sender.id, recipient.id):
                return
            raise HTTPException(status_code=403, detail="Not allowed to message this user")
        raise HTTPException(status_code=403, detail="Not allowed to message this user")

    # student
    if recipient.role is UserRole.org_admin:
        return
    if recipient.role is UserRole.teacher:
        if _shared_active_course_ids(db, sender.id, recipient.id):
            return
        raise HTTPException(status_code=403, detail="Not allowed to message this user")
    if recipient.role is UserRole.student:
        if _shares_course_as_students(db, sender.id, recipient.id):
            return
        raise HTTPException(status_code=403, detail="Not allowed to message this user")
    raise HTTPException(status_code=403, detail="Not allowed to message this user")


def _directory_for(db: Session, user: User) -> list[MessageDirectoryEntry]:
    if user.role is UserRole.org_admin:
        rows = db.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.id != user.id,
                # Fase C: directorio solo de la propia organización
                User.organization_id == user.organization_id,
            )
            .order_by(User.name)
        ).all()
        return [
            MessageDirectoryEntry(
                id=u.id,
                name=u.name,
                role=u.role.value,
                username=u.username,
                email=u.email,
            )
            for u in rows
        ]

    if user.role is UserRole.teacher:
        admins = db.scalars(
            select(User).where(
                User.role == UserRole.org_admin,
                User.is_active.is_(True),
                # Fase C: solo admin de la propia organización
                User.organization_id == user.organization_id,
            )
        ).all()
        student_ids = list(
            db.scalars(
                select(Enrollment.student_id)
                .join(CourseTeacher, CourseTeacher.course_id == Enrollment.course_id)
                .where(
                    CourseTeacher.teacher_id == user.id,
                    Enrollment.status == EnrollmentStatus.active,
                )
                .distinct()
            ).all()
        )
        students = (
            db.scalars(
                select(User)
                .where(User.id.in_(student_ids), User.is_active.is_(True))
                .order_by(User.name)
            ).all()
            if student_ids
            else []
        )
        # cursos compartidos por alumno → course_ids del teacher con ese alumno
        out: list[MessageDirectoryEntry] = []
        for u in [*admins, *students]:
            course_ids: list[int] = []
            if u.role is UserRole.student:
                course_ids = _shared_active_course_ids(db, user.id, u.id)
            out.append(
                MessageDirectoryEntry(
                    id=u.id,
                    name=u.name,
                    role=u.role.value,
                    username=u.username,
                    email=u.email,
                    course_ids=course_ids,
                )
            )
        out.sort(key=lambda e: (e.role, e.name))
        return out

    # student
    my_courses = set(_classmate_course_ids(db, user.id))
    admins = db.scalars(
        select(User).where(
            User.role == UserRole.org_admin,
            User.is_active.is_(True),
            # Fase C: solo admin de la propia organización
            User.organization_id == user.organization_id,
        )
    ).all()
    teacher_ids = (
        list(
            db.scalars(
                select(CourseTeacher.teacher_id).where(CourseTeacher.course_id.in_(my_courses))
            ).all()
        )
        if my_courses
        else []
    )
    teachers = (
        db.scalars(
            select(User)
            .where(User.id.in_(teacher_ids), User.is_active.is_(True))
            .order_by(User.name)
        ).all()
        if teacher_ids
        else []
    )
    classmate_ids = (
        list(
            db.scalars(
                select(Enrollment.student_id)
                .where(
                    Enrollment.course_id.in_(my_courses),
                    Enrollment.status == EnrollmentStatus.active,
                    Enrollment.student_id != user.id,
                )
                .distinct()
            ).all()
        )
        if my_courses
        else []
    )
    classmates = (
        db.scalars(
            select(User)
            .where(User.id.in_(classmate_ids), User.is_active.is_(True))
            .order_by(User.name)
        ).all()
        if classmate_ids
        else []
    )

    out = []
    for u in [*admins, *teachers, *classmates]:
        shared_ids: list[int] = []
        if u.role is UserRole.student:
            shared_ids = sorted(my_courses & set(_classmate_course_ids(db, u.id)))
        elif u.role is UserRole.teacher:
            shared_ids = sorted(
                set(
                    db.scalars(
                        select(CourseTeacher.course_id).where(
                            CourseTeacher.teacher_id == u.id,
                            CourseTeacher.course_id.in_(my_courses),
                        )
                    ).all()
                )
            )
        out.append(
            MessageDirectoryEntry(
                id=u.id,
                name=u.name,
                role=u.role.value,
                username=u.username,
                email=u.email,
                course_ids=shared_ids,
            )
        )
    out.sort(key=lambda e: (e.role, e.name))
    return out


@router.get("/directory", response_model=list[MessageDirectoryEntry])
def message_directory(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[MessageDirectoryEntry]:
    """Personas con las que el usuario puede abrir chat privado (según rol)."""
    return _directory_for(db, user)


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> UnreadCountResponse:
    """Badge ligero: no leídos privados + por sala de curso."""
    from app.models import CourseMessage, CourseMessageRead

    private = int(
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.recipient_id == user.id, Message.read_at.is_(None))
        )
        or 0
    )

    # cursos visibles: matrículas activas o staff
    course_ids = set(_classmate_course_ids(db, user.id))
    if user.role in (UserRole.org_admin, UserRole.teacher):
        if user.role is UserRole.teacher:
            rows = db.scalars(
                select(CourseTeacher.course_id).where(CourseTeacher.teacher_id == user.id)
            ).all()
            course_ids |= set(rows)
        else:
            # Fase C: solo cursos de la propia organización
            course_ids |= set(
                db.scalars(
                    select(Course.id).where(Course.organization_id == user.organization_id)
                ).all()
            )

    courses: dict[str, int] = {}
    if course_ids:
        reads = {
            (r.course_id): r.last_read_id
            for r in db.scalars(
                select(CourseMessageRead).where(
                    CourseMessageRead.user_id == user.id,
                    CourseMessageRead.course_id.in_(course_ids),
                )
            ).all()
        }
        for cid in course_ids:
            last = reads.get(cid, 0)
            unread = int(
                db.scalar(
                    select(func.count())
                    .select_from(CourseMessage)
                    .where(
                        CourseMessage.course_id == cid,
                        CourseMessage.id > last,
                        CourseMessage.sender_id != user.id,
                    )
                )
                or 0
            )
            if unread:
                courses[str(cid)] = unread

    return build_unread_count(private, courses)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[ConversationSummary]:
    """Hilo más reciente con cada interlocutor + no leídos (portable SQLite/PG)."""
    rows = db.scalars(
        select(Message)
        .where(or_(Message.sender_id == user.id, Message.recipient_id == user.id))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(500)
    ).all()

    latest_by_partner: dict[int, Message] = {}
    for msg in rows:
        other_id = msg.recipient_id if msg.sender_id == user.id else msg.sender_id
        if other_id not in latest_by_partner:
            latest_by_partner[other_id] = msg

    out: list[ConversationSummary] = []
    for other_id, msg in latest_by_partner.items():
        other = db.get(User, other_id)
        if other is None:
            continue
        unread = int(
            db.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.sender_id == other_id,
                    Message.recipient_id == user.id,
                    Message.read_at.is_(None),
                )
            )
            or 0
        )
        out.append(
            ConversationSummary(
                user_id=other.id,
                name=other.name,
                role=other.role.value,
                username=other.username,
                email=other.email,
                last_message=msg.body[:200],
                last_at=msg.created_at,
                unread_count=unread,
            )
        )
    out.sort(key=lambda c: c.last_at, reverse=True)
    return out[:100]


@router.get("/{user_id}", response_model=list[MessagePublic])
def thread_with(
    user_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[MessagePublic]:
    other = db.get(User, user_id)
    if other is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Fase C: no abrir hilos con usuarios de otra organización
    if user.organization_id is not None and other.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="User not found")
    rows = db.scalars(
        select(Message)
        .where(
            or_(
                and_(Message.sender_id == user.id, Message.recipient_id == user_id),
                and_(Message.sender_id == user_id, Message.recipient_id == user.id),
            )
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(500)
    ).all()
    return [_message_public(m) for m in rows]


@router.post("", response_model=MessagePublic, status_code=201)
def send_message(
    body: MessageCreate,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    request: Request,
) -> MessagePublic:
    recipient = db.get(User, body.recipient_id)
    if recipient is None:
        raise HTTPException(status_code=404, detail="Recipient not found")
    _can_message(db, user, recipient)
    if body.course_id is not None:
        course = db.get(Course, body.course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        # Fase C: el curso adjunto debe ser de la propia organización
        if user.organization_id is not None and course.organization_id != user.organization_id:
            raise HTTPException(status_code=404, detail="Course not found")
    msg = Message(
        sender_id=user.id,
        recipient_id=recipient.id,
        course_id=body.course_id,
        body=body.body.strip(),
    )
    db.add(msg)
    log_action(
        db,
        action="message.sent",
        actor_id=user.id,
        entity_type="message",
        entity_id="new",
        course_id=body.course_id,
        payload={"recipient_id": recipient.id},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(msg)
    return _message_public(msg)


@router.post("/{user_id}/read", status_code=204)
def mark_read(
    user_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> None:
    rows = db.scalars(
        select(Message).where(
            Message.sender_id == user_id,
            Message.recipient_id == user.id,
            Message.read_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for m in rows:
        m.read_at = now
    if rows:
        db.commit()
