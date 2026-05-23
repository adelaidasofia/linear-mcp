"""JSONL audit log. Same shape as slack-mcp / whatsapp-mcp.

Every tool call appends one line: ts, tool, params (redacted),
result_summary, duration_ms, error. Path overridable via
LINEAR_MCP_AUDIT_LOG_PATH env. Disable with LINEAR_MCP_AUDIT_LOG=false.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path.home() / ".claude" / "linear-mcp" / "audit.log"
AUDIT_PATH = Path(os.environ.get("LINEAR_MCP_AUDIT_LOG_PATH", str(DEFAULT_PATH)))
AUDIT_ENABLED = os.environ.get("LINEAR_MCP_AUDIT_LOG", "true").lower() in ("1", "true", "yes", "on")


def audit(tool: str, params: dict[str, Any], result_summary: str,
          duration_ms: int, error: str | None = None) -> None:
    if not AUDIT_ENABLED:
        return
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.time(),
            "tool": tool,
            "params": _redact(params),
            "result_summary": result_summary,
            "duration_ms": duration_ms,
            "error": error,
        }
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    """Strip token-like values."""
    redacted: dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, str) and (v.startswith("lin_api_") or k.lower() in ("token", "pat", "api_key", "secret")):
            redacted[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 500:
            redacted[k] = v[:500] + f"...[{len(v) - 500} more chars]"
        else:
            redacted[k] = v
    return redacted
