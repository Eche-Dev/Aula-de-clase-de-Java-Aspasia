"""Endpoints de administración: usuarios, PIN, CSV, audit log, dashboard, observador."""

import csv
import io
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select

from app.core.security import hash_secret
from app.models import (
    AuditLog,
    Course,
    CourseStatus,
    Enrollment,
    Evaluation,
    Submission,
    SubmissionStatus,
    User,
    UserRole,
)
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserCreated,
    AdminUserPublic,
    AdminUserUpdate,
    AuditLogPublic,
    CsvImportRequest,
    CsvImportResult,
    PinResetRequest,
    PinResetResponse,
    StaffPasswordResetRequest,
    StaffPasswordResetResponse,
    UserStatusUpdate,
)
from app.schemas.dashboard import AdminDashboardStats, ObserverResponse, ObserverSubmissionRow
from app.security.policies import DbSession, ensure_same_org, require_admin
from app.services.audit import log_action

router = APIRouter(tags=["admin"])


def _generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _generate_password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789!@#$"
    return "".join(secrets.choice(alphabet) for _ in range(12))


@router.get("/admin/users", response_model=list[AdminUserPublic])
def list_users(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    role: UserRole | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[AdminUserPublic]:
    stmt = select(User).order_by(User.id)
    # Fase C: el admin solo ve usuarios de SU organización
    stmt = stmt.where(User.organization_id == _admin.organization_id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            (User.name.ilike(pattern))
            | (User.email.ilike(pattern))
            | (User.username.ilike(pattern))
        )
    rows = db.scalars(stmt.limit(limit)).all()
    return [AdminUserPublic.model_validate(u) for u in rows]


@router.post("/admin/users", response_model=AdminUserCreated, status_code=201)
def create_user(
    body: AdminUserCreate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> AdminUserCreated:
    if body.role is UserRole.student and not body.username:
        raise HTTPException(status_code=422, detail="username required for students")
    if body.role is not UserRole.student and not body.email:
        raise HTTPException(status_code=422, detail="email required for staff")
    if body.role is UserRole.super_admin:
        raise HTTPException(
            status_code=403,
            detail="super_admin only via CLI (scripts.create_admin --role super_admin)",
        )
    if body.email and db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status_code=409, detail="Email already exists")
    if body.username and db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status_code=409, detail="Username already exists")

    temporary_secret: str | None = None
    user = User(
        name=body.name,
        email=body.email,
        username=body.username,
        role=body.role,
        is_active=True,
        # Los usuarios creados por un admin pertenecen a su organización
        organization_id=admin.organization_id,
        # El PIN/contraseña temporal que entrega el admin ya es el definitivo para students
        must_change_credentials=body.role is not UserRole.student,
    )
    if body.role is UserRole.student:
        pin = body.pin or _generate_pin()
        user.pin_hash = hash_secret(pin)
        temporary_secret = pin
    else:
        password = body.password or _generate_password()
        user.password_hash = hash_secret(password)
        temporary_secret = password

    db.add(user)
    log_action(
        db,
        action="user.created",
        actor_id=admin.id,
        entity_type="user",
        entity_id="new",
        payload={"role": body.role.value, "name": body.name},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    out = AdminUserCreated.model_validate(user)
    out.temporary_secret = temporary_secret
    return out


@router.patch("/admin/users/{user_id}", response_model=AdminUserPublic)
def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> AdminUserPublic:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    ensure_same_org(admin, user.organization_id, detail="User not found")
    if body.email is not None and body.email != user.email:
        if db.scalar(select(User).where(User.email == body.email, User.id != user.id)):
            raise HTTPException(status_code=409, detail="Email already exists")
        user.email = body.email
    if body.username is not None and body.username != user.username:
        if db.scalar(select(User).where(User.username == body.username, User.id != user.id)):
            raise HTTPException(status_code=409, detail="Username already exists")
        user.username = body.username
    if body.name is not None:
        user.name = body.name
    if body.role is not None:
        if body.role is UserRole.super_admin:
            raise HTTPException(
                status_code=403,
                detail="super_admin only via CLI (scripts.create_admin --role super_admin)",
            )
        if user.id == admin.id and body.role is not UserRole.org_admin:
            raise HTTPException(status_code=400, detail="Cannot demote yourself")
        user.role = body.role
    if body.is_active is not None:
        if user.id == admin.id and not body.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        user.is_active = body.is_active
    log_action(
        db,
        action="user.updated",
        actor_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        payload=body.model_dump(exclude_none=True),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return AdminUserPublic.model_validate(user)


@router.post(
    "/admin/users/{user_id}/reset-password",
    response_model=StaffPasswordResetResponse,
)
def reset_staff_password(
    user_id: int,
    body: StaffPasswordResetRequest,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> StaffPasswordResetResponse:
    user = db.get(User, user_id)
    if user is None or user.role is UserRole.student:
        raise HTTPException(status_code=404, detail="Staff user not found")
    ensure_same_org(admin, user.organization_id, detail="Staff user not found")
    password = body.password or _generate_password()
    user.password_hash = hash_secret(password)
    user.must_change_credentials = True
    log_action(
        db,
        action="password.reset",
        actor_id=admin.id,
        entity_type="user",
        entity_id=str(user.id),
        payload={"reason": "admin_reset"},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return StaffPasswordResetResponse(user_id=user.id, password=password)


@router.patch("/admin/users/{user_id}/status", response_model=AdminUserPublic)
def set_user_status(
    user_id: int,
    body: UserStatusUpdate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> AdminUserPublic:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    ensure_same_org(admin, user.organization_id, detail="User not found")
    user.is_active = body.is_active
    log_action(
        db,
        action="user.status_changed",
        actor_id=admin.id,
        entity_type="user",
        entity_id=user.id,
        payload={"is_active": body.is_active},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return AdminUserPublic.model_validate(user)


@router.post("/admin/users/{user_id}/reset-pin", response_model=PinResetResponse)
def reset_pin(
    user_id: int,
    body: PinResetRequest,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> PinResetResponse:
    user = db.get(User, user_id)
    if user is None or user.role is not UserRole.student:
        raise HTTPException(status_code=404, detail="Student not found")
    ensure_same_org(admin, user.organization_id, detail="Student not found")
    pin = body.pin or _generate_pin()
    user.pin_hash = hash_secret(pin)
    # El PIN que genera el admin es directamente el definitivo (students no cambian su PIN)
    user.must_change_credentials = False
    log_action(
        db,
        action="pin.reset",
        actor_id=admin.id,
        entity_type="user",
        entity_id=user.id,
        # Nunca el PIN en claro en el log
        payload={"reason": "admin_reset"},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return PinResetResponse(user_id=user.id, pin=pin, must_change_credentials=False)


@router.post("/admin/courses/{course_id}/import-students", response_model=CsvImportResult)
def import_students_csv(
    course_id: int,
    body: CsvImportRequest,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CsvImportResult:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    ensure_same_org(admin, course.organization_id, detail="Course not found")

    reader = csv.reader(io.StringIO(body.csv_text))
    created = 0
    skipped = 0
    pins: dict[str, str] = {}

    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue
        # cabecera opcional
        if row[0].strip().lower() == "name" and created == 0 and skipped == 0:
            continue
        name = row[0].strip()
        if not name:
            skipped += 1
            continue
        email = row[1].strip() if len(row) > 1 and row[1].strip() else None
        username = row[2].strip() if len(row) > 2 and row[2].strip() else None
        if username is None:
            base = "".join(c.lower() for c in name if c.isalnum()) or "student"
            username = base
            suffix = 1
            while db.scalar(select(User).where(User.username == username)):
                suffix += 1
                username = f"{base}{suffix}"

        existing = db.scalar(select(User).where(User.username == username))
        if existing is not None:
            skipped += 1
            continue

        pin = _generate_pin()
        student = User(
            name=name,
            email=email,
            username=username,
            role=UserRole.student,
            pin_hash=hash_secret(pin),
            is_active=True,
            organization_id=admin.organization_id,
            must_change_credentials=False,
        )
        db.add(student)
        db.flush()
        db.add(Enrollment(course_id=course.id, student_id=student.id))
        pins[username] = pin
        created += 1

    log_action(
        db,
        action="students.imported",
        actor_id=admin.id,
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        payload={"created": created, "skipped": skipped},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return CsvImportResult(created=created, skipped=skipped, pins=pins)


@router.get("/admin/audit-logs", response_model=list[AuditLogPublic])
def list_audit_logs(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    action: str | None = Query(default=None, max_length=80),
    course_id: int | None = Query(default=None, ge=1),
    actor_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLogPublic]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    # Fase C: solo logs de actores de la propia organización
    stmt = stmt.where(
        AuditLog.actor_id.in_(select(User.id).where(User.organization_id == _admin.organization_id))
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if course_id is not None:
        stmt = stmt.where(AuditLog.course_id == course_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    rows = db.scalars(stmt.limit(limit)).all()
    out: list[AuditLogPublic] = []
    for row in rows:
        item = AuditLogPublic.model_validate(row)
        if row.actor_id is not None:
            actor = db.get(User, row.actor_id)
            item.actor_name = actor.name if actor else None
        out.append(item)
    return out


@router.get("/admin/metrics/course/{course_id}")
def course_metrics(
    course_id: int,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> dict[str, int]:
    """Métricas básicas: entregas por estado y matrículas."""
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    ensure_same_org(_admin, course.organization_id, detail="Course not found")
    from app.models import Submission, SubmissionStatus

    enrolled = int(
        db.scalar(
            select(func.count()).select_from(Enrollment).where(Enrollment.course_id == course.id)
        )
        or 0
    )
    total_subs = int(
        db.scalar(
            select(func.count()).select_from(Submission).where(Submission.course_id == course.id)
        )
        or 0
    )
    by_status: dict[str, int] = {}
    for status in SubmissionStatus:
        count = int(
            db.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.course_id == course.id,
                    Submission.status == status,
                )
            )
            or 0
        )
        by_status[status.value] = count
    return {
        "enrolled": enrolled,
        "submissions_total": total_subs,
        **{f"submissions_{k}": v for k, v in by_status.items()},
    }


@router.get("/admin/dashboard", response_model=AdminDashboardStats)
def admin_dashboard(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> AdminDashboardStats:
    org_id = _admin.organization_id
    org_courses = select(Course.id).where(Course.organization_id == org_id)
    org_actor_ids = select(User.id).where(User.organization_id == org_id)
    courses_total = int(
        db.scalar(select(func.count()).select_from(Course).where(Course.organization_id == org_id))
        or 0
    )
    courses_active = int(
        db.scalar(
            select(func.count())
            .select_from(Course)
            .where(Course.organization_id == org_id, Course.status == CourseStatus.active)
        )
        or 0
    )
    users_total = int(
        db.scalar(select(func.count()).select_from(User).where(User.organization_id == org_id)) or 0
    )
    students_total = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == org_id, User.role == UserRole.student)
        )
        or 0
    )
    teachers_total = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == org_id, User.role == UserRole.teacher)
        )
        or 0
    )
    enrollments_total = int(
        db.scalar(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.course_id.in_(org_courses))
        )
        or 0
    )
    submissions_total = int(
        db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(Submission.course_id.in_(org_courses))
        )
        or 0
    )
    submissions_pending = int(
        db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.course_id.in_(org_courses),
                Submission.status == SubmissionStatus.submitted,
            )
        )
        or 0
    )

    recent_audit_rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.actor_id.in_(org_actor_ids))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(8)
    ).all()
    recent_audit: list[dict[str, Any]] = []
    for row in recent_audit_rows:
        actor = db.get(User, row.actor_id) if row.actor_id else None
        recent_audit.append(
            {
                "id": row.id,
                "action": row.action,
                "actor_name": actor.name if actor else None,
                "course_id": row.course_id,
                "created_at": row.created_at.isoformat(),
            }
        )

    recent_subs = db.scalars(
        select(Submission)
        .where(
            Submission.course_id.in_(org_courses),
            Submission.status.in_([SubmissionStatus.submitted, SubmissionStatus.reviewed]),
        )
        .order_by(Submission.updated_at.desc())
        .limit(8)
    ).all()
    recent_submissions: list[dict[str, Any]] = []
    for sub in recent_subs:
        course = db.get(Course, sub.course_id)
        recent_submissions.append(
            {
                "id": sub.id,
                "student_name": sub.student.name if sub.student else None,
                "course_name": course.name if course else None,
                "status": sub.status.value,
                "updated_at": sub.updated_at.isoformat(),
            }
        )

    return AdminDashboardStats(
        courses_total=courses_total,
        courses_active=courses_active,
        users_total=users_total,
        students_total=students_total,
        teachers_total=teachers_total,
        enrollments_total=enrollments_total,
        submissions_pending=submissions_pending,
        submissions_total=submissions_total,
        recent_audit=recent_audit,
        recent_submissions=recent_submissions,
    )


