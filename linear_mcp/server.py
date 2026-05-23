"""linear-mcp FastMCP server entry point.

Run with: python3 -m linear_mcp.server

Tools are registered by `tools.register_all(mcp)` at import time. The
WorkspaceRegistry is loaded once at process start; restart Claude Code
(or reload the server) to pick up `admin.env` changes.
"""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP

from . import __version__
from .tools import register_all
from .workspaces import REGISTRY

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("linear-mcp")

mcp = FastMCP("linear-mcp")

register_all(mcp)


def _startup_log() -> None:
    log.info("linear-mcp v%s starting", __version__)
    log.info("workspaces configured: %s", list(REGISTRY.aliases()))
    log.info("primary workspace: %s", REGISTRY.primary)
    if REGISTRY.errors:
        for err in REGISTRY.errors:
            log.warning("config error: %s", err)


_startup_log()


def main() -> None:
    """Console-script entry point."""
    mcp.run()


if __name__ == "__main__":
    main()
