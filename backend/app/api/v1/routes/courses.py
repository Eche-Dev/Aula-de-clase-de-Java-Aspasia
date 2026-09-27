"""Endpoints de cursos, asientos, matrículas y vista de aula."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Assignment,
    AttendanceRecord,
    Course,
    CourseTeacher,
    Enrollment,
    EnrollmentStatus,
    Seat,
    Submission,
    SubmissionStatus,
    User,
    UserRole,
)
from app.schemas.course import (
    ClassroomResponse,
    ClassroomSeat,
    CourseCreate,
    CoursePublic,
    CourseUpdate,
    EnrollmentCreate,
    EnrollmentPublic,
    SeatAssign,
    SeatPublic,
)
from app.schemas.student import (
    StudentAssignmentProgress,
    StudentAttendanceSummary,
    StudentCourseProgress,
    StudentProgressSummary,
)
from app.schemas.teacher import (
    CourseAssignmentStat,
    CourseOverview,
    CourseStudentStat,
    StudentAttendance,
    StudentCourseDetail,
    StudentSubmissionRow,
)
from app.security.policies import (
    CurrentUser,
    DbSession,
    ensure_same_org,
    require_admin,
    require_enrolled,
    require_staff_of_course,
)
from app.services.audit import log_action

router = APIRouter(tags=["courses"])


def _enrollment_public(e: Enrollment) -> EnrollmentPublic:
    return EnrollmentPublic(
        id=e.id,
        course_id=e.course_id,
        student_id=e.student_id,
        seat_id=e.seat_id,
        status=e.status,
        student_name=e.student.name if e.student else None,
        student_username=e.student.username if e.student else None,
        seat_row=e.seat.row if e.seat else None,
        seat_col=e.seat.col if e.seat else None,
    )


def _generate_seats(db: Session, course: Course) -> None:
    existing = db.scalar(select(func.count()).select_from(Seat).where(Seat.course_id == course.id))
    if existing and existing > 0:
        return
    for r in range(1, course.layout_rows + 1):
        for c in range(1, course.layout_cols + 1):
            db.add(Seat(course_id=course.id, row=r, col=c))


@router.get("/courses", response_model=list[CoursePublic])
def list_courses(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[CoursePublic]:
    if user.role is UserRole.org_admin:
        # Fase C: el admin solo ve cursos de SU organización
        rows = db.scalars(
            select(Course).where(Course.organization_id == user.organization_id).order_by(Course.id)
        ).all()
        return [CoursePublic.model_validate(c) for c in rows]
    if user.role is UserRole.teacher:
        rows = db.scalars(
            select(Course)
            .join(CourseTeacher, CourseTeacher.course_id == Course.id)
            .where(CourseTeacher.teacher_id == user.id)
            .order_by(Course.id)
        ).all()
        return [CoursePublic.model_validate(c) for c in rows]
    rows = db.scalars(
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(
            Enrollment.student_id == user.id,
            Enrollment.status == EnrollmentStatus.active,
        )
        .order_by(Course.id)
    ).all()
    return [CoursePublic.model_validate(c) for c in rows]


@router.post("/courses", response_model=CoursePublic, status_code=201)
def create_course(
    body: CourseCreate,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CoursePublic:
    code = body.code.strip().upper()
    # Fase C: el código es único dentro de la organización (no entre orgs)
    if db.scalar(
        select(Course).where(
            Course.code == code,
            Course.organization_id == _admin.organization_id,
        )
    ):
        raise HTTPException(status_code=409, detail="Course code already exists")
    course = Course(
        name=body.name,
        code=code,
        description=body.description,
        layout_rows=body.layout_rows,
        layout_cols=body.layout_cols,
        organization_id=_admin.organization_id,
        settings=body.settings,
    )
    db.add(course)
    db.flush()
    _generate_seats(db, course)
    log_action(
        db,
        action="course.created",
        actor_id=_admin.id,
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(course)
    return CoursePublic.model_validate(course)


@router.get("/courses/{course_id}", response_model=CoursePublic)
def get_course(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> CoursePublic:
    _user, course, _enr = require_enrolled(db, user, _get_course(db, course_id))
    return CoursePublic.model_validate(course)


def _get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.patch("/courses/{course_id}", response_model=CoursePublic)
def update_course(
    course_id: int,
    body: CourseUpdate,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> CoursePublic:
    course = _get_course(db, course_id)
    ensure_same_org(_admin, course.organization_id, detail="Course not found")
    data = body.model_dump(exclude_unset=True)
    layout_changed = False
    for key, value in data.items():
        if key in {"layout_rows", "layout_cols"} and value is not None:
            setattr(course, key, value)
            layout_changed = True
        elif key == "settings" and value is not None:
            course.settings = value
        elif value is not None:
            setattr(course, key, value)
    if layout_changed:
        # Solo regenerar asientos si ampliamos y no hay matrículas activas en posiciones nuevas
        db.flush()
        _generate_seats(db, course)
    db.commit()
    db.refresh(course)
    return CoursePublic.model_validate(course)


@router.get("/courses/{course_id}/classroom", response_model=ClassroomResponse)
def classroom(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> ClassroomResponse:
    _user, course, _enr = require_enrolled(db, user, _get_course(db, course_id))

    enrollments = db.scalars(
        select(Enrollment).where(
            Enrollment.course_id == course.id,
            Enrollment.status == EnrollmentStatus.active,
        )
    ).all()
    by_seat = {e.seat_id: e for e in enrollments if e.seat_id is not None}

    # Estado de entrega por estudiante (última submission del curso)
    latest: dict[int, SubmissionStatus] = {}
    subs = db.scalars(
        select(Submission).where(Submission.course_id == course.id).order_by(Submission.id.desc())
    ).all()
    for s in subs:
        if s.student_id not in latest:
            latest[s.student_id] = s.status

    seats_out: list[ClassroomSeat] = []
    for seat in course.seats:
        e = by_seat.get(seat.id)
        status_val: str | None = None
        if e is not None:
            st = latest.get(e.student_id)
            status_val = st.value if st else "none"
        seats_out.append(
            ClassroomSeat(
                seat_id=seat.id,
                row=seat.row,
                col=seat.col,
                enrollment_id=e.id if e else None,
                student_id=e.student_id if e else None,
                student_name=e.student.name if e and e.student else None,
                student_username=e.student.username if e and e.student else None,
                status=status_val,
            )
        )

    teachers = [
        {"id": ct.teacher.id, "name": ct.teacher.name}
        for ct in course.teachers
        if ct.teacher is not None
    ]
    return ClassroomResponse(
        course=CoursePublic.model_validate(course),
        seats=seats_out,
        rows=course.layout_rows,
        cols=course.layout_cols,
        teachers=teachers,
    )


@router.get("/courses/{course_id}/seats", response_model=list[SeatPublic])
def list_seats(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[SeatPublic]:
    _user, course, _enr = require_enrolled(db, user, _get_course(db, course_id))
    return [SeatPublic.model_validate(s) for s in course.seats]


@router.get("/courses/{course_id}/enrollments", response_model=list[EnrollmentPublic])
def list_enrollments(
    course_id: int,
    db: DbSession,
    _staff: Annotated[tuple[User, Course], Depends(require_staff_of_course)],
) -> list[EnrollmentPublic]:
    _user, course = _staff
    rows = db.scalars(
        select(Enrollment).where(Enrollment.course_id == course.id).order_by(Enrollment.id)
    ).all()
    return [_enrollment_public(e) for e in rows]


@router.post("/courses/{course_id}/enrollments", response_model=EnrollmentPublic, status_code=201)
def create_enrollment(
    course_id: int,
    body: EnrollmentCreate,
    db: DbSession,
    _staff: Annotated[tuple[User, Course], Depends(require_staff_of_course)],
    _admin: Annotated[User, Depends(require_admin)],
) -> EnrollmentPublic:
    _user, course = _staff
    student: User | None = None
    if body.student_id is not None:
        student = db.get(User, body.student_id)
    elif body.username:
        student = db.scalar(select(User).where(User.username == body.username))
    elif body.name:
        student = db.scalar(
            select(User).where(User.name == body.name, User.role == UserRole.student)
        )
    if student is None or student.role is not UserRole.student:
        raise HTTPException(status_code=404, detail="Student not found")
    # Fase C: no matricular alumnos de otra organización (404, no 403)
    ensure_same_org(_admin, student.organization_id, detail="Student not found")

    existing = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course.id,
            Enrollment.student_id == student.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already enrolled")

    seat_id = body.seat_id
    if seat_id is not None:
        seat = db.get(Seat, seat_id)
        if seat is None or seat.course_id != course.id:
            raise HTTPException(status_code=404, detail="Seat not found")
        taken = db.scalar(
            select(Enrollment).where(
                Enrollment.course_id == course.id,
                Enrollment.seat_id == seat_id,
            )
        )
        if taken is not None:
            raise HTTPException(status_code=409, detail="Seat already taken")

    enrollment = Enrollment(
        course_id=course.id,
        student_id=student.id,
        seat_id=seat_id,
        status=EnrollmentStatus.active,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return _enrollment_public(enrollment)


@router.patch(
    "/courses/{course_id}/enrollments/{enrollment_id}/seat",
    response_model=EnrollmentPublic,
)
def move_seat(
    course_id: int,
    enrollment_id: int,
    body: SeatAssign,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> EnrollmentPublic:
    course = _get_course(db, course_id)
    ensure_same_org(_admin, course.organization_id, detail="Course not found")
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None or enrollment.course_id != course.id:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if body.seat_id is None:
        enrollment.seat_id = None
    else:
        seat = db.get(Seat, body.seat_id)
        if seat is None or seat.course_id != course.id:
            raise HTTPException(status_code=404, detail="Seat not found")
        taken = db.scalar(
            select(Enrollment).where(
                Enrollment.course_id == course.id,
                Enrollment.seat_id == body.seat_id,
                Enrollment.id != enrollment.id,
            )
        )
        if taken is not None:
            raise HTTPException(status_code=409, detail="Seat already taken")
        enrollment.seat_id = body.seat_id
    # Las submissions cuelgan del student_id: mover asiento no las toca (D14)
    db.commit()
    db.refresh(enrollment)
    return _enrollment_public(enrollment)


@router.get("/courses/{course_id}/enrollments/me", response_model=EnrollmentPublic)
def my_enrollment(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> EnrollmentPublic:
    course = _get_course(db, course_id)
    # Fase C: no revelar cursos ajenos (404 aunque no exista matrícula)
    ensure_same_org(user, course.organization_id, detail="Course not found")
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course.id,
            Enrollment.student_id == user.id,
        )
    )
    if enrollment is None:
        if user.role in (UserRole.org_admin, UserRole.teacher):
            raise HTTPException(status_code=404, detail="No enrollment")
        raise HTTPException(status_code=404, detail="Course not found")
    return _enrollment_public(enrollment)


@router.delete("/courses/{course_id}/enrollments/{enrollment_id}", status_code=204)
def remove_enrollment(
    course_id: int,
    enrollment_id: int,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> None:
    course = _get_course(db, course_id)
    ensure_same_org(_admin, course.organization_id, detail="Course not found")
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None or enrollment.course_id != course.id:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    db.delete(enrollment)
    db.commit()


@router.post("/courses/{course_id}/teachers/{teacher_id}", status_code=204)
def assign_teacher(
    course_id: int,
    teacher_id: int,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> None:
    course = _get_course(db, course_id)
    ensure_same_org(_admin, course.organization_id, detail="Course not found")
    teacher = db.get(User, teacher_id)
    if teacher is None or teacher.role is not UserRole.teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    # Fase C: no asignar profesores de otra organización
    ensure_same_org(_admin, teacher.organization_id, detail="Teacher not found")
    if not db.scalar(
        select(CourseTeacher).where(
            CourseTeacher.course_id == course.id,
            CourseTeacher.teacher_id == teacher.id,
        )
    ):
        db.add(CourseTeacher(course_id=course.id, teacher_id=teacher.id))
        db.commit()


@router.delete("/courses/{course_id}/teachers/{teacher_id}", status_code=204)
def unassign_teacher(
    course_id: int,
    teacher_id: int,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> None:
    course = _get_course(db, course_id)
    ensure_same_org(_admin, course.organization_id, detail="Course not found")
    link = db.scalar(
        select(CourseTeacher).where(
            CourseTeacher.course_id == course.id,
            CourseTeacher.teacher_id == teacher_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(link)
    db.commit()


@router.get("/me/courses", response_model=list[CoursePublic])
def my_courses(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> list[CoursePublic]:
    return list_courses(db, user)


def _attendance_counts(db: Session, course_id: int) -> dict[int, dict[str, int]]:
    rows = db.execute(
        select(
            AttendanceRecord.student_id,
            AttendanceRecord.status,
            func.count(),
        )
        .where(AttendanceRecord.course_id == course_id)
        .group_by(AttendanceRecord.student_id, AttendanceRecord.status)
    ).all()
    out: dict[int, dict[str, int]] = {}
    for sid, status, cnt in rows:
        bucket = out.setdefault(int(sid), {"present": 0, "late": 0, "absent": 0, "excused": 0})
        bucket[str(status)] += int(cnt)
    return out


def _attendance_pct(counts: dict[str, int]) -> float | None:
    total = sum(counts.values())
    if total == 0:
        return None
    attended = counts.get("present", 0) + counts.get("late", 0)
    return round(attended / total * 100, 1)


@router.get("/courses/{course_id}/overview", response_model=CourseOverview)
def course_overview(
    course_id: int,
    db: DbSession,
    _staff: Annotated[tuple[User, Course], Depends(require_staff_of_course)],
) -> CourseOverview:
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
    submissions = db.scalars(select(Submission).where(Submission.course_id == course.id)).all()
    att_counts = _attendance_counts(db, course.id)

    delivered_by_assignment: dict[int, set[int]] = {}
    delivered_by_student: dict[int, set[int]] = {}
    last_score: dict[int, float] = {}
    last_eval_at: dict[int, datetime] = {}
    for sub in submissions:
        if sub.status is not SubmissionStatus.draft and sub.assignment_id is not None:
            delivered_by_assignment.setdefault(sub.assignment_id, set()).add(sub.student_id)
            delivered_by_student.setdefault(sub.student_id, set()).add(sub.assignment_id)
        if sub.evaluations:
            ev = sub.evaluations[0]
            if ev.score is None:
                continue
            prev = last_eval_at.get(sub.student_id)
            if prev is None or ev.created_at > prev:
                last_eval_at[sub.student_id] = ev.created_at
                last_score[sub.student_id] = float(ev.score)

    total_students = len(enrollments)
    assignment_stats = [
        CourseAssignmentStat(
            assignment_id=a.id,
            title=a.title,
            submitted=len(delivered_by_assignment.get(a.id, set())),
            total=total_students,
            pct=(
                round(len(delivered_by_assignment.get(a.id, set())) / total_students * 100, 1)
                if total_students
                else 0.0
            ),
        )
        for a in assignments
    ]

    assignment_total = len(assignments)
    student_stats = []
    for e in enrollments:
        delivered = len(delivered_by_student.get(e.student_id, set()))
        student_stats.append(
            CourseStudentStat(
                student_id=e.student_id,
                name=e.student.name if e.student else str(e.student_id),
                submitted=delivered,
                pending=max(0, assignment_total - delivered),
                last_score=last_score.get(e.student_id),
                attendance_pct=_attendance_pct(att_counts.get(e.student_id, {})),
            )
        )

    return CourseOverview(
        course_id=course.id,
        course_name=course.name,
        assignment_stats=assignment_stats,
        student_stats=student_stats,
    )


@router.get(
    "/courses/{course_id}/students/{student_id}",
    response_model=StudentCourseDetail,
)
def student_course_detail(
    course_id: int,
    student_id: int,
    db: DbSession,
    _staff: Annotated[tuple[User, Course], Depends(require_staff_of_course)],
) -> StudentCourseDetail:
    _user, course = _staff

    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course.id,
            Enrollment.student_id == student_id,
        )
    )
    if enrollment is None or enrollment.student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    student = enrollment.student

    assignments = db.scalars(select(Assignment).where(Assignment.course_id == course.id)).all()
    submissions = db.scalars(
        select(Submission)
        .where(
            Submission.course_id == course.id,
            Submission.student_id == student.id,
        )
        .order_by(Submission.id.desc())
    ).all()

    delivered: set[int] = set()
    latest_by_assignment: dict[int, Submission] = {}
    rows: list[StudentSubmissionRow] = []
    for sub in submissions:
        if sub.status is not SubmissionStatus.draft and sub.assignment_id is not None:
            delivered.add(sub.assignment_id)
        if sub.assignment_id is not None and sub.assignment_id not in latest_by_assignment:
            latest_by_assignment[sub.assignment_id] = sub
        ev = sub.evaluations[0] if sub.evaluations else None
        score = float(ev.score) if ev is not None and ev.score is not None else None
        rows.append(
            StudentSubmissionRow(
                submission_id=sub.id,
                assignment_id=sub.assignment_id,
                assignment_title=sub.assignment.title if sub.assignment else None,
                status=sub.status.value,
                submitted_at=sub.submitted_at,
                score=score,
                evaluated_at=ev.created_at if ev is not None else None,
            )
        )

    scores: list[float] = []
    for sub in latest_by_assignment.values():
        if not sub.evaluations:
            continue
        ev = sub.evaluations[0]
        if ev.score is not None:
            scores.append(float(ev.score))
    att = _attendance_counts(db, course.id).get(student.id, {})

    return StudentCourseDetail(
        student_id=student.id,
        name=student.name,
        username=student.username,
        course_id=course.id,
        course_name=course.name,
        submitted=len(delivered),
        pending=max(0, len(assignments) - len(delivered)),
        average_score=round(sum(scores) / len(scores), 1) if scores else None,
        attendance=StudentAttendance(
            present=att.get("present", 0),
            late=att.get("late", 0),
            absent=att.get("absent", 0),
            excused=att.get("excused", 0),
            pct=_attendance_pct(att),
        ),
        submissions=rows,
    )


MY_DELIVERED_STATUSES = (SubmissionStatus.submitted, SubmissionStatus.reviewed)


@router.get("/courses/{course_id}/my-progress", response_model=StudentCourseProgress)
def my_course_progress(
    course_id: int,
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> StudentCourseProgress:
    """Progreso propio en un curso (matriculado); solo sus entregas y su asistencia."""
    _user, course, enrollment = require_enrolled(db, user, _get_course(db, course_id))
    if enrollment is None and user.role is not UserRole.org_admin:
        raise HTTPException(status_code=403, detail="Student access required")

    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.course_id == course.id)
        .order_by(Assignment.due_at.asc().nulls_last(), Assignment.id.asc())
    ).all()

    submission_rows = db.scalars(
        select(Submission)
        .where(
            Submission.course_id == course.id,
            Submission.student_id == user.id,
            Submission.assignment_id.is_not(None),
        )
        .order_by(Submission.id.desc())
    ).all()
    latest: dict[int, Submission] = {}
    for sub in submission_rows:
        if sub.assignment_id is not None:
            latest.setdefault(int(sub.assignment_id), sub)

    stats: list[StudentAssignmentProgress] = []
    delivered = 0
    scores: list[float] = []
    for assignment in assignments:
        mine = latest.get(assignment.id)
        score: float | None = None
        submitted_at: datetime | None = mine.submitted_at if mine is not None else None
        if mine is not None:
            if mine.status in MY_DELIVERED_STATUSES:
                delivered += 1
            if mine.evaluations:
                ev = mine.evaluations[0]
                if ev.score is not None:
                    score = float(ev.score)
                    scores.append(score)
        stats.append(
            StudentAssignmentProgress(
                assignment_id=assignment.id,
                title=assignment.title,
                due_at=(
                    assignment.due_at.replace(tzinfo=UTC)
                    if assignment.due_at is not None and assignment.due_at.tzinfo is None
                    else assignment.due_at
                ),
                status=mine.status.value if mine is not None else "none",
                score=score,
                submitted_at=submitted_at,
            )
        )

    total = len(stats)
    att = _attendance_counts(db, course.id).get(user.id, {})

    return StudentCourseProgress(
        course_id=course.id,
        course_name=course.name,
        assignment_stats=stats,
        summary=StudentProgressSummary(
            total=total,
            delivered=delivered,
            pending=total - delivered,
            average_score=round(sum(scores) / len(scores), 1) if scores else None,
            delivery_pct=round(delivered / total * 100, 1) if total else 0.0,
        ),
        attendance=StudentAttendanceSummary(
            present=att.get("present", 0),
            late=att.get("late", 0),
            absent=att.get("absent", 0),
            excused=att.get("excused", 0),
            pct=_attendance_pct(att),
        ),
    )
