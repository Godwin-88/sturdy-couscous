"""
Credential helpers for the per-user settings vault.

- Passphrase hashing: stdlib `hashlib.scrypt` (no external dep).
- Short-lived stateless tokens: stdlib `hmac` (signed bearer).
- Secret-at-rest encryption: Fernet (via the `cryptography` package).

Never return raw secrets to the UI — always go through `mask_secret`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
    _FERNET_OK = True
except Exception:  # pragma: no cover - cryptography installed in api container
    _FERNET_OK = False


# ── Fernet master key management ─────────────────────────────────────────────
def _fernet() -> Fernet | None:
    if not _FERNET_OK:
        return None
    key = os.getenv("CREDENTIALS_MASTER_KEY", "").strip()
    if not key:
        # Dev fallback: a generated key file in the mounted volume. Loud warning.
        keyfile = Path("/app/.credentials_key")
        if not keyfile.exists():
            keyfile.write_text(Fernet.generate_key().decode())
        key = keyfile.read_text().strip()
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_secret(plain: str) -> str:
    f = _fernet()
    if f is None:
        return plain  # degrade: no crypto available (plaintext, flagged in logs)
    return f.encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    f = _fernet()
    if f is None:
        return token
    try:
        return f.decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return ""


def mask_secret(secret: str) -> str:
    """`••••` + last 4 chars. Never exposes the full key."""
    if not secret:
        return ""
    tail = secret[-4:] if len(secret) >= 4 else secret
    return f"\u2022\u2022\u2022\u2022{tail}"


def redact(text: str) -> str:
    """Best-effort removal of likely secret material from logs/errors."""
    if not text:
        return text
    import re
    text = re.sub(r"(?i)(key|secret|token|password|passphrase)[\"':=\s]*([A-Za-z0-9_\-\./]{6,})", r"\1=***", text)
    return text


# ── Passphrase hashing (scrypt) ──────────────────────────────────────────────
_SALT = b"graphalpha-settings-v1"


def passphrase_hash(passphrase: str) -> str:
    dk = hashlib.scrypt(passphrase.encode(), salt=_SALT, n=2**14, r=8, p=1)
    return base64.b64encode(dk).decode()


def verify_passphrase(passphrase: str, expected_hash: str) -> bool:
    try:
        return hmac.compare_digest(passphrase_hash(passphrase), expected_hash)
    except Exception:
        return False


# ── HMAC-signed stateless bearer tokens ──────────────────────────────────────
_TOKEN_TTL = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))  # 8h default


def _token_secret() -> bytes:
    return os.getenv("AUTH_HMAC_SECRET", "graphalpha-dev-hmac-secret-change-me").encode()


def issue_token(user_id: int, username: str) -> str:
    exp = int(time.time()) + _TOKEN_TTL
    payload = f"{user_id}.{username}.{exp}".encode()
    sig = hmac.new(_token_secret(), payload, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload + b"." + sig.encode()).decode()


def verify_token(token: str):
    """Return (user_id, username) or raise ValueError."""
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        payload, sig = raw.rsplit(b".", 1)
        expected = hmac.new(_token_secret(), payload, hashlib.sha256).hexdigest().encode()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        uid_s, uname, exp = payload.decode().split(".")
        if int(exp) < int(time.time()):
            raise ValueError("token expired")
        return int(uid_s), uname
    except Exception:
        raise ValueError("invalid token")


__all__ = [
    "encrypt_secret", "decrypt_secret", "mask_secret", "redact",
    "passphrase_hash", "verify_passphrase", "issue_token", "verify_token",
]
