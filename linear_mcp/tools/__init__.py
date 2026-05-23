"""Tool modules. Each exports register(mcp) which wires its tools to the
FastMCP instance."""

from . import (
    workspaces,
    teams,
    users,
    projects,
    initiatives,
    issues,
    cycles,
    milestones,
    statuses,
    labels,
    comments,
    documents,
    status_updates,
    search,
)


def register_all(mcp) -> None:
    workspaces.register(mcp)
    teams.register(mcp)
    users.register(mcp)
    projects.register(mcp)
    initiatives.register(mcp)
    issues.register(mcp)
    cycles.register(mcp)
    milestones.register(mcp)
    statuses.register(mcp)
    labels.register(mcp)
    comments.register(mcp)
    documents.register(mcp)
    status_updates.register(mcp)
    search.register(mcp)
