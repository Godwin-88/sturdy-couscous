"""
Alpaca MCP Bridge — GraphAlpha
Python client to interact with the official alpacahq/alpaca-mcp-server.
Allows the orchestrator to use natural-language Alpaca tools alongside
direct REST calls.
"""

import json
import os
import subprocess
from typing import Any

from loguru import logger


class AlpacaMCPBridge:
    def __init__(self):
        self.mcp_server_path = os.getenv(
            "ALPACA_MCP_SERVER_PATH",
            "npx @alpacahq/alpaca-mcp-server"
        )
        self._process = None

    def start(self):
        if self._process:
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
            logger.info("Alpaca MCP server started")
        except Exception as e:
            logger.error(f"Failed to start Alpaca MCP server: {e}")

    def stop(self):
        if self._process:
            self._process.terminate()
            self._process = None

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if not self._process:
            self.start()
        if not self._process:
            return {"error": "MCP server not available"}

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            self._process.stdin.write(json.dumps(payload) + "\n")
            self._process.stdin.flush()
            response_line = self._process.stdout.readline()
            return json.loads(response_line) if response_line else {"error": "no response"}
        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            return {"error": str(e)}


_mcp = AlpacaMCPBridge()
