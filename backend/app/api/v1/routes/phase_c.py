"""Fase C: dashboard multi-curso, gradebook, settings, reportes, backup."""

import contextlib
import csv
import io
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Announcement,
    Assignment,
    AttendanceRecord,
    AttendanceStatus,
    Course,
    CourseTeacher,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    Rubric,
    Section,
    Submission,
    SubmissionStatus,
    SystemSetting,
    User,
)
from app.schemas.phase_c import (
    CenterSettings,
    CenterSettingsUpdate,
    CourseBackup,
    GradebookCell,
    GradebookColumn,
    GradebookMatrix,
    GradebookStudent,
    MultiCourseDashboard,
    MultiCourseRow,
    ReportCourseRow,
    ReportOverview,
)
from app.security.policies import (
    DbSession,
    ensure_same_org,
    require_admin,
    require_permission,
    require_staff_of_course,
)
from app.services.audit import log_action

router = APIRouter(tags=["phase-c"])

SETTINGS_KEY = "center"


def _settings_dict(db: Session, org_id: int | None) -> dict[str, Any]:
    # Fase C: los ajustes del centro son POR organización (PK compuesta)
    row = db.get(SystemSetting, (SETTINGS_KEY, org_id))
    return dict(row.value) if row else {}


def _center_settings(db: Session, org_id: int | None) -> CenterSettings:
    raw = _settings_dict(db, org_id)
    return CenterSettings(**{k: v for k, v in raw.items() if k in CenterSettings.model_fields})


def _course_enrolled(db: Session, course_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Enrollment)
            .where(
                Enrollment.course_id == course_id,
                Enrollment.status == EnrollmentStatus.active,
            )
        )
        or 0
    )


def _course_submissions(db: Session, course_id: int) -> tuple[int, int]:
    total = int(
        db.scalar(
            select(func.count()).select_from(Submission).where(Submission.course_id == course_id)
        )
        or 0
    )
    pending = int(
        db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.course_id == course_id,
                Submission.status.in_([SubmissionStatus.submitted, SubmissionStatus.needs_changes]),
            )
        )
        or 0
    )
    return total, pending


