"""Settings + per-user credential vault API.

Auth: passphrase register/login -> HMAC-signed bearer token (stateless).
Broker credentials + LLM API keys stored encrypted, returned masked only.
Risk-engine thresholds editable live (applied next agent cycle).
"""
from __future__ import annotations

import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from loguru import logger

from common.credentials import (
    mask_secret, passphrase_hash, verify_passphrase,
    issue_token, verify_token, redact,
)
import agent.settings_client as store

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ── Auth dependency ──────────────────────────────────────────────────────────
def get_current_user(authorization: str | None = Header(default=None)) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated — log in")
    token = authorization.split(" ", 1)[1].strip()
    try:
        uid, _ = verify_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return uid


class RegisterReq(BaseModel):
    username: str
    passphrase: str


@router.post("/register")
def register(req: RegisterReq):
    u = (req.username or "").strip()
    if len(u) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    if len(req.passphrase or "") < 6:
        raise HTTPException(status_code=400, detail="Passphrase too short (min 6 chars)")
    uid = store.create_user(u, passphrase_hash(req.passphrase))
    if not uid:
        raise HTTPException(status_code=409, detail="Username already exists")
    return {"token": issue_token(uid, u), "user": u}


@router.post("/login")
def login(req: RegisterReq):
    user = store.get_user_by_name((req.username or "").strip())
    if not user or not verify_passphrase(req.passphrase, user["passphrase_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": issue_token(user["id"], user["username"]), "user": user["username"]}


@router.get("/me")
def me(uid: int = Depends(get_current_user)):
    return {"user_id": uid, "ok": True}


# ── Broker credentials ───────────────────────────────────────────────────────
class BrokerCredReq(BaseModel):
    broker: str            # alpaca | kraken
    key_id: str
    secret: str
    nickname: str = ""
    base_url: str = ""
    paper: bool = True
    cred_id: int | None = None


class SetActiveReq(BaseModel):
    broker: str
    cred_id: int


@router.get("/brokers")
def list_brokers(uid: int = Depends(get_current_user)):
    rows = store.list_broker_credentials(uid)
    for r in rows:
        if r.get("key_id"):
            r["key_id"] = mask_secret(str(r["key_id"]))
    return rows


@router.post("/brokers")
def save_broker(req: BrokerCredReq, uid: int = Depends(get_current_user)):
    if req.broker not in ("alpaca", "kraken"):
        raise HTTPException(status_code=400, detail="broker must be alpaca|kraken")
    if not req.key_id.strip() or not req.secret.strip():
        raise HTTPException(status_code=400, detail="key_id and secret are required")
    cid = store.save_broker_credential(uid, req.broker, req.key_id.strip(), req.secret,
                                       req.nickname, req.base_url, req.paper, req.cred_id)
    if not req.paper:
        logger.warning(f"LIVE account saved for user {uid} broker {req.broker} (paper=False)")
    return {"id": cid, "masked": mask_secret(req.secret), "broker": req.broker}


@router.delete("/brokers/{cred_id}")
def delete_broker(cred_id: int, uid: int = Depends(get_current_user)):
    return {"deleted": store.delete_broker_credential(uid, cred_id)}


@router.post("/brokers/active")
def set_active(req: SetActiveReq, uid: int = Depends(get_current_user)):
    ok = store.set_active_broker(uid, req.broker, req.cred_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Credential not found / not yours")
    logger.info(f"user {uid} activated {req.broker} cred {req.cred_id}")
    return {"ok": True}


@router.post("/brokers/test")
def test_broker(req: SetActiveReq, uid: int = Depends(get_current_user)):
    cred = store.get_active_broker(uid, req.broker)
    if not cred:
        # test the just-provided params via a temp credential set
        cred = {"key_id": req.cred_id if req.broker == "alpaca" else str(req.cred_id),
                "secret_key": "", "base_url": "", "paper": True}
    try:
        if req.broker == "alpaca":
            from agent.alpaca_client import alpaca
            base = cred.get("base_url") or "https://paper-api.alpaca.markets"
            old = (alpaca.key_id, alpaca.secret_key, alpaca.base_url, alpaca.paper)
            alpaca.configure(cred["key_id"], cred.get("secret_key", ""), base, cred.get("paper", True))
            try:
                import asyncio
                acc = asyncio.run(alpaca.get_account())
                ok = acc.get("status") not in ("unconfigured", "error")
                return {"ok": ok, "status": acc.get("status"), "equity": acc.get("equity")}
            finally:
                alpaca.configure(*old)
        return {"ok": False, "note": "Kraken test not wired (legacy)"}
    except Exception as e:
        return {"ok": False, "error": redact(str(e))}


# ── LLM API keys ─────────────────────────────────────────────────────────────
class ApiKeyReq(BaseModel):
    provider: str   # groq | featherless
    key: str
    base_url: str = ""
    model: str = ""


@router.get("/apikeys")
def list_api_keys(uid: int = Depends(get_current_user)):
    return store.get_api_keys(uid)


@router.post("/apikeys")
def save_api_key(req: ApiKeyReq, uid: int = Depends(get_current_user)):
    if req.provider not in ("groq", "featherless"):
        raise HTTPException(status_code=400, detail="provider must be groq|featherless")
    store.save_api_key(uid, req.provider, req.key, req.base_url, req.model)
    return {"ok": True, "provider": req.provider, "masked": mask_secret(req.key)}


@router.post("/apikeys/test")
def test_api_key(req: ApiKeyReq, uid: int = Depends(get_current_user)):
    url = (req.base_url or ("https://api.groq.com/openai/v1" if req.provider == "groq"
                            else "https://api.featherless.ai/v1")).rstrip("/")
    try:
        r = httpx.get(f"{url}/models", headers={"Authorization": f"Bearer {req.key}"},
                      timeout=15)
        if r.status_code == 200:
            data = r.json()
            models = [m.get("id") for m in (data.get("data") or [])][:20]
            return {"ok": True, "status": 200, "models": models}
        return {"ok": False, "status": r.status_code, "detail": redact(r.text[:200])}
    except Exception as e:
        return {"ok": False, "error": redact(str(e))}


# ── Risk-engine thresholds ───────────────────────────────────────────────────
@router.get("/risk")
def get_risk(uid: int = Depends(get_current_user)):
    return store.get_risk_prefs(uid)


@router.put("/risk")
def put_risk(prefs: dict, uid: int = Depends(get_current_user)):
    store.set_risk_prefs(uid, prefs)
    return store.get_risk_prefs(uid)


# ── Status summary ───────────────────────────────────────────────────────────
@router.get("/status")
def status(uid: int = Depends(get_current_user)):
    brokers = store.list_broker_credentials(uid)
    active = {}
    for b in brokers:
        if b.get("is_active"):
            active[b["broker"]] = {"nickname": b.get("nickname"), "id": b.get("id"), "paper": b.get("paper")}
    return {
        "brokers_configured": sorted({b["broker"] for b in brokers}),
        "active": active,
        "api_keys": list(store.get_api_keys(uid).keys()),
        "risk_prefs": store.get_risk_prefs(uid),
    }
