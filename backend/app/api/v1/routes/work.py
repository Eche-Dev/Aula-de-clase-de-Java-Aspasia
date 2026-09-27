"""Endpoints de tareas, entregas, archivos y evaluaciones."""

import contextlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Assignment,
    Course,
    CourseTeacher,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    Rubric,
    Submission,
    SubmissionFile,
    SubmissionStatus,
    User,
    UserRole,
)
from app.schemas.work import (
    AssignmentCreate,
    AssignmentPublic,
    AssignmentUpdate,
    EvaluationCreate,
    EvaluationPublic,
    SubmissionCreate,
    SubmissionPublic,
    SubmissionUpdate,
)
from app.security.policies import (
    CurrentUser,
    DbSession,
    can_read_submission,
    can_write_submission,
    ensure_same_org,
    require_teacher_of_course,
)
from app.services.audit import log_action
from app.storage import StorageError, get_storage, validate_content, validate_filename

router = APIRouter(tags=["work"])


def _get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _assert_staff_org(user: User, course: Course) -> None:
    """Fase C: staff solo de SU organización; super_admin no toca contenido académico."""
    if user.role is UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Staff access required")
    ensure_same_org(user, course.organization_id, detail="Course not found")


def _assert_enrolled(db: Session, user: User, course_id: int) -> None:
    if user.role in (UserRole.org_admin, UserRole.teacher):
        course = db.get(Course, course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        _assert_staff_org(user, course)
        return
    row = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.student_id == user.id,
            Enrollment.status == EnrollmentStatus.active,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Course not found")


def _visible_submission(db: Session, user: User, submission: Submission) -> Submission:
    if not can_read_submission(db, user, submission):
        # 404: no filtrar existencia (invariante 3)
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission


def _serialize_submission(
    db: Session,
    user: User,
    sub: Submission,
    *,
    full: bool | None = None,
) -> dict[str, Any]:
    """Serializa excluyendo evaluaciones cuando el requester no debe verlas."""
    if full is None:
        # Solo owner/staff ven evaluaciones; peer con visibility=class no
        is_owner = sub.student_id == user.id
        is_staff = user.role in (UserRole.org_admin, UserRole.teacher) and (
            user.role is UserRole.org_admin
            or db.scalar(
                select(CourseTeacher).where(
                    CourseTeacher.course_id == sub.course_id,
                    CourseTeacher.teacher_id == user.id,
                )
            )
            is not None
        )
        full = bool(is_owner or is_staff)

    latest = sub.evaluations[0] if sub.evaluations else None
    public = SubmissionPublic.model_validate(sub)
    data = public.model_dump()
    if full:
        data["latest_evaluation"] = (
            EvaluationPublic.model_validate(latest).model_dump() if latest else None
        )
        data["evaluations"] = [
            EvaluationPublic.model_validate(e).model_dump() for e in sub.evaluations
        ]
    else:
        data["latest_evaluation"] = None
        data["evaluations"] = []
    data["student_name"] = sub.student.name if sub.student else None
    return data


# ---- Assignments (teacher crea; students leen si enrolled) ----


@router.post("/assignments", response_model=AssignmentPublic, status_code=201)
def create_assignment(
    body: AssignmentCreate,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> AssignmentPublic:
    course = _get_course(db, body.course_id)
    _assert_staff_org(user, course)
    if user.role is UserRole.student:
        raise HTTPException(status_code=403, detail="Teacher access required")
    if user.role is UserRole.teacher:
        link = db.scalar(
            select(CourseTeacher).where(
                CourseTeacher.course_id == course.id,
                CourseTeacher.teacher_id == user.id,
            )
        )
        if link is None:
            raise HTTPException(status_code=404, detail="Course not found")
    if body.rubric_id is not None:
        rubric = db.get(Rubric, body.rubric_id)
        if rubric is None or rubric.course_id != course.id:
            raise HTTPException(status_code=404, detail="Rubric not found")
    assignment = Assignment(
        course_id=course.id,
        section_id=body.section_id,
        rubric_id=body.rubric_id,
        title=body.title,
        description_markdown=body.description_markdown,
        due_at=body.due_at,
        max_score=body.max_score,
        visibility=body.visibility,
        created_by=user.id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return AssignmentPublic.model_validate(assignment)


@router.get("/courses/{course_id}/assignments", response_model=list[AssignmentPublic])
def list_assignments(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[AssignmentPublic]:
    course = _get_course(db, course_id)
    _assert_enrolled(db, user, course.id)
    rows = db.scalars(
        select(Assignment).where(Assignment.course_id == course.id).order_by(Assignment.id.desc())
    ).all()
    return [AssignmentPublic.model_validate(a) for a in rows]


@router.get("/assignments/{assignment_id}", response_model=AssignmentPublic)
def get_assignment(
    assignment_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> AssignmentPublic:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _assert_enrolled(db, user, assignment.course_id)
    return AssignmentPublic.model_validate(assignment)


def _assert_teacher_of(db: Session, user: User, course_id: int) -> Course:
    course = _get_course(db, course_id)
    _assert_staff_org(user, course)
    if user.role is UserRole.student:
        raise HTTPException(status_code=403, detail="Teacher access required")
    if user.role is UserRole.teacher:
        link = db.scalar(
            select(CourseTeacher).where(
                CourseTeacher.course_id == course.id,
                CourseTeacher.teacher_id == user.id,
            )
        )
        if link is None:
            raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.patch("/assignments/{assignment_id}", response_model=AssignmentPublic)
def update_assignment(
    assignment_id: int,
    body: AssignmentUpdate,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> AssignmentPublic:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _assert_teacher_of(db, user, assignment.course_id)
    data = body.model_dump(exclude_unset=True)
    if body.rubric_id is not None:
        rubric = db.get(Rubric, body.rubric_id)
        if rubric is None or rubric.course_id != assignment.course_id:
            raise HTTPException(status_code=404, detail="Rubric not found")
    for key, value in data.items():
        setattr(assignment, key, value)
    db.commit()
    db.refresh(assignment)
    return AssignmentPublic.model_validate(assignment)


@router.delete("/assignments/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> None:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _assert_teacher_of(db, user, assignment.course_id)
    log_action(
        db,
        action="assignment.deleted",
        actor_id=user.id,
        entity_type="assignment",
        entity_id=assignment.id,
        course_id=assignment.course_id,
    )
    db.delete(assignment)
    db.commit()


# ---- Submissions ----


@router.post("/submissions", response_model=dict[str, Any], status_code=201)
def create_submission(
    body: SubmissionCreate,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> dict[str, Any]:
    if user.role is not UserRole.student:
        raise HTTPException(status_code=403, detail="Only students submit work")
    course = _get_course(db, body.course_id)
    _assert_enrolled(db, user, course.id)

    assignment: Assignment | None = None
    if body.assignment_id is not None:
        assignment = db.get(Assignment, body.assignment_id)
        if assignment is None or assignment.course_id != course.id:
            raise HTTPException(status_code=404, detail="Assignment not found")

    sub = Submission(
        assignment_id=assignment.id if assignment else None,
        course_id=course.id,
        student_id=user.id,
        github_url=body.github_url,
        notes=body.notes,
        status=SubmissionStatus.submitted if body.submit else SubmissionStatus.draft,
        submitted_at=datetime.now(UTC) if body.submit else None,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return _serialize_submission(db, user, sub)


@router.get("/courses/{course_id}/submissions", response_model=list[dict[str, Any]])
def list_submissions(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    student_id: int | None = None,
    mine: bool = False,
) -> list[dict[str, Any]]:
    course = _get_course(db, course_id)
    _assert_enrolled(db, user, course.id)

    stmt = select(Submission).where(Submission.course_id == course.id)
    if mine or user.role is UserRole.student:
        stmt = stmt.where(Submission.student_id == user.id)
    elif student_id is not None:
        stmt = stmt.where(Submission.student_id == student_id)
    stmt = stmt.order_by(Submission.id.desc())
    rows = db.scalars(stmt).all()

    out: list[dict[str, Any]] = []
    for sub in rows:
        if can_read_submission(db, user, sub) or sub.student_id == user.id:
            out.append(_serialize_submission(db, user, sub))
    return out


@router.get("/submissions/{submission_id}", response_model=dict)
def get_submission(
    submission_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> dict[str, Any]:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    _visible_submission(db, user, sub)
    return _serialize_submission(db, user, sub)


@router.patch("/submissions/{submission_id}", response_model=dict)
def update_submission(
    submission_id: int,
    body: SubmissionUpdate,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> dict[str, Any]:
    sub = db.get(Submission, submission_id)
    if sub is None or not can_write_submission(user, sub):
        raise HTTPException(status_code=404, detail="Submission not found")
    if body.github_url is not None:
        sub.github_url = body.github_url
    if body.notes is not None:
        sub.notes = body.notes
    if body.submit:
        sub.status = SubmissionStatus.submitted
        sub.submitted_at = datetime.now(UTC)
        sub.version += 1
    db.commit()
    db.refresh(sub)
    return _serialize_submission(db, user, sub)


@router.delete("/submissions/{submission_id}", status_code=204)
def delete_submission(
    submission_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> None:
    sub = db.get(Submission, submission_id)
    if sub is None or not can_write_submission(user, sub):
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.status is not SubmissionStatus.draft:
        raise HTTPException(status_code=409, detail="Only drafts can be deleted")
    storage = get_storage()
    for f in sub.files:
        with contextlib.suppress(StorageError):
            storage.delete(f.stored_name)
    db.delete(sub)
    db.commit()


@router.post("/submissions/{submission_id}/files", response_model=dict[str, Any], status_code=201)
async def upload_file(
    submission_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    file: Annotated[UploadFile, File(...)],
) -> dict[str, Any]:
    sub = db.get(Submission, submission_id)
    if sub is None or not can_write_submission(user, sub):
        raise HTTPException(status_code=404, detail="Submission not found")

    raw_name = file.filename or "upload"
    try:
        safe_name = validate_filename(raw_name)
        data = await file.read()
        validate_content(safe_name, data)
        if len(data) > settings.max_upload_bytes:
            raise StorageError("File too large", status_code=413)
        storage = get_storage()
        stored, mime, size, digest = storage.save(data, original_name=safe_name)
    except StorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    row = SubmissionFile(
        submission_id=sub.id,
        original_name=safe_name,
        stored_name=stored,
        mime=mime,
        size_bytes=size,
        sha256=digest,
    )
    db.add(row)
    if sub.status is SubmissionStatus.draft:
        sub.status = SubmissionStatus.submitted
        sub.submitted_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "original_name": row.original_name,
        "mime": row.mime,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
    }


@router.get("/submissions/{submission_id}/files/{file_id}/download")
def download_file(
    submission_id: int,
    file_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> Response:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    _visible_submission(db, user, sub)
    row = db.get(SubmissionFile, file_id)
    if row is None or row.submission_id != sub.id:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        stream = get_storage().open(row.stored_name)
    except StorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    safe = row.original_name.replace('"', "")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Type": row.mime,
        "Content-Length": str(row.size_bytes),
    }
    return StreamingResponse(stream, media_type=row.mime, headers=headers)


@router.delete("/submissions/{submission_id}/files/{file_id}", status_code=204)
def delete_file(
    submission_id: int,
    file_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> None:
    sub = db.get(Submission, submission_id)
    if sub is None or not can_write_submission(user, sub):
        raise HTTPException(status_code=404, detail="Submission not found")
    row = db.get(SubmissionFile, file_id)
    if row is None or row.submission_id != sub.id:
        raise HTTPException(status_code=404, detail="File not found")
    with contextlib.suppress(StorageError):
        get_storage().delete(row.stored_name)
    db.delete(row)
    db.commit()


# ---- Evaluations ----


@router.post(
    "/submissions/{submission_id}/evaluations", response_model=dict[str, Any], status_code=201
)
def create_evaluation(
    submission_id: int,
    body: EvaluationCreate,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
    request: Request,
) -> dict[str, Any]:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    # Solo staff del curso
    course = _get_course(db, sub.course_id)
    try:
        require_teacher_of_course(db, user, course)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Submission not found") from exc
        raise

    score = body.score
    if score is not None:
        assignment_max = sub.assignment.max_score if sub.assignment else Decimal("100.00")
        if score > assignment_max:
            raise HTTPException(status_code=400, detail="Score exceeds max_score")

    evaluation = Evaluation(
        submission_id=sub.id,
        teacher_id=user.id,
        score=score,
        rubric_scores=body.rubric_scores,
        comment_markdown=body.comment_markdown,
    )
    db.add(evaluation)
    if body.mark_status is not None:
        sub.status = body.mark_status
    elif score is not None or body.comment_markdown:
        sub.status = SubmissionStatus.reviewed
    log_action(
        db,
        action="evaluation.created",
        actor_id=user.id,
        entity_type="submission",
        entity_id=sub.id,
        course_id=sub.course_id,
        payload={"score": str(score) if score is not None else None},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(evaluation)
    return EvaluationPublic.model_validate(evaluation).model_dump()


@router.get("/submissions/{submission_id}/evaluations", response_model=list[dict[str, Any]])
def list_evaluations(
    submission_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[dict[str, Any]]:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    _visible_submission(db, user, sub)
    is_owner = sub.student_id == user.id
    is_staff = user.role in (UserRole.org_admin, UserRole.teacher)
    if not (is_owner or is_staff):
        # Peer: jamás evals ajenas
        return []
    return [EvaluationPublic.model_validate(e).model_dump() for e in sub.evaluations]
