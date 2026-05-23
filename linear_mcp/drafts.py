"""Draft+confirm pattern for destructive Linear operations.

Linear's writes split into two classes:

  - Routine writes (save_issue create/update, save_comment, save_project
    fields, status updates, label create) — go through immediately;
    Linear's own UI does not require confirmation for these.

  - Destructive transitions (issue archival, project cancel/archive,
    initiative archive, milestone delete) — go through the draft+confirm
    flow. The tool stages the operation, returns a draft_id with a
    preview of what will change. Nothing hits Linear until
    confirm_destructive(draft_id) is called.

Mirror of slack-mcp / whatsapp-mcp draft store, simplified: a draft
carries a `kind` and an `op` callable description so confirm can dispatch
without re-resolving anything.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

DRAFT_TTL_SECONDS = int(os.environ.get("LINEAR_MCP_DRAFT_TTL_SECONDS", "3600"))
DRAFT_LOG_PATH = Path(os.environ.get(
    "LINEAR_MCP_DRAFT_LOG_PATH",
    str(Path.home() / ".claude" / "linear-mcp" / "drafts.log"),
))


@dataclass
class Draft:
    draft_id: str
    workspace: str
    kind: str          # archive_issue | cancel_project | archive_project | archive_initiative | delete_milestone
    target_id: str     # entity id being changed
    target_label: str  # human-readable identifier (e.g. "ONDE-123: ...")
    preview: dict[str, Any]  # { before: {...}, after: {...} }
    created_at: float = field(default_factory=time.time)
    confirmed: bool = False
    cancelled: bool = False

    def expires_at(self) -> float:
        return self.created_at + DRAFT_TTL_SECONDS

    def is_expired(self) -> bool:
        return time.time() > self.expires_at()


class DraftStore:
    def __init__(self) -> None:
        self._drafts: dict[str, Draft] = {}
        self._lock = threading.Lock()

    def create(self, workspace: str, kind: str, target_id: str,
               target_label: str, preview: dict[str, Any]) -> Draft:
        with self._lock:
            draft = Draft(
                draft_id=uuid.uuid4().hex,
                workspace=workspace,
                kind=kind,
                target_id=target_id,
                target_label=target_label,
                preview=preview,
            )
            self._drafts[draft.draft_id] = draft
            self._append_log("create", draft)
            return draft

    def get(self, draft_id: str) -> Draft:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            if draft.is_expired():
                raise ValueError(f"draft expired: {draft_id}")
            if draft.confirmed:
                raise ValueError(f"draft already confirmed: {draft_id}")
            if draft.cancelled:
                raise ValueError(f"draft cancelled: {draft_id}")
            return draft

    def confirm(self, draft_id: str) -> Draft:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            if draft.is_expired():
                raise ValueError(f"draft expired: {draft_id}")
            if draft.confirmed:
                raise ValueError(f"draft already confirmed: {draft_id}")
            if draft.cancelled:
                raise ValueError(f"draft cancelled: {draft_id}")
            draft.confirmed = True
            self._append_log("confirm", draft)
            return draft

    def cancel(self, draft_id: str) -> Draft:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise KeyError(f"draft not found: {draft_id}")
            if draft.confirmed:
                raise ValueError(f"draft already confirmed: {draft_id}")
            draft.cancelled = True
            self._append_log("cancel", draft)
            return draft

    def size(self) -> int:
        with self._lock:
            return sum(
                1 for d in self._drafts.values()
                if not d.confirmed and not d.cancelled and not d.is_expired()
            )

    def _append_log(self, event: str, draft: Draft) -> None:
        try:
            DRAFT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {"event": event, "ts": time.time(), **asdict(draft)}
            with open(DRAFT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass


STORE = DraftStore()
