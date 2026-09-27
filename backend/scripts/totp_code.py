"""Muestra el secreto TOTP y el código vigente de un usuario (solo desarrollo).

Para probar el 2FA del super_admin sin app en el móvil.

Uso:
  python -m scripts.totp_code --email root@aspasia.test
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User
from app.services import totp


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the current TOTP code for a user")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == args.email))
        if user is None:
            raise SystemExit(f"No existe ningún usuario con email {args.email}")
        if not user.mfa_secret:
            raise SystemExit("Ese usuario aún no tiene 2FA (primero haz el setup desde la app)")
        print(f"secret: {user.mfa_secret}")
        print(f"code:   {totp.totp_code(user.mfa_secret)}")
        print("válido ~30s (ventana de ±1 pasos aceptada)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
