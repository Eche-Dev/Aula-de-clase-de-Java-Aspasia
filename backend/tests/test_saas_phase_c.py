"""Tests Fase C: aislamiento multi-tenant con DOS organizaciones + /superadmin/*.

La prueba principal crea las dos organizaciones con el FLUJO REAL de la Fase B
(registro público + webhook firmado + activación de ambas cuentas); el resto
usa organizaciones creadas directamente en BD (barato).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from stripe import WebhookSignature

from app.core.config import settings
from app.core.security import hash_secret
from app.models import (
    AuditLog,
    Course,
    CourseStatus,
    Organization,
    OrgStatus,
    RefreshToken,
    Submission,
    SubmissionStatus,
    User,
    UserRole,
)
from tests.api_helpers import (
    auth_headers,
    make_admin,
    make_course,
    make_student,
    make_super_admin,
)

WEBHOOK_SECRET = "whsec_phase_c_secret"
CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_phase_c"


@pytest.fixture(autouse=True)
def _billing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy_key")
    monkeypatch.setattr(settings, "stripe_price_starter", "price_starter_test")


class _Outbox:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    def send(self, email: Any) -> None:
        self.sent.append(email)


@pytest.fixture()
def outbox(monkeypatch: pytest.MonkeyPatch) -> _Outbox:
    box = _Outbox()
    monkeypatch.setattr("app.api.v1.routes.webhooks.get_email_service", lambda: box)
    return box


# ---- helpers ---------------------------------------------------------------


def _register_and_activate(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    outbox: _Outbox,
    *,
    name: str,
    tax_id: str,
    email: str,
) -> tuple[Organization, User, dict[str, str]]:
    """Alta real: registro público → webhook firmado → activación → login."""
    monkeypatch.setattr(
        "app.api.v1.routes.public.create_checkout_session",
        lambda org, plan: CHECKOUT_URL,
    )
    resp = client.post(
        "/api/v1/public/organizations",
        json={
            "name": name,
            "tax_id": tax_id,
            "billing_email": email,
            "plan_id": "starter",
        },
    )
    assert resp.status_code == 201, resp.text
    org_id = resp.json()["organization_id"]

    suffix = email.split("@")[0].replace("-", "_")
    event = {
        "id": f"evt_{email.replace('@', '_')}",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{suffix}",
                "customer": f"cus_{suffix}",
                "subscription": f"sub_{suffix}",
                "metadata": {"organization_id": str(org_id)},
            }
        },
    }
    payload = json.dumps(event)
    resp = client.post(
        "/api/v1/webhooks/stripe",
        content=payload.encode("utf-8"),
        headers={
            "Stripe-Signature": WebhookSignature.generate_signature_header(payload, WEBHOOK_SECRET)
        },
    )
    assert resp.status_code == 200, resp.text

    mail = outbox.sent[-1]
    match = re.search(r"/activar-cuenta/([A-Za-z0-9_\-]+)", mail.html)
    assert match is not None, "email de activación sin enlace"
    resp = client.post(
        "/api/v1/auth/activate",
        json={"token": match.group(1), "password": "fasec-secret-1"},
    )
    assert resp.status_code == 200, resp.text

    login = client.post(
        "/api/v1/auth/login/staff",
        json={"email": email, "password": "fasec-secret-1"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    org = db.get(Organization, org_id)
    assert org is not None
    admin = db.scalar(select(User).where(User.email == email))
    assert admin is not None
    return org, admin, headers


def _org_b(db: Session, *, email: str = "orgb@x.io") -> tuple[Organization, User]:
    org = Organization(
        name="Org B",
        tax_id="B87654321",
        billing_email=email,
        status=OrgStatus.active,
        plan_id="starter",
    )
    db.add(org)
    db.flush()
    admin = User(
        name="Admin B",
        email=email,
        role=UserRole.org_admin,
        organization_id=org.id,
        password_hash=hash_secret("adminb-secret-1"),
        is_active=True,
        must_change_credentials=False,
    )
    db.add(admin)
    db.commit()
    db.refresh(org)
    db.refresh(admin)
    return org, admin


def _user_in(
    db: Session,
    org: Organization,
    role: UserRole,
    *,
    name: str,
    email: str | None = None,
    username: str | None = None,
) -> User:
    fields: dict[str, Any] = {
        "name": name,
        "role": role,
        "organization_id": org.id,
        "is_active": True,
        "must_change_credentials": False,
    }
    if role is UserRole.student:
        fields["username"] = username
        fields["pin_hash"] = hash_secret("123456")
    else:
        fields["email"] = email
        fields["password_hash"] = hash_secret("clave-secret-1")
    user = User(**fields)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _course_in(db: Session, org: Organization, *, code: str) -> Course:
    course = Course(
        name=f"Curso {code}",
        code=code,
        description="Para pruebas de aislamiento",
        status=CourseStatus.active,
        layout_rows=2,
        layout_cols=2,
        organization_id=org.id,
        settings={},
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _submission_in(db: Session, course: Course, student: User) -> Submission:
    sub = Submission(
        course_id=course.id,
        student_id=student.id,
        status=SubmissionStatus.submitted,
        submitted_at=datetime.now(UTC),
        github_url="https://github.com/aula/entrega",
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


# ---- 1. Aislamiento con el flujo real de la Fase B -------------------------


def test_cross_org_isolation_via_real_registration_flow(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    outbox: _Outbox,
) -> None:
    org_a, admin_a, h_a = _register_and_activate(
        client,
        db,
        monkeypatch,
        outbox,
        name="Flux A",
        tax_id="B11111111",
        email="flow-a@x.io",
    )
    org_b, admin_b, h_b = _register_and_activate(
        client,
        db,
        monkeypatch,
        outbox,
        name="Flux B",
        tax_id="B22222222",
        email="flow-b@x.io",
    )
    assert org_a.id != org_b.id

    student_b = _user_in(db, org_b, UserRole.student, name="Begoña", username="begona")
    course_b = _course_in(db, org_b, code="FLWB")
    student_a = _user_in(db, org_a, UserRole.student, name="Alba", username="alba")
    course_a = _course_in(db, org_a, code="FLWA")

    # GET /admin/users de A: sin rastro de usuarios de B
    users_a = client.get("/api/v1/admin/users", headers=h_a).json()
    ids_a = {u["id"] for u in users_a}
    assert admin_a.id in ids_a
    assert student_a.id in ids_a
    assert admin_b.id not in ids_a
    assert student_b.id not in ids_a

    # Modificar usuario de B → 404 (nunca 403: no se revela su existencia)
    resp = client.patch(f"/api/v1/admin/users/{admin_b.id}", json={"name": "Hack"}, headers=h_a)
    assert resp.status_code == 404
    resp = client.patch(
        f"/api/v1/admin/users/{student_b.id}",
        json={"is_active": False},
        headers=h_a,
    )
    assert resp.status_code == 404

    # GET /courses de A: sin cursos de B; leer curso de B → 404
    courses_a = client.get("/api/v1/courses", headers=h_a).json()
    course_ids_a = {c["id"] for c in courses_a}
    assert course_a.id in course_ids_a
    assert course_b.id not in course_ids_a
    assert client.get(f"/api/v1/courses/{course_b.id}", headers=h_a).status_code == 404

    # Audit log: B genera traza propia; el listado de A la excluye
    r = client.post(
        "/api/v1/admin/categories",
        json={"name": "Cat A", "slug": "cat-a"},
        headers=h_a,
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/admin/categories",
        json={"name": "Cat B", "slug": "cat-b"},
        headers=h_b,
    )
    assert r.status_code == 201, r.text
    logs_a = client.get("/api/v1/admin/audit-logs", headers=h_a).json()
    actors_a = {row["actor_id"] for row in logs_a}
    assert admin_b.id not in actors_a
    assert admin_a.id in actors_a
    # ...pero la traza de B existe en BD (no se borra, solo no se lista)
    assert (
        db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.actor_id == admin_b.id))
        or 0
    ) >= 1

    # Contraste: B también está aislado respecto a A
    users_b = client.get("/api/v1/admin/users", headers=h_b).json()
    assert admin_a.id not in {u["id"] for u in users_b}
    courses_b = client.get("/api/v1/courses", headers=h_b).json()
    assert course_a.id not in {c["id"] for c in courses_b}


# ---- 2. Listado de usuarios ------------------------------------------------


def test_org_admin_users_list_scoped_to_own_org(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    org_b, admin_b = _org_b(db)
    student_b = _user_in(db, org_b, UserRole.student, name="Begoña", username="begona")

    resp = client.get("/api/v1/admin/users", headers=auth_headers(admin_a))
    assert resp.status_code == 200
    ids = {u["id"] for u in resp.json()}
    assert admin_a.id in ids
    assert admin_b.id not in ids
    assert student_b.id not in ids


# ---- 3. Mutaciones de usuario ajenas → 404 --------------------------------


def test_org_admin_cannot_modify_user_of_other_org(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    org_b, admin_b = _org_b(db)
    student_b = _user_in(db, org_b, UserRole.student, name="Begoña", username="begona")
    h = auth_headers(admin_a)

    assert (
        client.patch(
            f"/api/v1/admin/users/{admin_b.id}", json={"name": "Hack"}, headers=h
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/admin/users/{admin_b.id}/status",
            json={"is_active": False},
            headers=h,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/admin/users/{admin_b.id}/reset-password", json={}, headers=h
        ).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/admin/users/{student_b.id}/reset-pin", json={}, headers=h).status_code
        == 404
    )
    assert client.post(f"/api/v1/admin/users/{admin_b.id}/unlock", headers=h).status_code == 404
    assert (
        client.post(
            f"/api/v1/admin/users/{admin_b.id}/custom-role",
            json={"custom_role_id": None},
            headers=h,
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/admin/users/{admin_b.id}/data", headers=h).status_code == 404
    # y el usuario de B sigue intacto
    db.refresh(admin_b)
    assert admin_b.is_active is True
    assert admin_b.name == "Admin B"


# ---- 4. Audit logs ---------------------------------------------------------


def test_org_admin_audit_logs_scoped_to_own_org(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    _org, admin_b = _org_b(db)

    r = client.post(
        "/api/v1/admin/categories",
        json={"name": "Una", "slug": "una"},
        headers=auth_headers(admin_a),
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/admin/categories",
        json={"name": "Otra", "slug": "otra"},
        headers=auth_headers(admin_b),
    )
    assert r.status_code == 201, r.text
    # B tiene traza real en BD
    assert (
        db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.actor_id == admin_b.id))
        or 0
    ) >= 1

    logs = client.get("/api/v1/admin/audit-logs", headers=auth_headers(admin_a))
    assert logs.status_code == 200
    rows = logs.json()
    assert len(rows) >= 1
    assert all(row["actor_id"] == admin_a.id for row in rows)
    assert admin_b.id not in {row["actor_id"] for row in rows}


# ---- 5. Dashboard / observador / reportes ---------------------------------


def test_org_admin_dashboard_observer_and_reports_scoped(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    org_b, _admin_b = _org_b(db)
    course_a = make_course(db, code="DASHA")
    course_b = _course_in(db, org_b, code="DASHB")
    student_a = make_student(db, name="Alba", username="alba")
    student_b = _user_in(db, org_b, UserRole.student, name="Begoña", username="begona")
    sub_a = _submission_in(db, course_a, student_a)
    sub_b = _submission_in(db, course_b, student_b)
    h = auth_headers(admin_a)

    # KPIs: 1 curso (el de B no cuenta)
    dash = client.get("/api/v1/admin/dashboard", headers=h)
    assert dash.status_code == 200
    assert dash.json()["courses_total"] == 1

    # Dashboard multi-curso: solo filas de la propia org
    multi = client.get("/api/v1/admin/dashboard/multi", headers=h).json()
    row_ids = {row["course_id"] for row in multi["courses"]}
    assert course_a.id in row_ids
    assert course_b.id not in row_ids

    # Observador: entregas solo de la propia org
    obs = client.get("/api/v1/admin/observer/submissions", headers=h).json()
    obs_ids = {item["id"] for item in obs["items"]}
    assert sub_a.id in obs_ids
    assert sub_b.id not in obs_ids

    # Reportes: filas de cursos solo de la propia org
    rep = client.get("/api/v1/admin/reports/overview", headers=h).json()
    rep_ids = {row["course_id"] for row in rep["courses"]}
    assert rep_ids == {course_a.id}
    assert course_b.id not in rep_ids


# ---- 6. Cursos de otra organización → 404 en todo -------------------------


def test_org_admin_cannot_touch_other_org_courses(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    org_b, _admin_b = _org_b(db)
    course_b = _course_in(db, org_b, code="TOUB")
    h = auth_headers(admin_a)

    assert client.get(f"/api/v1/courses/{course_b.id}", headers=h).status_code == 404
    assert client.patch(f"/api/v1/courses/{course_b.id}", json={}, headers=h).status_code == 404
    assert (
        client.post(
            f"/api/v1/courses/{course_b.id}/clone",
            json={"name": "Clon", "code": "CLONB"},
            headers=h,
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/courses/{course_b.id}/backup", headers=h).status_code == 404
    assert client.get(f"/api/v1/courses/{course_b.id}/gradebook", headers=h).status_code == 404
    assert client.get(f"/api/v1/admin/metrics/course/{course_b.id}", headers=h).status_code == 404
    assert (
        client.post(
            f"/api/v1/admin/courses/{course_b.id}/import-students",
            json={"csv_text": "Alumno Nuevo"},
            headers=h,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/admin/courses/{course_b.id}/taxonomy", json={}, headers=h
        ).status_code
        == 404
    )
    assert client.post(f"/api/v1/courses/{course_b.id}/auto-enroll", headers=h).status_code == 404
    assert client.get(f"/api/v1/courses/{course_b.id}/enrollments", headers=h).status_code == 404
    org_a = db.get(Organization, admin_a.organization_id)
    assert org_a is not None
    teacher_a = _user_in(db, org_a, UserRole.teacher, name="Profe A", email="profea@aula.test")
    assert (
        client.post(f"/api/v1/courses/{course_b.id}/teachers/{teacher_a.id}", headers=h).status_code
        == 404
    )

    # Listado: sin cursos ajenos
    ids = {c["id"] for c in client.get("/api/v1/courses", headers=h).json()}
    assert course_b.id not in ids


# ---- 7. Unicidades por organización ---------------------------------------


def test_course_code_and_catalogs_unique_per_org(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    _org, admin_b = _org_b(db)
    ha, hb = auth_headers(admin_a), auth_headers(admin_b)

    # courses.code: mismo código en dos orgs → 201 y 201; repetido en una → 409
    r = client.post("/api/v1/courses", json={"name": "Java A", "code": "SAME1"}, headers=ha)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/courses", json={"name": "Java B", "code": "SAME1"}, headers=hb)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/courses", json={"name": "Java A2", "code": "SAME1"}, headers=ha)
    assert r.status_code == 409

    # categorías.slug
    r = client.post(
        "/api/v1/admin/categories",
        json={"name": "Mismo slug", "slug": "mismo-slug"},
        headers=ha,
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/admin/categories",
        json={"name": "Mismo slug B", "slug": "mismo-slug"},
        headers=hb,
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/v1/admin/categories",
        json={"name": "Mismo slug A2", "slug": "mismo-slug"},
        headers=ha,
    )
    assert r.status_code == 409

    # cohorts.code
    r = client.post("/api/v1/admin/cohorts", json={"name": "Coh A", "code": "COH1"}, headers=ha)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/admin/cohorts", json={"name": "Coh B", "code": "COH1"}, headers=hb)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/admin/cohorts", json={"name": "Coh A2", "code": "COH1"}, headers=ha)
    assert r.status_code == 409

    # custom_roles.name
    r = client.post("/api/v1/admin/roles", json={"name": "Editor", "permissions": []}, headers=ha)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/admin/roles", json={"name": "Editor", "permissions": []}, headers=hb)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/admin/roles", json={"name": "Editor", "permissions": []}, headers=ha)
    assert r.status_code == 409

    # y los listados son por org (cada admin ve SU Editor)
    roles_a = client.get("/api/v1/admin/roles", headers=ha).json()
    roles_b = client.get("/api/v1/admin/roles", headers=hb).json()
    assert [r_["name"] for r_ in roles_a] == ["Editor"]
    assert [r_["name"] for r_ in roles_b] == ["Editor"]
    assert roles_a[0]["id"] != roles_b[0]["id"]


# ---- 8. Matricular/asignar gente de otra org → 404 ------------------------


def test_cross_org_student_and_teacher_assignment_blocked(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    org_b, _admin_b = _org_b(db)
    course_a = make_course(db, code="ASSGA")
    student_b = _user_in(db, org_b, UserRole.student, name="Begoña", username="begona")
    teacher_b = _user_in(db, org_b, UserRole.teacher, name="Profe B", email="profeb@orgb.test")
    h = auth_headers(admin_a)

    # matricular alumno de B en curso de A → 404
    resp = client.post(
        f"/api/v1/courses/{course_a.id}/enrollments",
        json={"student_id": student_b.id},
        headers=h,
    )
    assert resp.status_code == 404

    # asignar profesor de B → 404
    resp = client.post(f"/api/v1/courses/{course_a.id}/teachers/{teacher_b.id}", headers=h)
    assert resp.status_code == 404

    # miembro de cohorte de A → 404
    resp = client.post(
        "/api/v1/admin/cohorts",
        json={"name": "Coh A", "code": "MEMBA"},
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    cohort_id = resp.json()["id"]
    resp = client.post(
        f"/api/v1/admin/cohorts/{cohort_id}/members",
        json={"student_id": student_b.id},
        headers=h,
    )
    assert resp.status_code == 404


# ---- 9. Ajustes del centro aislados ---------------------------------------


def test_settings_isolated_between_orgs(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    _org, admin_b = _org_b(db)

    resp = client.put(
        "/api/v1/admin/settings",
        json={"center_name": "Centro A", "pin_length": 8},
        headers=auth_headers(admin_a),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["center_name"] == "Centro A"

    settings_a = client.get("/api/v1/admin/settings", headers=auth_headers(admin_a)).json()
    settings_b = client.get("/api/v1/admin/settings", headers=auth_headers(admin_b)).json()
    assert settings_a["center_name"] == "Centro A"
    assert settings_a["pin_length"] == 8
    # la org B no heredó nada del PUT de A
    assert settings_b["center_name"] == "Aspasia"
    assert settings_b["pin_length"] == 6


# ---- 10. Sesiones ----------------------------------------------------------


def test_sessions_list_revoke_scoped(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    _org, admin_b = _org_b(db)
    now = datetime.now(UTC)
    token_a = RefreshToken(
        user_id=admin_a.id, token_hash="a" * 64, expires_at=now + timedelta(days=1)
    )
    token_b = RefreshToken(
        user_id=admin_b.id, token_hash="b" * 64, expires_at=now + timedelta(days=1)
    )
    db.add_all([token_a, token_b])
    db.commit()

    h = auth_headers(admin_a)
    rows = client.get("/api/v1/admin/sessions", headers=h).json()
    user_ids = {row["user_id"] for row in rows}
    assert admin_a.id in user_ids
    assert admin_b.id not in user_ids

    # revocar sesiones de un usuario de B → 404 y sus tokens siguen vivos
    resp = client.post("/api/v1/admin/sessions/revoke", json={"user_id": admin_b.id}, headers=h)
    assert resp.status_code == 404
    db.refresh(token_b)
    assert token_b.revoked_at is None


# ---- 11. Contenido académico de otra org ----------------------------------


def test_org_admin_cannot_read_academic_content_of_other_org(
    client: TestClient, db: Session
) -> None:
    admin_a = make_admin(db)
    org_b, _admin_b = _org_b(db)
    course_b = _course_in(db, org_b, code="ACADB")
    student_b = _user_in(db, org_b, UserRole.student, name="Begoña", username="begona")
    sub_b = _submission_in(db, course_b, student_b)
    h = auth_headers(admin_a)

    assert client.get(f"/api/v1/submissions/{sub_b.id}", headers=h).status_code == 404
    assert client.get(f"/api/v1/submissions/{sub_b.id}/github-meta", headers=h).status_code == 404
    assert (
        client.post(
            f"/api/v1/courses/{course_b.id}/chat",
            json={"body": "hola desde otra org"},
            headers=h,
        ).status_code
        == 404
    )
    # la entrega sigue existiendo (no se borró nada)
    assert db.get(Submission, sub_b.id) is not None


# ---- 12. Super admin: CRUD de organizaciones ------------------------------


def test_super_admin_organization_crud(client: TestClient, db: Session) -> None:
    sa = make_super_admin(db)
    hs = auth_headers(sa)

    resp = client.post(
        "/api/v1/superadmin/organizations",
        json={
            "name": "Enterprise Uno",
            "tax_id": "B00000001",
            "billing_email": "ent1@x.io",
            "plan_id": "enterprise",
            "status": "active",
        },
        headers=hs,
    )
    assert resp.status_code == 201, resp.text
    org_id = resp.json()["id"]
    assert resp.json()["user_count"] == 0

    # email duplicado → 409
    dup = client.post(
        "/api/v1/superadmin/organizations",
        json={
            "name": "Enterprise Dup",
            "tax_id": "B00000002",
            "billing_email": "ent1@x.io",
            "plan_id": "enterprise",
        },
        headers=hs,
    )
    assert dup.status_code == 409

    # listar y detalle
    listing = client.get("/api/v1/superadmin/organizations", headers=hs)
    assert listing.status_code == 200
    assert any(o["id"] == org_id for o in listing.json())
    detail = client.get(f"/api/v1/superadmin/organizations/{org_id}", headers=hs)
    assert detail.status_code == 200
    assert detail.json()["name"] == "Enterprise Uno"

    # patch
    patched = client.patch(
        f"/api/v1/superadmin/organizations/{org_id}",
        json={"name": "Enterprise Uno SL", "status": "past_due"},
        headers=hs,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Enterprise Uno SL"
    assert patched.json()["status"] == "past_due"

    # inexistente → 404
    assert client.get("/api/v1/superadmin/organizations/999999", headers=hs).status_code == 404

    # org con usuarios → 409
    resp = client.post(
        "/api/v1/superadmin/organizations",
        json={
            "name": "Con Gente",
            "tax_id": "B00000003",
            "billing_email": "congente@x.io",
            "plan_id": "enterprise",
        },
        headers=hs,
    )
    assert resp.status_code == 201, resp.text
    full_org_id = resp.json()["id"]
    _user_in(
        db,
        db.get(Organization, full_org_id),
        UserRole.org_admin,
        name="Admin Congente",
        email="admin@congente.x.io",
    )
    resp = client.delete(f"/api/v1/superadmin/organizations/{full_org_id}", headers=hs)
    assert resp.status_code == 409
    assert db.get(Organization, full_org_id) is not None

    # org vacía → 204 y desaparece
    resp = client.delete(f"/api/v1/superadmin/organizations/{org_id}", headers=hs)
    assert resp.status_code == 204, resp.text
    assert db.get(Organization, org_id) is None


# ---- 13. Suscripciones y métricas sin datos académicos --------------------


def test_super_admin_subscriptions_and_metrics_no_academic_data(
    client: TestClient, db: Session
) -> None:
    sa = make_super_admin(db)
    admin_a = make_admin(db)
    org_b, _admin_b = _org_b(db)
    hs = auth_headers(sa)

    subs = client.get("/api/v1/superadmin/subscriptions", headers=hs)
    assert subs.status_code == 200
    rows = subs.json()
    org_ids = {row["organization_id"] for row in rows}
    assert admin_a.organization_id in org_ids
    assert org_b.id in org_ids
    row_b = next(r for r in rows if r["organization_id"] == org_b.id)
    assert row_b["status"] == OrgStatus.active.value
    assert row_b["organization_name"] == "Org B"

    metrics = client.get("/api/v1/superadmin/metrics", headers=hs)
    assert metrics.status_code == 200
    m = metrics.json()
    assert set(m) == {
        "orgs_by_status",
        "orgs_by_plan",
        "users_by_role",
        "total_courses",
        "trials_ending_soon",
    }
    # agregados coherentes con la BD
    org_total = db.scalar(select(func.count()).select_from(Organization)) or 0
    user_total = db.scalar(select(func.count()).select_from(User)) or 0
    course_total = db.scalar(select(func.count()).select_from(Course)) or 0
    assert sum(m["orgs_by_status"].values()) == org_total
    assert sum(m["users_by_role"].values()) == user_total
    assert m["total_courses"] == course_total
    assert m["trials_ending_soon"] == 0

    # sin claves de datos académicos (compromiso de producto)
    forbidden = {
        "submissions",
        "evaluations",
        "messages",
        "course_messages",
        "student_id",
        "student_name",
        "submission_id",
        "gradebook",
    }
    assert forbidden.isdisjoint(m.keys())
    for value in m.values():
        if isinstance(value, dict):
            assert forbidden.isdisjoint(value.keys())

    # trial que termina mañana → contado
    org = db.get(Organization, org_b.id)
    org.trial_ends_at = datetime.now(UTC) + timedelta(days=1)
    db.commit()
    m2 = client.get("/api/v1/superadmin/metrics", headers=hs).json()
    assert m2["trials_ending_soon"] == 1


# ---- 14. Fronteras de rol --------------------------------------------------


def test_super_admin_role_boundaries(client: TestClient, db: Session) -> None:
    admin_a = make_admin(db)
    sa = make_super_admin(db)
    ha, hs = auth_headers(admin_a), auth_headers(sa)

    # org_admin → 403 en todas las rutas /superadmin/*
    get_cases = [
        "/api/v1/superadmin/organizations",
        "/api/v1/superadmin/organizations/1",
        "/api/v1/superadmin/subscriptions",
        "/api/v1/superadmin/metrics",
    ]
    for path in get_cases:
        assert client.get(path, headers=ha).status_code == 403, path
    assert (
        client.post(
            "/api/v1/superadmin/organizations",
            json={
                "name": "X",
                "tax_id": "B00000009",
                "billing_email": "nope@x.io",
            },
            headers=ha,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/api/v1/superadmin/organizations/1", json={"name": "X"}, headers=ha
        ).status_code
        == 403
    )
    assert client.delete("/api/v1/superadmin/organizations/1", headers=ha).status_code == 403

    # super_admin → 403 en las rutas /admin/* (sin datos académicos, Fase A)
    admin_cases = [
        "/api/v1/admin/users",
        "/api/v1/admin/dashboard",
        "/api/v1/admin/settings",
        "/api/v1/admin/audit-logs",
        "/api/v1/admin/observer/submissions",
        "/api/v1/admin/sessions",
    ]
    for path in admin_cases:
        assert client.get(path, headers=hs).status_code == 403, path
    assert (
        client.post(
            "/api/v1/admin/categories",
            json={"name": "No", "slug": "no"},
            headers=hs,
        ).status_code
        == 403
    )
