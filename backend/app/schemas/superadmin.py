"""Esquemas del panel de la dueña de la plataforma (Fase C, /superadmin/*)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.organization import OrgStatus
from app.schemas.auth import EmailLike


class OrganizationAdminPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tax_id: str
    billing_email: str
    status: OrgStatus
    plan_id: str
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    trial_ends_at: datetime | None = None
    created_at: datetime
    user_count: int = 0
    course_count: int = 0


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tax_id: str = Field(min_length=1, max_length=32)
    billing_email: EmailLike
    plan_id: str = Field(default="", max_length=64)
    status: OrgStatus = OrgStatus.active


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, min_length=1, max_length=32)
    billing_email: EmailLike | None = None
    plan_id: str | None = Field(default=None, max_length=64)
    status: OrgStatus | None = None


class SubscriptionRow(BaseModel):
    organization_id: int
    organization_name: str
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    status: OrgStatus
    plan_id: str
    trial_ends_at: datetime | None = None


class PlatformMetrics(BaseModel):
    """Agregados de plataforma SIN datos académicos de alumnos."""

    orgs_by_status: dict[str, int]
    orgs_by_plan: dict[str, int]
    users_by_role: dict[str, int]
    total_courses: int
    trials_ending_soon: int
