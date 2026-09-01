"""
Alpaca MCP Bridge — GraphAlpha
Python client to interact with the official alpacahq/alpaca-mcp-server.
Allows the orchestrator to use natural-language Alpaca tools alongside
direct REST calls.
"""

import json
import os
import queue
import subprocess
import threading
from typing import Any

from loguru import logger

# Alpaca MCP servers speak the JSON-RPC-over-stdio framing used by the MCP SDK:
# a single JSON-RPC message per line, with a Content-Length header line first
# (LSP-style). We must a) send the initialize handshake before first tool call,
# b) send Content-Length headers, c) read framed responses, d) background-read
# stdout so the stream never deadlocks, and e) tolerate a server that uses
# newline-delimited JSON instead of Content-Length.

_JSONRPC_VERSION = "2.0"


class AlpacaMCPBridge:
    def __init__(self):
        self.mcp_server_path = os.getenv(
            "ALPACA_MCP_SERVER_PATH",
            "npx @alpacahq/alpaca-mcp-server",
        )
        self.timeout_s = float(os.getenv("ALPACA_MCP_TIMEOUT", 15))
        self._process = None
        self._stdout_q: queue.Queue = queue.Queue()
        self._reader_thread = None
        self._next_id = 0

    # ── Process lifecycle ─────────────────────────────────────────────────────
    def start(self):
        if self._process and self._process.poll() is None:
            return
        try:
            self._process = subprocess.Popen(
                self.mcp_server_path.split(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._stdout_q = queue.Queue()
            self._reader_thread = threading.Thread(
                target=self._read_stdout, daemon=True
            )
            self._reader_thread.start()
            self._initialize()
            logger.info("Alpaca MCP server started + initialized")
        except Exception as e:
            logger.error(f"Failed to start Alpaca MCP server: {e}")
            self._process = None

    def stop(self):
        if self._process:
            self._process.terminate()
            self._process = None

    def _read_stdout(self):
        while True:
            line = self._process.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line:
                self._stdout_q.put(line)

    def _send(self, payload: dict) -> str:
        body = json.dumps(payload)
        raw = (
            f"Content-Length: {len(body.encode('utf-8'))}\r\n"
            f"\r\n"
            f"{body}\r\n"
        )
        self._process.stdin.write(raw)
        self._process.stdin.flush()
        return self._receive()

    def _receive(self) -> str:
        """Read one framed JSON-RPC response (Content-Length or newline-delimited)."""
        try:
            return self._stdout_q.get(timeout=self.timeout_s) or ""
        except queue.Empty:
            return ""

    def _request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        payload = {"jsonrpc": _JSONRPC_VERSION, "id": self._next_id,
                   "method": method, "params": params}
        raw = self._send(payload)
        if not raw:
            return {"error": {"message": "no response from MCP server", "code": -32000}}
        return self._parse_response(raw)

    def _initialize(self):
        """MCP stdio requires an initialize handshake before tools/list etc."""
        init = self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "graphalpha", "version": "1.0.0"},
        })
        if "error" in init and init.get("error"):
            logger.warning(f"MCP initialize failed: {init['error']}")
        # Acknowledge the server's initialized notification
        try:
            self._request("notifications/initialized", {})
        except Exception:
            pass

    @staticmethod
    def _parse_response(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"error": {"message": f"invalid JSON from MCP: {raw[:200]}", "code": -32700}}

    # ── Tool call ─────────────────────────────────────────────────────────────
    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if not self._process or self._process.poll() is not None:
            self.start()
        if not self._process:
            return {"error": "MCP server not available"}
        resp = self._request(
            "tools/call", {"name": tool_name, "arguments": arguments}
        )
        if "error" in resp and isinstance(resp.get("error"), dict):
            return {"error": resp["error"].get("message")}
        return resp


_mcp = AlpacaMCPBridge()
