"""Tests Fase D: 2FA TOTP obligatorio de super_admin (backend).

Vectores oficiales del RFC 6238 + flujo completo de login con reto:
el super_admin NUNCA recibe tokens hasta verificar el segundo factor.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import User, UserRole
from app.services.totp import generate_secret, totp_code, verify_totp
from tests.api_helpers import auth_headers, make_admin, make_super_admin

# Secreto ASCII de los vectores de prueba del RFC 6238 (SHA-1)
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

BASE = "/api/v1"


def _login_challenge(client: TestClient) -> str:
    r = client.post(
        f"{BASE}/auth/login/staff",
        json={"email": "root@aula.test", "password": "root-secret-1"},
    )
    assert r.status_code == 200
    assert r.json()["mfa_required"] is True
    return str(r.json()["mfa_token"])


def _root_secret(db: Session) -> str:
    root = db.scalar(select(User).where(User.role == UserRole.super_admin))
    assert root is not None and root.mfa_secret
    return root.mfa_secret


# --- 1. TOTP (vectores RFC 6238 y deriva de reloj) ---


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_totp_rfc6238_vectors(at: int, expected: str) -> None:
    # Los vectores del RFC 6238 (Apéndice B) son de 8 dígitos; la app usa
    # los 6 dígitos estándar de las apps authenticator → últimos 6 del vector.
    assert totp_code(RFC_SECRET, at=float(at)) == expected[-6:]


def test_totp_verify_rejects_garbage_and_foreign_codes() -> None:
    secret = generate_secret()
    assert verify_totp(secret, totp_code(secret)) is True
    # Un código de otro secreto (otra ventana, otra cuenta) no autentica
    assert verify_totp(secret, totp_code(RFC_SECRET)) is False
    # Entradas mal formadas nunca autentican
    assert verify_totp(secret, "abcdef") is False
    assert verify_totp(secret, "12345") is False
    assert verify_totp("", totp_code(secret)) is False


# --- 2. Login: el reto 2FA ---


def test_super_admin_login_returns_challenge_without_tokens(
    client: TestClient, db: Session
) -> None:
    make_super_admin(db, email="root@aula.test", password="root-secret-1")
    r = client.post(
        f"{BASE}/auth/login/staff",
        json={"email": "root@aula.test", "password": "root-secret-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_required"] is True
    assert body["access_token"] == ""
    assert body["mfa_enrolled"] is False
    assert body["mfa_token"]
    # Sin segundo factor no existe ninguna sesión: ni access ni refresh
    assert r.cookies.get("refresh_token") is None


def test_org_admin_login_unchanged_without_mfa(client: TestClient, db: Session) -> None:
    make_admin(db, email="admin@aula.test", password="admin-secret-1")
    r = client.post(
        f"{BASE}/auth/login/staff",
        json={"email": "admin@aula.test", "password": "admin-secret-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["mfa_required"] is False
    assert body["mfa_token"] is None
    assert r.cookies.get("refresh_token")


def test_super_admin_full_mfa_flow_then_relogin_enrolled(client: TestClient, db: Session) -> None:
    make_super_admin(db, email="root@aula.test", password="root-secret-1")
    mfa_token = _login_challenge(client)

    # Setup (aún sin sesión): devuelve el secreto pendiente de confirmar
    r = client.post(f"{BASE}/auth/mfa/setup", json={"mfa_token": mfa_token})
    assert r.status_code == 200
    setup = r.json()
    assert setup["mfa_enabled"] is False
    assert setup["otpauth_url"].startswith("otpauth://totp/")

    # Verify con el código vigente → aquí salen los tokens reales
    r = client.post(
        f"{BASE}/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": totp_code(setup["secret"])},
    )
    assert r.status_code == 200
    tokens = r.json()
    assert tokens["mfa_enabled"] is True
    assert tokens["access_token"]
    assert tokens["must_change_credentials"] is False
    assert r.cookies.get("refresh_token")

    # La sesión recién emitida funciona y el usuario queda "enrolled"
    me = client.get(
        f"{BASE}/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["role"] == "super_admin"
    assert me.json()["mfa_enabled"] is True

    # Segundo login: mismo reto, pero ya enrolled (sin setup)
    r = client.post(
        f"{BASE}/auth/login/staff",
        json={"email": "root@aula.test", "password": "root-secret-1"},
    )
    body = r.json()
    assert body["mfa_required"] is True
    assert body["mfa_enrolled"] is True
    r = client.post(
        f"{BASE}/auth/mfa/verify",
        json={"mfa_token": body["mfa_token"], "code": totp_code(_root_secret(db))},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


# --- 3. Rechazos: código malo, lockout y tokens basura ---


def test_invalid_codes_then_lockout_after_five(client: TestClient, db: Session) -> None:
    make_super_admin(db, email="root@aula.test", password="root-secret-1")
    mfa_token = _login_challenge(client)
    secret = client.post(f"{BASE}/auth/mfa/setup", json={"mfa_token": mfa_token}).json()["secret"]
    wrong = "000000" if totp_code(secret) != "000000" else "111111"

    # 5 códigos malos → 401 cada uno y jamás un token
    for _ in range(5):
        r = client.post(
            f"{BASE}/auth/mfa/verify",
            json={"mfa_token": mfa_token, "code": wrong},
        )
        assert r.status_code == 401
        assert r.json() == {"detail": "Invalid authentication code"}

    # 6º intento (incluso con el código CORRECTO) → bloqueo 429
    r = client.post(
        f"{BASE}/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": totp_code(secret)},
    )
    assert r.status_code == 429


def test_garbage_or_wrong_purpose_mfa_token_rejected(client: TestClient, db: Session) -> None:
    make_super_admin(db, email="root@aula.test", password="root-secret-1")

    # Token inexistente
    assert client.post(f"{BASE}/auth/mfa/setup", json={"mfa_token": "no-existe"}).status_code == 401

    # Un access token normal no sirve como mfa_token (propósito distinto)
    other = make_super_admin(db, email="root2@aula.test", password="root-secret-2")
    access = create_access_token(str(other.id), role="super_admin")
    r = client.post(f"{BASE}/auth/mfa/verify", json={"mfa_token": access, "code": "123456"})
    assert r.status_code == 401

    # Sin token y sin sesión → 401
    assert client.post(f"{BASE}/auth/mfa/setup", json={}).status_code == 401


# --- 4. Fronteras de rol y gestión con sesión ---


def test_mfa_endpoints_reject_non_super_admin_roles(client: TestClient, db: Session) -> None:
    org_admin = make_admin(db, email="admin@aula.test", password="admin-secret-1")
    headers = auth_headers(org_admin)

    assert client.post(f"{BASE}/auth/mfa/setup", json={}, headers=headers).status_code == 403
    assert (
        client.post(f"{BASE}/auth/mfa/verify", json={"code": "123456"}, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            f"{BASE}/auth/mfa/disable", json={"code": "123456"}, headers=headers
        ).status_code
        == 403
    )


def test_session_setup_verify_and_disable(client: TestClient, db: Session) -> None:
    root = make_super_admin(db, email="root@aula.test", password="root-secret-1")
    headers = auth_headers(root)

    # Sin setup previo → verify con sesión es un 400 explícito
    assert (
        client.post(f"{BASE}/auth/mfa/verify", json={"code": "123456"}, headers=headers).status_code
        == 400
    )

    # Setup + verify con sesión → activa sin emitir tokens (ya hay sesión)
    setup = client.post(f"{BASE}/auth/mfa/setup", json={}, headers=headers)
    assert setup.status_code == 200
    r = client.post(
        f"{BASE}/auth/mfa/verify",
        json={"code": totp_code(setup.json()["secret"])},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json() == {
        "mfa_enabled": True,
        "access_token": None,
        "token_type": "bearer",
        "must_change_credentials": None,
    }

    # Ya activo → un nuevo setup responde 409
    assert client.post(f"{BASE}/auth/mfa/setup", json={}, headers=headers).status_code == 409

    # Disable exige un código vigente (no basta con la sesión)
    bad = client.post(f"{BASE}/auth/mfa/disable", json={"code": "000000"}, headers=headers)
    assert bad.status_code == 401
    r = client.post(
        f"{BASE}/auth/mfa/disable",
        json={"code": totp_code(_root_secret(db))},
        headers=headers,
    )
    assert r.status_code == 204

    # Tras desactivar: /auth/me vuelve a false y el login exige setup otra vez
    me = client.get(f"{BASE}/auth/me", headers=headers)
    assert me.json()["mfa_enabled"] is False
    r = client.post(
        f"{BASE}/auth/login/staff",
        json={"email": "root@aula.test", "password": "root-secret-1"},
    )
    assert r.json()["mfa_required"] is True
    assert r.json()["mfa_enrolled"] is False