@router.get("/admin/dashboard/multi", response_model=MultiCourseDashboard)
def multi_course_dashboard(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> MultiCourseDashboard:
    # Fase C: solo cursos de la propia organización
    courses = db.scalars(
        select(Course).where(Course.organization_id == _admin.organization_id).order_by(Course.name)
    ).all()
    rows: list[MultiCourseRow] = []
    totals = {
        "courses": len(courses),
        "enrolled": 0,
        "assignments": 0,
        "submissions": 0,
        "pending": 0,
    }
    for c in courses:
        enrolled = _course_enrolled(db, c.id)
        assignments = int(
            db.scalar(
                select(func.count()).select_from(Assignment).where(Assignment.course_id == c.id)
            )
            or 0
        )
        subs_total, subs_pending = _course_submissions(db, c.id)
        expected = enrolled * assignments
        rate = round((subs_total / expected) * 100, 1) if expected else 0.0
        rows.append(
            MultiCourseRow(
                course_id=c.id,
                name=c.name,
                code=c.code,
                status=c.status.value,
                enrolled=enrolled,
                assignments=assignments,
                submissions_total=subs_total,
                submissions_pending=subs_pending,
                completion_rate=rate,
            )
        )
        totals["enrolled"] += enrolled
        totals["assignments"] += assignments
        totals["submissions"] += subs_total
        totals["pending"] += subs_pending
    return MultiCourseDashboard(totals=totals, courses=rows)


@router.get("/courses/{course_id}/gradebook", response_model=GradebookMatrix)
def gradebook_matrix(
    course_id: int,
    db: DbSession,
    _staff: Annotated[tuple[User, Course], Depends(require_staff_of_course)],
) -> GradebookMatrix:
    _user, course = _staff
    assignments = db.scalars(
        select(Assignment).where(Assignment.course_id == course.id).order_by(Assignment.id)
    ).all()
    enrollments = db.scalars(
        select(Enrollment)
        .where(
            Enrollment.course_id == course.id,
            Enrollment.status == EnrollmentStatus.active,
        )
        .order_by(Enrollment.id)
    ).all()

    latest: dict[tuple[int, int], Submission] = {}
    for s in db.scalars(select(Submission).where(Submission.course_id == course.id)).all():
        if s.assignment_id is None:
            continue
        key = (s.student_id, s.assignment_id)
        prev = latest.get(key)
        if prev is None or s.id > prev.id:
            latest[key] = s

    columns = [
        GradebookColumn(
            assignment_id=a.id,
            title=a.title,
            max_score=str(a.max_score),
        )
        for a in assignments
    ]
    students: list[GradebookStudent] = []
    for e in enrollments:
        student = e.student
        cells: dict[str, GradebookCell] = {}
        scores: list[float] = []
        for a in assignments:
            sub = latest.get((e.student_id, a.id))
            status = sub.status.value if sub else None
            score: str | None = None
            if sub is not None and sub.evaluations:
                sc = sub.evaluations[0].score
                if sc is not None:
                    score = str(sc)
                    with contextlib.suppress(TypeError, ValueError):
                        scores.append(float(sc))
            cells[str(a.id)] = GradebookCell(assignment_id=a.id, status=status, score=score)
        avg = f"{sum(scores) / len(scores):.1f}" if scores else None
        students.append(
            GradebookStudent(
                student_id=e.student_id,
                name=student.name if student else str(e.student_id),
                username=student.username if student else None,
                cells=cells,
                average=avg,
            )
        )
    return GradebookMatrix(
        course_id=course.id,
        course_name=course.name,
        columns=columns,
        students=students,
    )


@router.get("/admin/settings", response_model=CenterSettings)
def get_center_settings(
    db: DbSession,
    _user: Annotated[User, Depends(require_permission("settings.manage"))],
) -> CenterSettings:
    return _center_settings(db, _user.organization_id)


@router.put("/admin/settings", response_model=CenterSettings)
def update_center_settings(
    body: CenterSettingsUpdate,
    db: DbSession,
    admin: Annotated[User, Depends(require_permission("settings.manage"))],
    request: Request,
) -> CenterSettings:
    org_id = admin.organization_id
    if org_id is None:
        raise HTTPException(status_code=403, detail="Admin access required")
    current = _center_settings(db, org_id)
    patch = body.model_dump(exclude_unset=True)
    merged = current.model_dump()
    merged.update(patch)
    row = db.get(SystemSetting, (SETTINGS_KEY, org_id))
    if row is None:
        db.add(SystemSetting(key=SETTINGS_KEY, organization_id=org_id, value=merged))
    else:
        row.value = merged
    log_action(
        db,
        action="settings.updated",
        actor_id=admin.id,
        entity_type="system_setting",
        entity_id=SETTINGS_KEY,
        payload={"fields": sorted(patch.keys())},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return CenterSettings(**merged)


@router.get("/admin/reports/overview", response_model=ReportOverview)
def reports_overview(
    db: DbSession,
    _user: Annotated[User, Depends(require_permission("reports.view"))],
) -> ReportOverview:
    center = _center_settings(db, _user.organization_id)
    # Fase C: solo cursos de la propia organización
    courses = db.scalars(
        select(Course).where(Course.organization_id == _user.organization_id).order_by(Course.name)
    ).all()
    rows: list[ReportCourseRow] = []
    totals = {
        "courses": len(courses),
        "enrolled": 0,
        "submissions": 0,
        "reviewed": 0,
    }
    for c in courses:
        enrolled = _course_enrolled(db, c.id)
        assignments = int(
            db.scalar(
                select(func.count()).select_from(Assignment).where(Assignment.course_id == c.id)
            )
            or 0
        )
        subs_total, _ = _course_submissions(db, c.id)
        reviewed = int(
            db.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.course_id == c.id,
                    Submission.status == SubmissionStatus.reviewed,
                )
            )
            or 0
        )
        avg = db.scalar(
            select(func.avg(Evaluation.score))
            .join(Submission, Submission.id == Evaluation.submission_id)
            .where(Submission.course_id == c.id)
        )
        avg_score = round(float(avg), 2) if avg is not None else None
        present = int(
            db.scalar(
                select(func.count())
                .select_from(AttendanceRecord)
                .where(
                    AttendanceRecord.course_id == c.id,
                    AttendanceRecord.status == AttendanceStatus.present,
                )
            )
            or 0
        )
        absent = int(
            db.scalar(
                select(func.count())
                .select_from(AttendanceRecord)
                .where(
                    AttendanceRecord.course_id == c.id,
                    AttendanceRecord.status == AttendanceStatus.absent,
                )
            )
            or 0
        )
        rows.append(
            ReportCourseRow(
                course_id=c.id,
                name=c.name,
                code=c.code,
                status=c.status.value,
                enrolled=enrolled,
                assignments=assignments,
                submissions=subs_total,
                reviewed=reviewed,
                avg_score=avg_score,
                attendance_present=present,
                attendance_absent=absent,
            )
        )
        totals["enrolled"] += enrolled
        totals["submissions"] += subs_total
        totals["reviewed"] += reviewed
    return ReportOverview(
        generated_at=datetime.now(UTC),
        center_name=center.center_name,
        totals=totals,
        courses=rows,
    )


