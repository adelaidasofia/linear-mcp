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
    # v0.2 additions
    webhooks,
    notifications,
    attachments,
    relations,
    agent_sessions,
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
    # v0.2
    webhooks.register(mcp)
    notifications.register(mcp)
    attachments.register(mcp)
    relations.register(mcp)
    agent_sessions.register(mcp)
