from __future__ import annotations

import base64
import binascii
import hashlib
import hmac


MIN_PASSWORD_ITERATIONS = 600_000
MAX_PASSWORD_ITERATIONS = 2_000_000


def validate_password_hash(encoded: str) -> tuple[int, bytes, bytes]:
    """Decode a bounded PBKDF2-SHA256 record without exposing its contents."""

    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$")
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text, validate=True)
        digest = base64.b64decode(digest_text, validate=True)
        if (
            algorithm != "pbkdf2_sha256"
            or not MIN_PASSWORD_ITERATIONS <= iterations <= MAX_PASSWORD_ITERATIONS
            or not 16 <= len(salt) <= 64
            or len(digest) != 32
        ):
            raise ValueError
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ValueError("console password hash must be a valid PBKDF2-SHA256 record with 600000 to 2000000 iterations") from exc
    return iterations, salt, digest


def verify_password(password: str, encoded: str) -> bool:
    iterations, salt, expected = validate_password_hash(encoded)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
