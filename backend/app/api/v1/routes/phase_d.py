"""Fase D: categorías, cohorts, autoenrolamiento, roles, sesiones, desbloqueo."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Cohort,
    CohortMembership,
    Course,
    CourseCategory,
    CustomRole,
    Enrollment,
    EnrollmentStatus,
    RefreshToken,
    Seat,
    User,
    UserRole,
)
from app.schemas.scale import (
    KNOWN_PERMISSIONS,
    ActiveSessionPublic,
    AutoEnrollResult,
    CategoryCreate,
    CategoryPublic,
    CategoryUpdate,
    CohortCreate,
    CohortDetail,
    CohortMemberAdd,
    CohortMemberPublic,
    CohortPublic,
    CourseTaxonomyPublic,
    CourseTaxonomyUpdate,
    CustomRoleCreate,
    CustomRolePublic,
    CustomRoleUpdate,
    PermissionCatalog,
    SessionRevokeRequest,
    SessionRevokeResult,
    UnlockResult,
    UserCustomRoleAssign,
)
from app.security.policies import (
    CurrentUser,
    DbSession,
    ensure_same_org,
    require_admin,
    require_staff_of_course,
    user_permissions,
)
from app.services.audit import log_action

router = APIRouter(tags=["phase-d"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --- Categorías (15) -------------------------------------------------------


@router.get("/categories", response_model=list[CategoryPublic])
def list_categories(
    db: DbSession,
    _user: Annotated[User, Depends(CurrentUser)],
) -> list[CategoryPublic]:
    # Fase C: categorías (y sus conteos) de la propia organización
    categories = db.scalars(
        select(CourseCategory)
        .where(CourseCategory.organization_id == _user.organization_id)
        .order_by(CourseCategory.name)
    ).all()
    counts: dict[int, int] = {
        int(k): int(v)
        for k, v in db.execute(
            select(Course.category_id, func.count())
            .where(
                Course.category_id.is_not(None),
                Course.organization_id == _user.organization_id,
            )
            .group_by(Course.category_id)
        ).all()
        if k is not None
    }
    out: list[CategoryPublic] = []
    for c in categories:
        item = CategoryPublic.model_validate(c)
        item.course_count = counts.get(c.id, 0)
        out.append(item)
    return out


@router.post("/admin/categories", response_model=CategoryPublic, status_code=201)
def create_category(
    body: CategoryCreate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CategoryPublic:
    # Fase C: slug único dentro de la organización
    if db.scalar(
        select(CourseCategory).where(
            CourseCategory.slug == body.slug,
            CourseCategory.organization_id == admin.organization_id,
        )
    ):
        raise HTTPException(status_code=409, detail="Slug already exists")
    category = CourseCategory(**body.model_dump(), organization_id=admin.organization_id)
    db.add(category)
    log_action(
        db,
        action="category.created",
        actor_id=admin.id,
        entity_type="category",
        payload={"slug": body.slug},
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(category)
    return CategoryPublic.model_validate(category)


@router.patch("/admin/categories/{category_id}", response_model=CategoryPublic)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CategoryPublic:
    category = db.get(CourseCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    ensure_same_org(admin, category.organization_id, detail="Category not found")
    data = body.model_dump(exclude_unset=True)
    if (
        data.get("slug") is not None
        and data["slug"] != category.slug
        and db.scalar(
            select(CourseCategory).where(
                CourseCategory.slug == data["slug"],
                CourseCategory.organization_id == admin.organization_id,
                CourseCategory.id != category.id,
            )
        )
    ):
        raise HTTPException(status_code=409, detail="Slug already exists")
    for key, value in data.items():
        setattr(category, key, value)
    log_action(
        db,
        action="category.updated",
        actor_id=admin.id,
        entity_type="category",
        entity_id=category.id,
        payload={"fields": sorted(data.keys())},
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(category)
    return CategoryPublic.model_validate(category)


@router.delete("/admin/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> None:
    category = db.get(CourseCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    ensure_same_org(admin, category.organization_id, detail="Category not found")
    db.delete(category)
    log_action(
        db,
        action="category.deleted",
        actor_id=admin.id,
        entity_type="category",
        entity_id=category_id,
        ip=_client_ip(request),
    )
    db.commit()


@router.patch(
    "/admin/courses/{course_id}/taxonomy",
    response_model=CourseTaxonomyPublic,
)
def set_course_taxonomy(
    course_id: int,
    body: CourseTaxonomyUpdate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CourseTaxonomyPublic:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    ensure_same_org(admin, course.organization_id, detail="Course not found")
    if body.category_id is not None:
        category = db.get(CourseCategory, body.category_id)
        if category is None or category.organization_id != admin.organization_id:
            raise HTTPException(status_code=404, detail="Category not found")
    if body.cohort_id is not None:
        cohort = db.get(Cohort, body.cohort_id)
        if cohort is None or cohort.organization_id != admin.organization_id:
            raise HTTPException(status_code=404, detail="Cohort not found")
    course.category_id = body.category_id
    course.cohort_id = body.cohort_id
    log_action(
        db,
        action="course.taxonomy_updated",
        actor_id=admin.id,
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        payload={"category_id": body.category_id, "cohort_id": body.cohort_id},
        ip=_client_ip(request),
    )
    db.commit()
    return CourseTaxonomyPublic(
        course_id=course.id,
        category_id=course.category_id,
        cohort_id=course.cohort_id,
    )


# --- Cohorts y autoenrolamiento (15) --------------------------------------


def _cohort_counts(db: Session) -> dict[int, int]:
    return {
        int(k): int(v)
        for k, v in db.execute(
            select(CohortMembership.cohort_id, func.count()).group_by(CohortMembership.cohort_id)
        ).all()
        if k is not None
    }


@router.get("/admin/cohorts", response_model=list[CohortPublic])
def list_cohorts(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> list[CohortPublic]:
    # Fase C: cohorts de la propia organización
    cohorts = db.scalars(
        select(Cohort).where(Cohort.organization_id == _admin.organization_id).order_by(Cohort.name)
    ).all()
    counts = _cohort_counts(db)
    out: list[CohortPublic] = []
    for c in cohorts:
        item = CohortPublic.model_validate(c)
        item.member_count = counts.get(c.id, 0)
        out.append(item)
    return out


@router.post("/admin/cohorts", response_model=CohortPublic, status_code=201)
def create_cohort(
    body: CohortCreate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CohortPublic:
    # Fase C: code único dentro de la organización
    if db.scalar(
        select(Cohort).where(
            Cohort.code == body.code,
            Cohort.organization_id == admin.organization_id,
        )
    ):
        raise HTTPException(status_code=409, detail="Cohort code already exists")
    if body.category_id is not None:
        category = db.get(CourseCategory, body.category_id)
        if category is None or category.organization_id != admin.organization_id:
            raise HTTPException(status_code=404, detail="Category not found")
    cohort = Cohort(**body.model_dump(), organization_id=admin.organization_id)
    db.add(cohort)
    log_action(
        db,
        action="cohort.created",
        actor_id=admin.id,
        entity_type="cohort",
        payload={"code": body.code},
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(cohort)
    return CohortPublic.model_validate(cohort)


@router.get("/admin/cohorts/{cohort_id}", response_model=CohortDetail)
def get_cohort(
    cohort_id: int,
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> CohortDetail:
    cohort = db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found")
    ensure_same_org(_admin, cohort.organization_id, detail="Cohort not found")
    counts = _cohort_counts(db)
    detail = CohortDetail.model_validate(cohort)
    detail.member_count = counts.get(cohort.id, 0)
    detail.members = [
        CohortMemberPublic(
            student_id=m.student_id,
            name=m.student.name if m.student else str(m.student_id),
            username=m.student.username if m.student else None,
        )
        for m in cohort.memberships
    ]
    return detail


@router.delete("/admin/cohorts/{cohort_id}", status_code=204)
def delete_cohort(
    cohort_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> None:
    cohort = db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found")
    ensure_same_org(admin, cohort.organization_id, detail="Cohort not found")
    db.delete(cohort)
    log_action(
        db,
        action="cohort.deleted",
        actor_id=admin.id,
        entity_type="cohort",
        entity_id=cohort_id,
        ip=_client_ip(request),
    )
    db.commit()


@router.post("/admin/cohorts/{cohort_id}/members", response_model=list[CohortMemberPublic])
def add_cohort_members(
    cohort_id: int,
    body: CohortMemberAdd,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> list[CohortMemberPublic]:
    cohort = db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found")
    ensure_same_org(admin, cohort.organization_id, detail="Cohort not found")
    ids = list(body.student_ids or [])
    if body.student_id is not None:
        ids.append(body.student_id)
    if not ids:
        raise HTTPException(status_code=422, detail="student_id or student_ids required")

    added: list[CohortMemberPublic] = []
    for student_id in dict.fromkeys(ids):
        student = db.get(User, student_id)
        if student is None or student.role is not UserRole.student:
            raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
        # Fase C: no mezclar alumnos de otra organización
        ensure_same_org(admin, student.organization_id, detail=f"Student {student_id} not found")
        exists = db.scalar(
            select(CohortMembership).where(
                CohortMembership.cohort_id == cohort.id,
                CohortMembership.student_id == student_id,
            )
        )
        if exists is None:
            db.add(CohortMembership(cohort_id=cohort.id, student_id=student_id))
            added.append(
                CohortMemberPublic(
                    student_id=student_id, name=student.name, username=student.username
                )
            )
    log_action(
        db,
        action="cohort.members_added",
        actor_id=admin.id,
        entity_type="cohort",
        entity_id=cohort.id,
        payload={"added": len(added)},
        ip=_client_ip(request),
    )
    db.commit()
    return added


@router.delete("/admin/cohorts/{cohort_id}/members/{student_id}", status_code=204)
def remove_cohort_member(
    cohort_id: int,
    student_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> None:
    cohort = db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    ensure_same_org(admin, cohort.organization_id, detail="Membership not found")
    membership = db.scalar(
        select(CohortMembership).where(
            CohortMembership.cohort_id == cohort_id,
            CohortMembership.student_id == student_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found")
    db.delete(membership)
    log_action(
        db,
        action="cohort.member_removed",
        actor_id=admin.id,
        entity_type="cohort",
        entity_id=cohort_id,
        payload={"student_id": student_id},
        ip=_client_ip(request),
    )
    db.commit()


@router.post("/courses/{course_id}/auto-enroll", response_model=AutoEnrollResult)
def auto_enroll_course(
    course_id: int,
    db: DbSession,
    _staff: Annotated[tuple[User, Course], Depends(require_staff_of_course)],
    request: Request,
) -> AutoEnrollResult:
    _user, course = _staff
    if course.cohort_id is None:
        return AutoEnrollResult(enrolled=0, skipped=0, reason="no_cohort")

    cohort = db.get(Cohort, course.cohort_id)
    # Fase C: la cohorte debe pertenecer a la misma organización que el curso
    if cohort is None or cohort.organization_id != course.organization_id:
        return AutoEnrollResult(enrolled=0, skipped=0, reason="no_cohort")

    member_ids = list(
        db.scalars(
            select(CohortMembership.student_id).where(CohortMembership.cohort_id == cohort.id)
        ).all()
    )
    already = set(
        db.scalars(
            select(Enrollment.student_id).where(
                Enrollment.course_id == course.id,
                Enrollment.status == EnrollmentStatus.active,
            )
        ).all()
    )
    taken_seat_ids = set(
        db.scalars(
            select(Enrollment.seat_id).where(
                Enrollment.course_id == course.id,
                Enrollment.seat_id.is_not(None),
            )
        ).all()
    )
    free_seats = [
        s
        for s in db.scalars(select(Seat).where(Seat.course_id == course.id)).all()
        if s.id not in taken_seat_ids
    ]

    enrolled = 0
    skipped = 0
    for student_id in member_ids:
        if student_id in already:
            skipped += 1
            continue
        if not free_seats:
            skipped += 1
            continue
        seat = free_seats.pop(0)
        db.add(
            Enrollment(
                course_id=course.id,
                student_id=student_id,
                seat_id=seat.id,
                status=EnrollmentStatus.active,
            )
        )
        enrolled += 1

    reason = None
    if member_ids and enrolled == 0 and skipped:
        reason = "no_free_seats" if free_seats == [] else "already_enrolled"
    elif not member_ids:
        reason = "empty_cohort"

    log_action(
        db,
        action="course.auto_enrolled",
        actor_id=_user.id,
        entity_type="course",
        entity_id=course.id,
        course_id=course.id,
        payload={"enrolled": enrolled, "skipped": skipped, "reason": reason},
        ip=_client_ip(request),
    )
    db.commit()
    return AutoEnrollResult(enrolled=enrolled, skipped=skipped, reason=reason)


# --- Roles personalizados (16) ---------------------------------------------


@router.get("/admin/permissions", response_model=PermissionCatalog)
def permission_catalog(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> PermissionCatalog:
    return PermissionCatalog(permissions=KNOWN_PERMISSIONS, effective=list(KNOWN_PERMISSIONS))


@router.get("/auth/permissions", response_model=PermissionCatalog)
def effective_permissions(
    db: DbSession,
    user: Annotated[User, Depends(CurrentUser)],
) -> PermissionCatalog:
    return PermissionCatalog(permissions=KNOWN_PERMISSIONS, effective=user_permissions(user))


@router.get("/admin/roles", response_model=list[CustomRolePublic])
def list_roles(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> list[CustomRolePublic]:
    # Fase C: roles (y sus conteos) de la propia organización
    roles = db.scalars(
        select(CustomRole)
        .where(CustomRole.organization_id == _admin.organization_id)
        .order_by(CustomRole.name)
    ).all()
    counts: dict[int, int] = {
        int(k): int(v)
        for k, v in db.execute(
            select(User.custom_role_id, func.count())
            .where(
                User.custom_role_id.is_not(None),
                User.organization_id == _admin.organization_id,
            )
            .group_by(User.custom_role_id)
        ).all()
        if k is not None
    }
    out: list[CustomRolePublic] = []
    for r in roles:
        item = CustomRolePublic.model_validate(r)
        item.assigned_count = counts.get(r.id, 0)
        out.append(item)
    return out


@router.post("/admin/roles", response_model=CustomRolePublic, status_code=201)
def create_role(
    body: CustomRoleCreate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CustomRolePublic:
    invalid = [p for p in body.permissions if p not in KNOWN_PERMISSIONS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown permissions: {invalid}")
    # Fase C: nombre de rol único dentro de la organización
    if db.scalar(
        select(CustomRole).where(
            CustomRole.name == body.name,
            CustomRole.organization_id == admin.organization_id,
        )
    ):
        raise HTTPException(status_code=409, detail="Role name already exists")
    role = CustomRole(**body.model_dump(), organization_id=admin.organization_id)
    db.add(role)
    log_action(
        db,
        action="role.created",
        actor_id=admin.id,
        entity_type="custom_role",
        payload={"name": body.name, "permissions": body.permissions},
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(role)
    return CustomRolePublic.model_validate(role)


@router.patch("/admin/roles/{role_id}", response_model=CustomRolePublic)
def update_role(
    role_id: int,
    body: CustomRoleUpdate,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CustomRolePublic:
    role = db.get(CustomRole, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    ensure_same_org(admin, role.organization_id, detail="Role not found")
    data = body.model_dump(exclude_unset=True)
    perms = data.get("permissions")
    if perms is not None:
        invalid = [p for p in perms if p not in KNOWN_PERMISSIONS]
        if invalid:
            raise HTTPException(status_code=422, detail=f"Unknown permissions: {invalid}")
    if (
        data.get("name") is not None
        and data["name"] != role.name
        and db.scalar(
            select(CustomRole).where(
                CustomRole.name == data["name"],
                CustomRole.organization_id == admin.organization_id,
                CustomRole.id != role.id,
            )
        )
    ):
        raise HTTPException(status_code=409, detail="Role name already exists")
    for key, value in data.items():
        setattr(role, key, value)
    log_action(
        db,
        action="role.updated",
        actor_id=admin.id,
        entity_type="custom_role",
        entity_id=role.id,
        payload={"fields": sorted(data.keys())},
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(role)
    return CustomRolePublic.model_validate(role)


@router.delete("/admin/roles/{role_id}", status_code=204)
def delete_role(
    role_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> None:
    role = db.get(CustomRole, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    ensure_same_org(admin, role.organization_id, detail="Role not found")
    db.delete(role)
    log_action(
        db,
        action="role.deleted",
        actor_id=admin.id,
        entity_type="custom_role",
        entity_id=role_id,
        ip=_client_ip(request),
    )
    db.commit()


@router.post("/admin/users/{user_id}/custom-role", response_model=CustomRolePublic | None)
def assign_custom_role(
    user_id: int,
    body: UserCustomRoleAssign,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> CustomRolePublic | None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    ensure_same_org(admin, user.organization_id, detail="User not found")
    if body.custom_role_id is not None:
        role = db.get(CustomRole, body.custom_role_id)
        if role is None or role.organization_id != admin.organization_id:
            raise HTTPException(status_code=404, detail="Role not found")
    user.custom_role_id = body.custom_role_id
    log_action(
        db,
        action="user.custom_role_assigned",
        actor_id=admin.id,
        entity_type="user",
        entity_id=user.id,
        payload={"custom_role_id": body.custom_role_id},
        ip=_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    if user.custom_role is None:
        return None
    counts: dict[int, int] = {
        int(k): int(v)
        for k, v in db.execute(
            select(User.custom_role_id, func.count())
            .where(User.custom_role_id.is_not(None))
            .group_by(User.custom_role_id)
        ).all()
        if k is not None
    }
    out = CustomRolePublic.model_validate(user.custom_role)
    out.assigned_count = counts.get(user.custom_role.id, 0)
    return out


# --- Sesiones activas y desbloqueo (16) ------------------------------------


@router.get("/admin/sessions", response_model=list[ActiveSessionPublic])
def active_sessions(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
) -> list[ActiveSessionPublic]:
    now = datetime.now(UTC)
    # Fase C: solo sesiones de usuarios de la propia organización
    rows = db.scalars(
        select(RefreshToken)
        .join(User, User.id == RefreshToken.user_id)
        .where(
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
            User.organization_id == _admin.organization_id,
        )
        .order_by(RefreshToken.created_at.desc())
    ).all()
    return [
        ActiveSessionPublic(
            id=r.id,
            user_id=r.user_id,
            user_name=r.user.name if r.user else str(r.user_id),
            user_role=r.user.role.value if r.user else "unknown",
            created_at=r.created_at,
            expires_at=r.expires_at,
        )
        for r in rows
    ]


@router.post("/admin/sessions/revoke", response_model=SessionRevokeResult)
def revoke_user_sessions(
    body: SessionRevokeRequest,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> SessionRevokeResult:
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    ensure_same_org(admin, user.organization_id, detail="User not found")
    rows = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        row.revoked_at = now
    log_action(
        db,
        action="sessions.revoked",
        actor_id=admin.id,
        entity_type="user",
        entity_id=user.id,
        payload={"revoked": len(rows)},
        ip=_client_ip(request),
    )
    db.commit()
    return SessionRevokeResult(revoked=len(rows))


@router.post("/admin/users/{user_id}/unlock", response_model=UnlockResult)
def unlock_user(
    user_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
    request: Request,
) -> UnlockResult:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    ensure_same_org(admin, user.organization_id, detail="User not found")
    identifiers = [i for i in (user.email, user.username, user.name) if i]
    stmt = delete(AuditLog).where(
        AuditLog.action == "auth.login_failed",
        or_(*[AuditLog.payload["identifier"].as_string() == i for i in identifiers]),
    )
    result = db.execute(stmt)
    cleared = int(getattr(result, "rowcount", 0) or 0)
    log_action(
        db,
        action="user.unlocked",
        actor_id=admin.id,
        entity_type="user",
        entity_id=user.id,
        payload={"cleared": cleared},
        ip=_client_ip(request),
    )
    db.commit()
    return UnlockResult(cleared_failures=cleared)


# Nota: los permisos efectivos se exponen en GET /auth/permissions; el email
# real (ítem 17) queda fuera por diseño: todo es in-app (roadmap lo marca opcional).
