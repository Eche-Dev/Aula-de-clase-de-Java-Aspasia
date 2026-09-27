"""Tests Fase A SaaS: migración multi-tenant, roles nuevos y CLI super_admin."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Assignment, Course, Organization, Submission, User, UserRole
from app.security.policies import can_read_submission, user_permissions
from app.services.organization import get_or_create_default_organization
from tests.api_helpers import (
    assign_teacher,
    auth_headers,
    enroll,
    make_admin,
    make_course,
    make_org,
    make_student,
    make_super_admin,
    make_teacher,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
# Cabecera actual de Alembic: la Fase B añadió su migración encima de la de la Fase A
MIGRATION_HEAD = "d8e9f0a1b2c3"
LEGACY_REVISION = "d9a4b5c6e7f8"


def _run_alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    proc = subprocess.run(  # noqa: S603 - comando fijo del proyecto, sin input externo
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, f"alembic {' '.join(args)} failed:\n{proc.stdout}\n{proc.stderr}"


def _insert_legacy_data(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (name, email, role, is_active, must_change_credentials) "
            "VALUES ('Legacy Admin', 'legacy-admin@x.io', 'admin', 1, 0)"
        )
        conn.execute(
            "INSERT INTO users (name, email, role, is_active, must_change_credentials) "
            "VALUES ('Legacy Profe', 'legacy-profe@x.io', 'teacher', 1, 0)"
        )
        conn.execute(
            "INSERT INTO users (name, username, role, is_active, must_change_credentials) "
            "VALUES ('Legacy Alumna', 'legacyalumna', 'student', 1, 0)"
        )
        conn.execute(
            "INSERT INTO courses (name, code, status, layout_rows, layout_cols) "
            "VALUES ('Legacy Java', 'LEGACY1', 'active', 3, 5)"
        )
        conn.commit()
    finally:
        conn.close()


def test_migration_backfill_and_downgrade(tmp_path: Path) -> None:
    """Fase A: admin->org_admin + backfill de organización; downgrade reversible."""
    db_path = tmp_path / "phase_a.db"
    _run_alembic(db_path, "upgrade", LEGACY_REVISION)
    _insert_legacy_data(db_path)

    _run_alembic(db_path, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version == MIGRATION_HEAD

        orgs = conn.execute(
            "SELECT id, name, tax_id, billing_email, status, plan_id FROM organizations"
        ).fetchall()
        assert len(orgs) == 1
        org_id, org_name, tax_id, billing, status, plan_id = orgs[0]
        assert org_name == "Organización por defecto"
        assert tax_id == "000000000A"
        assert billing == "legacy-admin@x.io"  # primer admin original
        assert status == "active"
        assert plan_id == ""

        users = dict(
            conn.execute("SELECT email, role FROM users WHERE email IS NOT NULL").fetchall()
        )
        assert users["legacy-admin@x.io"] == "org_admin"
        assert users["legacy-profe@x.io"] == "teacher"
        student_role = conn.execute(
            "SELECT role FROM users WHERE username = 'legacyalumna'"
        ).fetchone()[0]
        assert student_role == "student"

        org_ids = dict(conn.execute("SELECT email, organization_id FROM users").fetchall())
        assert all(oid == org_id for oid in org_ids.values())

        course_org = conn.execute("SELECT organization_id FROM courses").fetchone()[0]
        assert course_org == org_id

        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0]
        assert "ck_users_org_by_role" in ddl
        assert "REFERENCES organizations" in ddl
        course_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='courses'").fetchone()[
            0
        ]
        assert "REFERENCES organizations" in course_ddl
        assert "ix_courses_organization_id" in {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    finally:
        conn.close()

    _run_alembic(db_path, "downgrade", LEGACY_REVISION)

    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "organizations" not in tables
        roles = {r[0] for r in conn.execute("SELECT role FROM users")}
        assert roles == {"admin", "teacher", "student"}
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0]
        assert "organization_id" not in ddl
        assert "ck_users_org_by_role" not in ddl
        course_ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='courses'").fetchone()[
            0
        ]
        assert "organization_id" not in course_ddl
    finally:
        conn.close()


def test_check_constraint_rejects_invalid_role_org_pairs(db: Session) -> None:
    org = make_org(db)

    # super_admin no puede pertenecer a una organización
    db.add(
        User(
            name="Root Con Org",
            role=UserRole.super_admin,
            organization_id=org.id,
            is_active=True,
            must_change_credentials=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # cualquier otro rol debe tener organización
    db.add(
        User(
            name="Admin Sin Org",
            role=UserRole.org_admin,
            organization_id=None,
            is_active=True,
            must_change_credentials=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # y el rol legacy 'admin' ya no es válido
    db.add(
        User(
            name="Legacy",
            role="admin",  # type: ignore[arg-type]
            organization_id=org.id,
            is_active=True,
            must_change_credentials=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_cli_create_org_admin_and_super_admin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'cli.db').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("scripts.create_admin.SessionLocal", TestingSession)

    from scripts.create_admin import create_admin

    org_admin = create_admin("cli-admin@x.io", "secret1234")
    assert org_admin is not None
    assert org_admin.role is UserRole.org_admin
    assert org_admin.organization_id is not None

    super_admin = create_admin("cli-root@x.io", "secret1234", role=UserRole.super_admin)
    assert super_admin is not None
    assert super_admin.role is UserRole.super_admin
    assert super_admin.organization_id is None

    # idempotencia: no duplica
    again = create_admin("cli-root@x.io", "secret1234", role=UserRole.super_admin)
    assert again is not None and again.id == super_admin.id

    # la org por defecto hereda el email del primer admin creado
    session = TestingSession()
    try:
        billing = session.scalar(select(Organization.billing_email))
        assert billing == "cli-admin@x.io"
        org_count = session.scalar(select(Organization.id))
        assert org_count is not None
    finally:
        session.close()
    engine.dispose()


def test_get_or_create_default_organization_is_idempotent(db: Session) -> None:
    first = get_or_create_default_organization(db, billing_email="a@x.io")
    db.commit()
    second = get_or_create_default_organization(db, billing_email="b@x.io")
    db.commit()
    assert first.id == second.id
    assert second.billing_email == "a@x.io"
    assert first.status == "active"


def test_super_admin_blocked_from_admin_api(client: TestClient, db: Session) -> None:
    root = make_super_admin(db)
    headers = auth_headers(root)
    for path in ("/api/v1/admin/dashboard", "/api/v1/admin/users"):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 403, f"{path}: {resp.status_code}"


def test_super_admin_cannot_be_created_or_promoted_via_api(client: TestClient, db: Session) -> None:
    admin = make_admin(db)
    teacher = make_teacher(db, email="promote@aula.test")

    created = client.post(
        "/api/v1/admin/users",
        json={"name": "Root", "role": "super_admin", "email": "root@x.io"},
        headers=auth_headers(admin),
    )
    assert created.status_code == 403

    promoted = client.patch(
        f"/api/v1/admin/users/{teacher.id}",
        json={"role": "super_admin"},
        headers=auth_headers(admin),
    )
    assert promoted.status_code == 403


def test_super_admin_has_no_academic_permissions(db: Session) -> None:
    root = make_super_admin(db)
    admin = make_admin(db)
    course = make_course(db, code="SAP1")
    teacher = make_teacher(db, email="sapp@aula.test")
    assign_teacher(db, course, teacher)
    student = make_student(db, username="sap1")
    enroll(db, course, student)

    assert user_permissions(root) == []
    assert len(user_permissions(admin)) > 0

    assignment = Assignment(
        course_id=course.id,
        title="T",
        description_markdown="",
        created_by=teacher.id,
    )
    db.add(assignment)
    db.flush()
    submission = Submission(
        assignment_id=assignment.id,
        course_id=course.id,
        student_id=student.id,
        notes="ok",
    )
    db.add(submission)
    db.commit()

    assert can_read_submission(db, root, submission) is False
    assert can_read_submission(db, teacher, submission) is True


def test_created_users_inherit_admin_organization(client: TestClient, db: Session) -> None:
    admin = make_admin(db)
    created = client.post(
        "/api/v1/admin/users",
        json={"name": "Profe Org", "role": "teacher", "email": "profe-org@aula.test"},
        headers=auth_headers(admin),
    )
    assert created.status_code == 201, created.text
    user = db.get(User, created.json()["id"])
    assert user is not None
    assert user.organization_id == admin.organization_id

    course = client.post(
        "/api/v1/courses",
        json={"name": "Org Course", "code": "ORG1", "layout_rows": 2, "layout_cols": 2},
        headers=auth_headers(admin),
    )
    assert course.status_code == 201, course.text
    row = db.scalar(select(Course).where(Course.code == "ORG1"))
    assert row is not None
    assert row.organization_id == admin.organization_id
