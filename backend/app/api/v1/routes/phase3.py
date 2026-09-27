"""Clonar curso, export CSV, metadatos GitHub y endpoints RGPD."""

import csv
import io
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.models import (
    Announcement,
    Assignment,
    AttendanceRecord,
    Course,
    CourseStatus,
    CourseTeacher,
    Enrollment,
    EnrollmentStatus,
    Rubric,
    Seat,
    Section,
    Submission,
    User,
    UserRole,
)
from app.schemas.course import CoursePublic
from app.schemas.phase3 import (
    CloneCourseRequest,
    GithubMetaResponse,
    RgpdExportResponse,
)
from app.security.policies import (
    CurrentUser,
    DbSession,
    can_read_submission,
    ensure_same_org,
    require_admin,
    require_staff_of_course,
)
from app.services.audit import log_action
from app.services.github_meta import fetch_repo_metadata, parse_github_url

router = APIRouter(tags=["phase3"])


@router.post("/courses/{course_id}/clone", response_model=CoursePublic, status_code=201)
def clone_course(
    course_id: int,
    body: CloneCourseRequest,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CoursePublic:
    source = db.get(Course, course_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Course not found")
    # Fase C: solo clonar cursos de la propia organización
    ensure_same_org(_admin, source.organization_id, detail="Course not found")
    code = body.code.strip().upper()
    # Fase C: código único dentro de la organización
    if db.scalar(
        select(Course).where(
            Course.code == code,
            Course.organization_id == _admin.organization_id,
        )
    ):
        raise HTTPException(status_code=409, detail="Course code already exists")

    clone = Course(
        name=body.name,
        code=code,
        description=source.description,
        status=CourseStatus.active,
        layout_rows=source.layout_rows,
        layout_cols=source.layout_cols,
        organization_id=_admin.organization_id,
        settings=dict(source.settings),
    )
    db.add(clone)
    db.flush()

    for r in range(1, clone.layout_rows + 1):
        for c in range(1, clone.layout_cols + 1):
            db.add(Seat(course_id=clone.id, row=r, col=c))

    for ct in source.teachers:
        if ct.teacher_id:
            db.add(CourseTeacher(course_id=clone.id, teacher_id=ct.teacher_id))

    section_map: dict[int, int] = {}
    sections = db.scalars(
        select(Section).where(Section.course_id == source.id).order_by(Section.order, Section.id)
    ).all()
    for s in sections:
        new_s = Section(
            course_id=clone.id,
            title=s.title,
            slug=s.slug,
            order=s.order,
            kind=s.kind,
            body_markdown=s.body_markdown,
            external_url=s.external_url,
        )
        db.add(new_s)
        db.flush()
        section_map[s.id] = new_s.id

    rubric_map: dict[int, int] = {}
    for rub in db.scalars(select(Rubric).where(Rubric.course_id == source.id)).all():
        new_r = Rubric(
            course_id=clone.id,
            title=rub.title,
            criteria=list(rub.criteria or []),
            created_by=rub.created_by,
        )
        db.add(new_r)
        db.flush()
        rubric_map[rub.id] = new_r.id

    for a in db.scalars(
        select(Assignment).where(Assignment.course_id == source.id).order_by(Assignment.id)
    ).all():
        db.add(
            Assignment(
                course_id=clone.id,
                section_id=section_map.get(a.section_id) if a.section_id else None,
                rubric_id=rubric_map.get(a.rubric_id) if a.rubric_id else None,
                title=a.title,
                description_markdown=a.description_markdown,
                due_at=a.due_at,
                max_score=a.max_score,
                visibility=a.visibility,
                created_by=a.created_by,
            )
        )

    for ann in db.scalars(
        select(Announcement)
        .where(Announcement.course_id == source.id)
        .order_by(Announcement.created_at.desc())
        .limit(20)
    ).all():
        db.add(
            Announcement(
                course_id=clone.id,
                author_id=ann.author_id,
                title=ann.title,
                body_markdown=ann.body_markdown,
            )
        )

    log_action(
        db,
        action="course.cloned",
        actor_id=_admin.id,
        entity_type="course",
        entity_id=clone.id,
        course_id=clone.id,
        payload={"source_id": source.id},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(clone)
    return CoursePublic.model_validate(clone)


@router.get("/courses/{course_id}/export/grades.csv")
def export_grades_csv(
    course_id: int,
    db: DbSession,
    _staff: Annotated[tuple[User, Course], Depends(require_staff_of_course)],
) -> Response:
    _user, course = _staff
    assignments = db.scalars(
        select(Assignment).where(Assignment.course_id == course.id).order_by(Assignment.id)
    ).all()
    submissions = db.scalars(select(Submission).where(Submission.course_id == course.id)).all()

    latest: dict[tuple[int, int | None], Submission] = {}
    for s in submissions:
        key = (s.student_id, s.assignment_id)
        prev = latest.get(key)
        if prev is None or s.id > prev.id:
            latest[key] = s

    students: dict[int, str] = {}
    for s in submissions:
        students[s.student_id] = s.student.name if s.student else str(s.student_id)
    for e in db.scalars(
        select(Enrollment).where(
            Enrollment.course_id == course.id,
            Enrollment.status == EnrollmentStatus.active,
        )
    ).all():
        if e.student_id not in students:
            students[e.student_id] = e.student.name if e.student else str(e.student_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["student_id", "student_name", "assignment_id", "assignment_title", "status", "score"]
    )
    for sid, name in sorted(students.items(), key=lambda x: x[1]):
        for a in assignments:
            sub = latest.get((sid, a.id))
            score = ""
            status = ""
            if sub is not None:
                status = sub.status.value
                if sub.evaluations and sub.evaluations[0].score is not None:
                    score = str(sub.evaluations[0].score)
            writer.writerow([sid, name, a.id, a.title, status, score])
        free = latest.get((sid, None))
        if free is not None:
            score = ""
            if free.evaluations and free.evaluations[0].score is not None:
                score = str(free.evaluations[0].score)
            writer.writerow([sid, name, "", "(free)", free.status.value, score])

    filename = f"grades_{course.code}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/submissions/{submission_id}/github-meta", response_model=GithubMetaResponse)
def submission_github_meta(
    submission_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> GithubMetaResponse:
    sub = db.get(Submission, submission_id)
    if sub is None or not can_read_submission(db, user, sub):
        raise HTTPException(status_code=404, detail="Submission not found")
    if not sub.github_url:
        raise HTTPException(status_code=404, detail="No GitHub URL on submission")
    if parse_github_url(sub.github_url) is None:
        return GithubMetaResponse(url=sub.github_url, ok=False, error="invalid_url")
    data = fetch_repo_metadata(sub.github_url)
    return GithubMetaResponse(**data)


@router.get("/me/export", response_model=RgpdExportResponse)
def rgpd_export(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> RgpdExportResponse:
    """Art. 20 RGPD: exportar todos los datos personales del titular."""
    enrollments = [
        {
            "id": e.id,
            "course_id": e.course_id,
            "status": e.status.value,
            "seat_id": e.seat_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in db.scalars(select(Enrollment).where(Enrollment.student_id == user.id)).all()
    ]
    subs = db.scalars(select(Submission).where(Submission.student_id == user.id)).all()
    submissions_out: list[dict[str, Any]] = []
    evaluations_out: list[dict[str, Any]] = []
    for s in subs:
        submissions_out.append(
            {
                "id": s.id,
                "course_id": s.course_id,
                "assignment_id": s.assignment_id,
                "github_url": s.github_url,
                "notes": s.notes,
                "status": s.status.value,
                "version": s.version,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "files": [
                    {
                        "id": f.id,
                        "original_name": f.original_name,
                        "size_bytes": f.size_bytes,
                        "sha256": f.sha256,
                    }
                    for f in s.files
                ],
            }
        )
        for ev in s.evaluations:
            evaluations_out.append(
                {
                    "id": ev.id,
                    "submission_id": s.id,
                    "score": str(ev.score) if ev.score is not None else None,
                    "rubric_scores": ev.rubric_scores,
                    "comment_markdown": ev.comment_markdown,
                    "created_at": ev.created_at.isoformat() if ev.created_at else None,
                }
            )
    attendance = [
        {
            "id": a.id,
            "course_id": a.course_id,
            "date": a.date.isoformat(),
            "status": a.status.value,
        }
        for a in db.scalars(
            select(AttendanceRecord).where(AttendanceRecord.student_id == user.id)
        ).all()
    ]
    return RgpdExportResponse(
        user={
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "username": user.username,
            "role": user.role.value,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        enrollments=enrollments,
        submissions=submissions_out,
        evaluations=evaluations_out,
        attendance=attendance,
        exported_at=datetime.now(UTC),
    )


@router.delete("/me/data", status_code=204)
def rgpd_erase_me(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    request: Request,
) -> None:
    """Art. 17 RGPD: anonimizar datos personales del estudiante."""
    if user.role is not UserRole.student:
        raise HTTPException(status_code=403, detail="Only students can erase via self-service")
    user.name = f"[ELIMINADO {user.id}]"
    user.email = None
    user.username = f"deleted_{user.id}_{secrets.token_hex(4)}"
    user.pin_hash = None
    user.is_active = False
    user.must_change_credentials = False
    for s in db.scalars(select(Submission).where(Submission.student_id == user.id)).all():
        s.github_url = None
        s.notes = ""
    log_action(
        db,
        action="rgpd.erased",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        payload={"anonymized": True},
        ip=request.client.host if request.client else None,
    )
    db.commit()


@router.delete("/admin/users/{user_id}/data", status_code=204)
def rgpd_erase_user_admin(
    user_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> None:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Fase C: no anonimizar usuarios de otra organización
    ensure_same_org(admin, target.organization_id, detail="User not found")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot erase yourself")
    target.name = f"[ELIMINADO {target.id}]"
    target.email = None
    if target.username:
        target.username = f"deleted_{target.id}_{secrets.token_hex(4)}"
    target.pin_hash = None
    target.password_hash = None
    target.is_active = False
    target.must_change_credentials = False
    for s in db.scalars(select(Submission).where(Submission.student_id == target.id)).all():
        s.github_url = None
        s.notes = ""
    log_action(
        db,
        action="rgpd.erased",
        actor_id=admin.id,
        entity_type="user",
        entity_id=target.id,
        payload={"by": "admin"},
        ip=request.client.host if request.client else None,
    )
    db.commit()
