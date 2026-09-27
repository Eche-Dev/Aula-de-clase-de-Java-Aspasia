"""Crea el primer administrador (org_admin) o un super_admin del sistema.

Uso:
  python -m scripts.create_admin --role org_admin --email admin@aula.test --password ...
  python -m scripts.create_admin --role super_admin --email root@aula.test --password ...
  python -m scripts.create_admin --email admin@aula.test --password ... --reset
      (restaurar la contraseña de un usuario existente)
  AULA_ADMIN_EMAIL=... AULA_ADMIN_PASSWORD=... python -m scripts.create_admin

org_admin hereda la organización por defecto (se crea si no existe).
super_admin nace sin organización: únicamente por esta vía CLI.
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import select

from app.core.security import hash_secret
from app.db.session import SessionLocal
from app.models import User, UserRole
from app.services.organization import get_or_create_default_organization

CLI_ROLES = (UserRole.org_admin, UserRole.super_admin)


def create_admin(
    email: str,
    password: str,
    name: str = "Admin",
    role: UserRole = UserRole.org_admin,
    reset: bool = False,
) -> User | None:
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")
    if role not in CLI_ROLES:
        raise SystemExit(f"role must be one of: {', '.join(r.value for r in CLI_ROLES)}")
    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            if reset:
                existing.password_hash = hash_secret(password)
                existing.must_change_credentials = False
                existing.is_active = True
                db.add(existing)
                db.commit()
                db.refresh(existing)
                print(f"Password reset for {existing.email} (role={existing.role.value})")
                return existing
            print(f"User already exists: {existing.email} (role={existing.role.value})")
            return existing
        organization_id = None
        if role is UserRole.org_admin:
            organization_id = get_or_create_default_organization(db, billing_email=email).id
        user = User(
            name=name,
            email=email,
            role=role,
            organization_id=organization_id,
            password_hash=hash_secret(password),
            is_active=True,
            must_change_credentials=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        scope = "system" if role is UserRole.super_admin else "organization"
        print(f"Created {role.value}: {user.email} (id={user.id}, scope={scope})")
        return user
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an org_admin or a super_admin")
    parser.add_argument(
        "--role",
        choices=[r.value for r in CLI_ROLES],
        default=UserRole.org_admin.value,
        help="org_admin (default, with default organization) or super_admin (no org, CLI only)",
    )
    parser.add_argument("--email", default=os.environ.get("AULA_ADMIN_EMAIL", "admin@aula.test"))
    parser.add_argument("--password", default=os.environ.get("AULA_ADMIN_PASSWORD", ""))
    parser.add_argument("--name", default="Admin")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="If the user already exists, set a new password instead of doing nothing",
    )
    args = parser.parse_args()
    if not args.password:
        print("Set --password or AULA_ADMIN_PASSWORD (min 8 chars)", file=sys.stderr)
        raise SystemExit(1)
    create_admin(
        args.email,
        args.password,
        name=args.name,
        role=UserRole(args.role),
        reset=args.reset,
    )


if __name__ == "__main__":
    main()
