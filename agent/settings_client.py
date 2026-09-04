"""
Settings / credential store - reads and persists per-user broker credentials,
LLM API keys, and risk-engine thresholds in PostgreSQL.

Secrets are stored encrypted (Fernet); only these DAO methods return them
plaintext. Route/UI layers must use common.credentials.mask_secret.
"""
from __future__ import annotations

import os
import psycopg2
import psycopg2.extras

from common.credentials import decrypt_secret, encrypt_secret

RISK_PREF_KEYS = [
    "AGENT_KELLY_FRACTION", "AGENT_MAX_POSITION_PCT", "RISK_MAX_SECTOR_PCT",
    "RISK_VAR_CONFIDENCE", "RISK_MAX_VAR_PCT", "AGENT_MAX_DRAWDOWN_HALT",
]
RISK_PREF_DEFAULTS = {
    "AGENT_KELLY_FRACTION": "0.5", "AGENT_MAX_POSITION_PCT": "0.20",
    "RISK_MAX_SECTOR_PCT": "0.40", "RISK_VAR_CONFIDENCE": "0.99",
    "RISK_MAX_VAR_PCT": "0.05", "AGENT_MAX_DRAWDOWN_HALT": "0.10",
}


def _conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "graphalpha"),
        user=os.getenv("POSTGRES_USER", "graphalpha"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def _table_exists(cur, name: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (name,))
    r = cur.fetchone()
    if not r:
        return False
    val = r["to_regclass"] if isinstance(r, dict) else list(r.values())[0]
    return val is not None


def create_user(username: str, passphrase_hash: str) -> int:
    with _conn() as conn, conn.cursor() as cur:
        try:
            cur.execute("INSERT INTO users (username, passphrase_hash) VALUES (%s,%s) RETURNING id", (username, passphrase_hash))
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else 0
        except psycopg2.errors.UniqueViolation:
            return 0


def get_user_by_name(username: str) -> dict:
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if not _table_exists(cur, "users"):
            return None
        cur.execute("SELECT id, username, passphrase_hash FROM users WHERE username=%s", (username,))
        return cur.fetchone()

# ── Broker credentials ───────────────────────────────────────────────────
def list_broker_credentials(user_id: int, broker: str | None = None) -> list[dict]:
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if not _table_exists(cur, "broker_credentials"):
            return []
        q = "SELECT id, owner_id, broker, nickname, key_id, base_url, paper, is_active, last_verified_at FROM broker_credentials WHERE owner_id=%s"
        args = [user_id]
        if broker:
            q += " AND broker=%s"
            args.append(broker)
        q += " ORDER BY id DESC"
        cur.execute(q, args)
        return [dict(r) for r in cur.fetchall()]


def save_broker_credential(user_id: int, broker: str, key_id: str, secret: str,
                           nickname: str = "", base_url: str = "", paper: bool = True,
                           cred_id: int | None = None) -> int:
    enc = encrypt_secret(secret)
    with _conn() as conn, conn.cursor() as cur:
        if cred_id:
            cur.execute(
                "UPDATE broker_credentials SET key_id=%s, secret_encrypted=%s, nickname=%s, "
                "base_url=%s, paper=%s WHERE id=%s AND owner_id=%s RETURNING id",
                (key_id, enc, nickname, base_url, paper, cred_id, user_id))
            row = cur.fetchone(); conn.commit(); return row[0] if row else cred_id
        cur.execute(
            "INSERT INTO broker_credentials (owner_id, broker, key_id, secret_encrypted, "
            "nickname, base_url, paper) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (user_id, broker, key_id, enc, nickname, base_url, paper))
        row = cur.fetchone(); conn.commit(); return row[0] if row else 0


def delete_broker_credential(user_id: int, cred_id: int) -> bool:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM broker_credentials WHERE id=%s AND owner_id=%s", (cred_id, user_id))
        affected = cur.rowcount; conn.commit(); return affected > 0


def set_active_broker(user_id: int, broker: str, cred_id: int) -> bool:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM broker_credentials WHERE id=%s AND owner_id=%s AND broker=%s", (cred_id, user_id, broker))
        if not cur.fetchone():
            return False
        cur.execute("UPDATE broker_credentials SET is_active=FALSE WHERE owner_id=%s AND broker=%s", (user_id, broker))
        cur.execute("UPDATE broker_credentials SET is_active=TRUE WHERE id=%s", (cred_id,))
        conn.commit(); return True


def get_active_broker(user_id: int, broker: str) -> dict | None:
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if not _table_exists(cur, "broker_credentials"):
            return None
        cur.execute(
            "SELECT id, broker, key_id, secret_encrypted, base_url, paper FROM broker_credentials "
            "WHERE owner_id=%s AND broker=%s AND is_active=TRUE LIMIT 1", (user_id, broker))
        r = cur.fetchone()
        if not r:
            return None
        d = dict(r); d["secret_key"] = decrypt_secret(d.pop("secret_encrypted")); return d

def resolve_active_alpaca(user_id: int) -> dict | None: return get_active_broker(user_id, "alpaca")
def resolve_active_kraken(user_id: int) -> dict | None: return get_active_broker(user_id, "kraken")

# ── LLM API keys ───────────────────────────────────────────────────────────
def get_api_keys(user_id: int) -> dict:
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if not _table_exists(cur, "user_api_keys"):
            return {}
        cur.execute("SELECT provider, base_url, model FROM user_api_keys WHERE owner_id=%s", (user_id,))
        return {r["provider"]: {"provider": r["provider"], "base_url": r["base_url"], "model": r["model"], "configured": True} for r in cur.fetchall()}


def save_api_key(user_id: int, provider: str, key: str, base_url: str = "", model: str = "") -> int:
    enc = encrypt_secret(key)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_api_keys (owner_id, provider, key_encrypted, base_url, model) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (owner_id, provider) DO UPDATE SET "
            "key_encrypted=EXCLUDED.key_encrypted, base_url=EXCLUDED.base_url, model=EXCLUDED.model "
            "RETURNING id", (user_id, provider, enc, base_url, model))
        row = cur.fetchone(); conn.commit(); return row[0] if row else 0


def get_api_key_plain(user_id: int, provider: str) -> dict | None:
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if not _table_exists(cur, "user_api_keys"):
            return None
        cur.execute("SELECT provider, key_encrypted, base_url, model FROM user_api_keys WHERE owner_id=%s AND provider=%s", (user_id, provider))
        r = cur.fetchone()
        if not r:
            return None
        d = dict(r); d["key"] = decrypt_secret(d.pop("key_encrypted")); return d


# ── Risk-engine prefs ──────────────────────────────────────────────────────
def get_risk_prefs(user_id: int, fallback_env: bool = True) -> dict:
    prefs = dict(RISK_PREF_DEFAULTS)
    if fallback_env:
        for k in RISK_PREF_KEYS:
            if os.getenv(k):
                prefs[k] = str(os.getenv(k))
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if _table_exists(cur, "user_risk_prefs"):
            cur.execute("SELECT key, value FROM user_risk_prefs WHERE owner_id=%s", (user_id,))
            for r in cur.fetchall():
                prefs[r["key"]] = r["value"]
    return prefs


def set_risk_prefs(user_id: int, prefs: dict) -> None:
    with _conn() as conn, conn.cursor() as cur:
        for k, v in prefs.items():
            if k not in RISK_PREF_KEYS:
                continue
            cur.execute(
                "INSERT INTO user_risk_prefs (owner_id, key, value) VALUES (%s,%s,%s) "
                "ON CONFLICT (owner_id, key) DO UPDATE SET value=EXCLUDED.value", (user_id, k, str(v)))
        conn.commit()


__all__ = [
    "create_user", "get_user_by_name", "list_broker_credentials", "save_broker_credential",
    "delete_broker_credential", "set_active_broker", "get_active_broker",
    "resolve_active_alpaca", "resolve_active_kraken", "get_api_keys", "save_api_key",
    "get_api_key_plain", "get_risk_prefs", "set_risk_prefs", "RISK_PREF_KEYS", "RISK_PREF_DEFAULTS",
]