@router.get("/admin/reports/overview.csv")
def reports_overview_csv(
    db: DbSession,
    _admin: Annotated[User, Depends(require_permission("reports.view"))],
) -> Response:
    overview = reports_overview(db, _admin)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "course_id",
            "name",
            "code",
            "status",
            "enrolled",
            "assignments",
            "submissions",
            "reviewed",
            "avg_score",
            "attendance_present",
            "attendance_absent",
        ]
    )
    for row in overview.courses:
        writer.writerow(
            [
                row.course_id,
                row.name,
                row.code,
                row.status,
                row.enrolled,
                row.assignments,
                row.submissions,
                row.reviewed,
                row.avg_score if row.avg_score is not None else "",
                row.attendance_present,
                row.attendance_absent,
            ]
        )
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="report_overview.csv"'},
    )


@router.get("/courses/{course_id}/backup", response_model=CourseBackup)
def course_backup(
    course_id: int,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CourseBackup:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    # Fase C: backup solo de cursos de la propia organización
    ensure_same_org(_admin, course.organization_id, detail="Course not found")
    db.refresh(course)

    course_teachers = db.scalars(
        select(CourseTeacher).where(CourseTeacher.course_id == course.id)
    ).all()

    log_action(
        db,
        action="course.backup",
        actor_id=_admin.id,
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        payload={},
        ip=request.client.host if request.client else None,
    )
    db.commit()

    submissions = db.scalars(select(Submission).where(Submission.course_id == course.id)).all()
    return CourseBackup(
        exported_at=datetime.now(UTC),
        course={
            "id": course.id,
            "name": course.name,
            "code": course.code,
            "description": course.description,
            "status": course.status.value,
            "layout_rows": course.layout_rows,
            "layout_cols": course.layout_cols,
            "settings": course.settings,
        },
        seats=[{"id": s.id, "row": s.row, "col": s.col} for s in course.seats],
        teachers=[
            {"teacher_id": t.teacher_id, "name": t.teacher.name if t.teacher else None}
            for t in course_teachers
        ],
        enrollments=[
            {
                "student_id": e.student_id,
                "username": e.student.username if e.student else None,
                "name": e.student.name if e.student else None,
                "status": e.status.value,
            }
            for e in db.scalars(select(Enrollment).where(Enrollment.course_id == course.id)).all()
        ],
        sections=[
            {
                "title": s.title,
                "slug": s.slug,
                "order": s.order,
                "kind": s.kind.value,
                "body_markdown": s.body_markdown,
                "external_url": s.external_url,
            }
            for s in db.scalars(
                select(Section).where(Section.course_id == course.id).order_by(Section.order)
            ).all()
        ],
        rubrics=[
            {"title": r.title, "criteria": r.criteria}
            for r in db.scalars(select(Rubric).where(Rubric.course_id == course.id)).all()
        ],
        assignments=[
            {
                "id": a.id,
                "title": a.title,
                "description_markdown": a.description_markdown,
                "due_at": a.due_at.isoformat() if a.due_at else None,
                "max_score": str(a.max_score),
                "visibility": a.visibility.value,
            }
            for a in db.scalars(select(Assignment).where(Assignment.course_id == course.id)).all()
        ],
        announcements=[
            {"title": an.title, "body_markdown": an.body_markdown}
            for an in db.scalars(
                select(Announcement).where(Announcement.course_id == course.id)
            ).all()
        ],
        submissions=[
            {
                "id": s.id,
                "assignment_id": s.assignment_id,
                "student_id": s.student_id,
                "status": s.status.value,
                "github_url": s.github_url,
                "notes": s.notes,
                "version": s.version,
                "scores": [str(e.score) if e.score is not None else None for e in s.evaluations],
            }
            for s in submissions
        ],
    )
