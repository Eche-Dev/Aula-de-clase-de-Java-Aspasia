"""TOTP (RFC 6238) para el 2FA de super_admin, solo con la stdlib.

SHA-1 de 6 dígitos con paso de 30 s (parámetros por defecto de la RFC y de
las apps authenticator habituales). Sin dependencias nuevas: `hmac`,
`hashlib`, `base64`, `struct`, `time` y `secrets`.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

DIGITS = 6
STEP_SECONDS = 30
ALGORITHM = hashlib.sha1
ISSUER = "Aspasia"

# 20 bytes = 160 bits de entropía, el mínimo recomendado para HOTP/TOTP.
SECRET_BYTES = 20


def generate_secret() -> str:
    """Secreto base32 (sin padding) listo para introducir en la app."""
    raw = secrets.token_bytes(SECRET_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _secret_to_bytes(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded, casefold=True)


def totp_code(secret: str, at: float | None = None) -> str:
    """Código TOTP para el instante `at` (epoch, por defecto ahora)."""
    counter = int((time.time() if at is None else at) // STEP_SECONDS)
    key = _secret_to_bytes(secret)
    digest = hmac.new(key, struct.pack(">Q", counter), ALGORITHM).digest()
    offset = digest[-1] & 0x0F
    (code,) = struct.unpack(">I", digest[offset : offset + 4])
    code &= 0x7FFFFFFF
    return str(code % 10**DIGITS).zfill(DIGITS)


def verify_totp(secret: str, code: str, *, window: int = 1) -> bool:
    """True si `code` coincide con el paso actual o los ±`window` adyacentes.

    Ventana ±1 (30 s de tolerancia por reloj desfasado) sin reutilización:
    cada código solo vale para su propio instante.
    """
    if not secret or not code.isdigit() or len(code) != DIGITS:
        return False
    now = time.time()
    current = int(now // STEP_SECONDS)
    for offset in range(-window, window + 1):
        if hmac.compare_digest(totp_code(secret, (current + offset) * STEP_SECONDS), code):
            return True
    return False


def otpauth_url(secret: str, *, account: str, issuer: str = ISSUER) -> str:
    """URL otpauth:// para añadirla a una app authenticator (mostrada como texto)."""
    label = urllib.parse.quote(f"{issuer}:{account}", safe=":")
    query = urllib.parse.urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": str(DIGITS),
            "period": str(STEP_SECONDS),
        }
    )
    return f"otpauth://totp/{label}?{query}"
