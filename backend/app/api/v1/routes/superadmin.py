"""Rutas exclusivas de la dueña de la plataforma (Fase C): /superadmin/*.

Sin datos académicos de alumnos (compromiso de producto): solo organizaciones,
suscripciones y agregados de plataforma.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Cohort,
    Course,
    CourseCategory,
    CustomRole,
    Organization,
    OrgStatus,
    SystemSetting,
    User,
)
from app.schemas.superadmin import (
    OrganizationAdminPublic,
    OrganizationCreate,
    OrganizationUpdate,
    PlatformMetrics,
    SubscriptionRow,
)
from app.security.policies import DbSession, require_super_admin
from app.services.audit import log_action

router = APIRouter(tags=["superadmin"])

SuperAdmin = Annotated[User, Depends(require_super_admin)]


def _org(db: Session, org_id: int) -> Organization:
    row = db.get(Organization, org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return row


def _counts(db: Session, org_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    users: dict[int, int] = {}
    courses: dict[int, int] = {}
    if org_ids:
        for org_id, n in db.execute(
            select(User.organization_id, func.count())
            .where(User.organization_id.in_(org_ids))
            .group_by(User.organization_id)
        ).all():
            if org_id is not None:
                users[int(org_id)] = int(n)
        for org_id, n in db.execute(
            select(Course.organization_id, func.count())
            .where(Course.organization_id.in_(org_ids))
            .group_by(Course.organization_id)
        ).all():
            if org_id is not None:
                courses[int(org_id)] = int(n)
    return users, courses


def _public(db: Session, row: Organization) -> OrganizationAdminPublic:
    item = OrganizationAdminPublic.model_validate(row)
    users, courses = _counts(db, [row.id])
    item.user_count = users.get(row.id, 0)
    item.course_count = courses.get(row.id, 0)
    return item


@router.get("/superadmin/organizations", response_model=list[OrganizationAdminPublic])
def list_organizations(
    db: DbSession,
    _sa: SuperAdmin,
    status: Annotated[OrgStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[OrganizationAdminPublic]:
    stmt = select(Organization)
    if status is not None:
        stmt = stmt.where(Organization.status == status)
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{q}%"))
    rows = db.scalars(stmt.order_by(Organization.id)).all()
    users, courses = _counts(db, [r.id for r in rows])
    out: list[OrganizationAdminPublic] = []
    for row in rows:
        item = OrganizationAdminPublic.model_validate(row)
        item.user_count = users.get(row.id, 0)
        item.course_count = courses.get(row.id, 0)
        out.append(item)
    return out


@router.get("/superadmin/organizations/{org_id}", response_model=OrganizationAdminPublic)
def get_organization(org_id: int, db: DbSession, _sa: SuperAdmin) -> OrganizationAdminPublic:
    return _public(db, _org(db, org_id))


@router.post("/superadmin/organizations", response_model=OrganizationAdminPublic, status_code=201)
def create_organization(
    body: OrganizationCreate,
    db: DbSession,
    _sa: SuperAdmin,
) -> OrganizationAdminPublic:
    if db.scalar(select(Organization).where(Organization.billing_email == body.billing_email)):
        raise HTTPException(status_code=409, detail="Billing email already exists")
    row = Organization(**body.model_dump())
    db.add(row)
    log_action(
        db,
        action="organization.created",
        actor_id=_sa.id,
        entity_type="organization",
        payload={"name": row.name, "status": row.status.value},
    )
    db.commit()
    db.refresh(row)
    return _public(db, row)


@router.patch("/superadmin/organizations/{org_id}", response_model=OrganizationAdminPublic)
def update_organization(
    org_id: int,
    body: OrganizationUpdate,
    db: DbSession,
    _sa: SuperAdmin,
) -> OrganizationAdminPublic:
    row = _org(db, org_id)
    data = body.model_dump(exclude_unset=True)
    email = data.get("billing_email")
    if email is not None and db.scalar(
        select(Organization).where(Organization.billing_email == email, Organization.id != row.id)
    ):
        raise HTTPException(status_code=409, detail="Billing email already exists")
    for key, value in data.items():
        setattr(row, key, value)
    log_action(
        db,
        action="organization.updated",
        actor_id=_sa.id,
        entity_type="organization",
        entity_id=row.id,
        payload={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(row)
    return _public(db, row)


@router.delete("/superadmin/organizations/{org_id}", status_code=204)
def delete_organization(
    org_id: int,
    db: DbSession,
    _sa: SuperAdmin,
) -> None:
    row = _org(db, org_id)
    user_count = db.scalar(
        select(func.count()).select_from(User).where(User.organization_id == row.id)
    )
    course_count = db.scalar(
        select(func.count()).select_from(Course).where(Course.organization_id == row.id)
    )
    if (user_count or 0) > 0 or (course_count or 0) > 0:
        raise HTTPException(status_code=409, detail="Organization has users or courses")
    # Org vacía a nivel de usuarios/cursos: limpia también sus filas propias
    # (settings, catálogos) para poder borrar la fila sin violar FKs.
    db.execute(delete(SystemSetting).where(SystemSetting.organization_id == row.id))
    db.execute(delete(Cohort).where(Cohort.organization_id == row.id))
    db.execute(delete(CourseCategory).where(CourseCategory.organization_id == row.id))
    db.execute(delete(CustomRole).where(CustomRole.organization_id == row.id))
    db.delete(row)
    log_action(
        db,
        action="organization.deleted",
        actor_id=_sa.id,
        entity_type="organization",
        entity_id=org_id,
        payload={"name": row.name},
    )
    db.commit()


@router.get("/superadmin/subscriptions", response_model=list[SubscriptionRow])
def list_subscriptions(
    db: DbSession,
    _sa: SuperAdmin,
) -> list[SubscriptionRow]:
    rows = db.scalars(select(Organization).order_by(Organization.id)).all()
    return [
        SubscriptionRow(
            organization_id=row.id,
            organization_name=row.name,
            stripe_customer_id=row.stripe_customer_id,
            stripe_subscription_id=row.stripe_subscription_id,
            status=row.status,
            plan_id=row.plan_id,
            trial_ends_at=row.trial_ends_at,
        )
        for row in rows
    ]


@router.get("/superadmin/metrics", response_model=PlatformMetrics)
def platform_metrics(
    db: DbSession,
    _sa: SuperAdmin,
) -> PlatformMetrics:
    orgs_by_status = {
        str(status): int(n)
        for status, n in db.execute(
            select(Organization.status, func.count()).group_by(Organization.status)
        ).all()
    }
    orgs_by_plan = {
        str(plan): int(n)
        for plan, n in db.execute(
            select(Organization.plan_id, func.count()).group_by(Organization.plan_id)
        ).all()
    }
    users_by_role = {
        str(role): int(n)
        for role, n in db.execute(select(User.role, func.count()).group_by(User.role)).all()
    }
    total_courses = int(db.scalar(select(func.count()).select_from(Course)) or 0)
    now = datetime.now(UTC)
    soon = now + timedelta(days=7)
    trials_ending_soon = int(
        db.scalar(
            select(func.count())
            .select_from(Organization)
            .where(
                Organization.trial_ends_at.is_not(None),
                Organization.trial_ends_at >= now,
                Organization.trial_ends_at <= soon,
            )
        )
        or 0
    )
    return PlatformMetrics(
        orgs_by_status=orgs_by_status,
        orgs_by_plan=orgs_by_plan,
        users_by_role=users_by_role,
        total_courses=total_courses,
        trials_ending_soon=trials_ending_soon,
    )
