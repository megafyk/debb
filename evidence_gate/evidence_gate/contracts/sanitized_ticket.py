from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SanitizedTicketContext(BaseModel):
    ticket_id: str
    summary: str
    issue_type: str
    priority: str
    status: str
    labels: list[str] = []
    components: list[str] = []
    description_sanitized: str = ""
    comments_sanitized: list[str] = []
    created: datetime | None = None
    updated: datetime | None = None
    issue_links: list[dict] = []
    subtasks: list[str] = []
