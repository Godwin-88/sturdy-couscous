"""
LLM clients for the agent layer.

Supports:
- Ollama (local, /api/generate)
- Groq (remote, OpenAI-compatible /chat/completions)

Selection is controlled by environment variables:
- If GROQ_API_KEY is set and non-empty, Groq is used.
- Otherwise, Ollama is used.
"""

import json
import os
import logging
from typing import Optional, Callable, Dict, Any

import requests

logger = logging.getLogger(__name__)


def _load_env():
    """Best-effort .env loader (no hard dependency on python-dotenv)."""
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)
    except ImportError:
        pass


# Load .env immediately on import so env vars are available before any get_*() call
_load_env()


# ── Ollama client ─────────────────────────────────────────────────────────────


def _get_ollama_config() -> Dict[str, Any]:
    _load_env()
    host = (os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").strip().rstrip("/")
    # Use 127.0.0.1 instead of localhost to avoid Windows IPv6 (::1) vs Ollama on IPv4
    if host in ("http://localhost:11434", "http://localhost:11434/"):
        host = "http://127.0.0.1:11434"
    return {
        "host": host,
        "model": os.getenv("OLLAMA_MODEL", "llama3:8b"),
        "fallback": os.getenv("OLLAMA_MODEL_FALLBACK", "qwen2:7b"),
        "timeout": float(os.getenv("OLLAMA_TIMEOUT", "60")),
    }


class OllamaClient:
    """Sync Ollama API client for /api/generate."""

    def __init__(self, host: Optional[str] = None, model: Optional[str] = None, timeout: float = 60.0):
        cfg = _get_ollama_config()
        self._base = (host or cfg["host"]).rstrip("/")
        self._model = model or cfg["model"]
        self._fallback = cfg["fallback"]
        self._timeout = timeout or cfg["timeout"]

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        model: Optional[str] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Call Ollama /api/generate. Returns full response text.
        On timeout or error, retries with fallback model once.
        """
        model = model or self._model
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream_callback is not None,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        def _call(m: str) -> str:
            payload["model"] = m
            if stream_callback:
                return self._generate_stream(payload, stream_callback)
            return self._generate_sync(payload)

        try:
            return _call(model)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.warning("Ollama primary model failed: %s", e)
            if model != self._fallback:
                try:
                    return _call(self._fallback)
                except Exception as e2:
                    logger.warning("Ollama fallback failed: %s", e2)
                    raise
            raise

    def _generate_sync(self, payload: dict) -> str:
        payload = {**payload, "stream": False}
        r = requests.post(f"{self._base}/api/generate", json=payload, timeout=self._timeout)
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()

    def _generate_stream(self, payload: dict, callback: Callable[[str], None]) -> str:
        payload["stream"] = True
        full: list[str] = []
        r = requests.post(
            f"{self._base}/api/generate",
            json=payload,
            timeout=self._timeout,
            stream=True,
        )
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                chunk = json.loads(line)
                piece = chunk.get("response") or ""
                if piece:
                    full.append(piece)
                    callback(piece)
            except json.JSONDecodeError:
                continue
        return "".join(full)

    def health_check(self) -> bool:
        """Verify Ollama is reachable (e.g. GET /api/tags)."""
        try:
            r = requests.get(f"{self._base}/api/tags", timeout=10.0)
            return r.status_code == 200
        except Exception as e:
            logger.warning("Ollama health_check failed at %s: %s", self._base, e)
            return False


# ── Groq client (remote, OpenAI-compatible) ───────────────────────────────────


def _get_groq_config() -> Dict[str, Any]:
    _load_env()
    api_key = os.getenv("GROQ_API_KEY") or ""
    model = os.getenv("GROQ_MODEL", "llama3-8b-8192")
    base = (os.getenv("GROQ_API_BASE") or "https://api.groq.com/openai/v1").rstrip("/")
    return {"api_key": api_key, "model": model, "base": base, "timeout": float(os.getenv("GROQ_TIMEOUT", "60"))}


class GroqClient:
    """Groq Cloud client using OpenAI-compatible /chat/completions API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        cfg = _get_groq_config()
        self._api_key = api_key or cfg["api_key"]
        self._model = model or cfg["model"]
        self._base = (base_url or cfg["base"]).rstrip("/")
        self._timeout = cfg["timeout"]

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        model: Optional[str] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Call Groq /chat/completions and return the assistant text."""
        if not self._api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        if stream_callback is not None:
            # For now, do non-streaming and send the full text at once.
            text = self._generate_sync(prompt, system, temperature, model)
            stream_callback(text)
            return text
        return self._generate_sync(prompt, system, temperature, model)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _generate_sync(
        self,
        prompt: str,
        system: Optional[str],
        temperature: float,
        model: Optional[str] = None,
    ) -> str:
        url = f"{self._base}/chat/completions"
        m = model or self._model
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": m,
            "messages": messages,
            "temperature": float(temperature),
            "stream": False,
        }
        r = requests.post(url, headers=self._headers(), json=payload, timeout=self._timeout)
        r.raise_for_status()
        data = r.json()
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError):
            logger.warning("Unexpected Groq response schema: %s", data)
            return ""

    def health_check(self) -> bool:
        """Basic health check by listing models."""
        if not self._api_key:
            return False
        try:
            url = f"{self._base}/models"
            r = requests.get(url, headers=self._headers(), timeout=10.0)
            return r.status_code == 200
        except Exception as e:
            logger.warning("Groq health_check failed at %s: %s", self._base, e)
            return False


# ── Factory ───────────────────────────────────────────────────────────────────


def get_llm_client():
    """
    Return the default LLM client based on environment configuration.

    Precedence:
    - If GROQ_API_KEY is set → GroqClient
    - Else → OllamaClient
    """
    _load_env()
    groq_key = os.getenv("GROQ_API_KEY") or ""
    if groq_key:
        logger.info("Using GroqClient for agent LLM")
        return GroqClient()
    logger.info("Using OllamaClient for agent LLM")
    return OllamaClient()