@router.get("/admin/observer/submissions", response_model=ObserverResponse)
def observer_submissions(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    course_id: int | None = Query(default=None, ge=1),
    status: SubmissionStatus | None = None,
    student_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> ObserverResponse:
    """Vista global del admin: todas las entregas, archivos y notas."""
    stmt = select(Submission).order_by(Submission.updated_at.desc())
    # Fase C: solo entregas de cursos de la propia organización
    stmt = stmt.where(
        Submission.course_id.in_(
            select(Course.id).where(Course.organization_id == _admin.organization_id)
        )
    )
    if course_id is not None:
        stmt = stmt.where(Submission.course_id == course_id)
    if status is not None:
        stmt = stmt.where(Submission.status == status)
    if student_id is not None:
        stmt = stmt.where(Submission.student_id == student_id)
    rows = db.scalars(stmt.limit(limit)).all()

    items: list[ObserverSubmissionRow] = []
    for sub in rows:
        course = db.get(Course, sub.course_id)
        latest = sub.evaluations[0] if sub.evaluations else None
        items.append(
            ObserverSubmissionRow(
                id=sub.id,
                course_id=sub.course_id,
                course_name=course.name if course else "",
                course_code=course.code if course else "",
                student_id=sub.student_id,
                student_name=sub.student.name if sub.student else None,
                student_username=sub.student.username if sub.student else None,
                assignment_id=sub.assignment_id,
                assignment_title=sub.assignment.title if sub.assignment else None,
                status=sub.status.value,
                version=sub.version,
                github_url=sub.github_url,
                notes=sub.notes,
                submitted_at=sub.submitted_at,
                updated_at=sub.updated_at,
                file_count=len(sub.files),
                files=[
                    {
                        "id": f.id,
                        "original_name": f.original_name,
                        "mime": f.mime,
                        "size_bytes": f.size_bytes,
                    }
                    for f in sub.files
                ],
                latest_score=str(latest.score) if latest and latest.score is not None else None,
                latest_comment=latest.comment_markdown if latest else None,
                evaluated_at=latest.created_at if latest else None,
            )
        )
    return ObserverResponse(total=len(items), items=items)


@router.get("/admin/observer/evaluations")
def observer_evaluations(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    course_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Historial de evaluaciones (notas y comentarios) de todo el centro."""
    stmt = select(Evaluation).order_by(Evaluation.created_at.desc())
    rows = db.scalars(stmt.limit(limit)).all()
    out: list[dict[str, Any]] = []
    for ev in rows:
        sub = db.get(Submission, ev.submission_id)
        if sub is None:
            continue
        if course_id is not None and sub.course_id != course_id:
            continue
        course = db.get(Course, sub.course_id)
        # Fase C: solo evaluaciones de cursos de la propia organización
        if course is None or course.organization_id != _admin.organization_id:
            continue
        out.append(
            {
                "id": ev.id,
                "submission_id": ev.submission_id,
                "course_id": sub.course_id,
                "course_name": course.name if course else None,
                "student_id": sub.student_id,
                "student_name": sub.student.name if sub.student else None,
                "score": str(ev.score) if ev.score is not None else None,
                "comment_markdown": ev.comment_markdown,
                "teacher_id": ev.teacher_id,
                "teacher_name": ev.teacher.name if ev.teacher else None,
                "created_at": ev.created_at.isoformat(),
            }
        )
    return out
