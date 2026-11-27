"""Security primitives: password hashing, auth tokens, secrets from the environment, and
optional field-level encryption for the re-identification table.

* Passwords: ``hashlib.scrypt`` (n=2**14, r=8, p=1, 32-byte key, 16-byte random salt), stored
  as ``scrypt$n$r$p$salt_b64$hash_b64``; verified in constant time.
* Tokens: 32 random bytes (urlsafe base64). Only the SHA-256 of a token is stored, so a stolen
  database does not yield usable tokens. Tokens expire (``NEUROMETRIC_TOKEN_TTL_MIN``, default
  30 minutes) and can be revoked (logout).
* Secrets come from environment variables only (never from the database or source code).
* Field-level encryption: AES-256-GCM from the ``cryptography`` package with the key in
  ``NEUROMETRIC_REID_KEY`` (urlsafe base64 of 32 bytes). Without both, storing a
  re-identification key is refused (see DATA_GOVERNANCE.md).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Optional

from .errors import ConfigurationError

SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 2 ** 14, 8, 1, 32
MIN_PASSWORD_LEN = 12

ENV_TOKEN_TTL = "NEUROMETRIC_TOKEN_TTL_MIN"
ENV_REID_KEY = "NEUROMETRIC_REID_KEY"


def env_secret(name: str, required: bool = False) -> Optional[str]:
    """Read a secret from the environment (the only supported secret source)."""
    v = os.environ.get(name)
    if required and not v:
        raise ConfigurationError(f"environment variable {name} is required")
    return v or None


def token_ttl_minutes() -> float:
    v = os.environ.get(ENV_TOKEN_TTL)
    try:
        return max(1.0, float(v)) if v else 30.0
    except ValueError:
        return 30.0


def check_password_policy(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                        p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p),
                            dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# A fixed dummy hash so that login for an unknown user costs the same as for a known one
# (avoids a username-enumeration timing side channel).
_DUMMY_HASH = None


def dummy_verify(password: str) -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("dummy-password-for-timing")
    verify_password(password, _DUMMY_HASH)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- field encryption
def crypto_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except Exception:  # pragma: no cover - depends on environment
        return False


def generate_field_key() -> str:
    """Helper for operators: a new urlsafe-base64 AES-256 key for NEUROMETRIC_REID_KEY."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _field_key() -> bytes:
    raw = env_secret(ENV_REID_KEY)
    if not raw:
        raise ConfigurationError(
            f"{ENV_REID_KEY} is not set: the re-identification table requires field-level "
            "encryption (generate a key with neurometric.study.security.generate_field_key())")
    try:
        key = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as e:
        raise ConfigurationError(f"{ENV_REID_KEY} is not valid urlsafe base64") from e
    if len(key) != 32:
        raise ConfigurationError(f"{ENV_REID_KEY} must decode to 32 bytes")
    return key


def encrypt_field(plaintext: str, associated: str) -> tuple[str, bytes]:
    """AES-256-GCM encrypt; ``associated`` (e.g. the participant pseudonym) is bound as AAD so
    a ciphertext cannot be moved to another row. Returns (scheme, nonce||ciphertext)."""
    if not crypto_available():  # pragma: no cover
        raise ConfigurationError("the 'cryptography' package is required for field encryption")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _field_key()
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), associated.encode("utf-8"))
    return "aes-256-gcm/v1", nonce + ct


def decrypt_field(scheme: str, blob: bytes, associated: str) -> str:
    if scheme != "aes-256-gcm/v1":
        raise ConfigurationError(f"unknown encryption scheme {scheme!r}")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _field_key()
    return AESGCM(key).decrypt(blob[:12], blob[12:], associated.encode("utf-8")).decode("utf-8")
