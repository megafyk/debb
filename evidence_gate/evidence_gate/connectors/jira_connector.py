"""Jira connector — fetches and sanitizes tickets via the REST API."""
from __future__ import annotations

import httpx

from evidence_gate.config import Settings
from evidence_gate.connectors.auth import jira_basic_auth_header
from evidence_gate.contracts import SanitizedTicketContext, SensitiveRef
from evidence_gate.redaction.jira_redactor import redact_text
from evidence_gate.redaction.pii_extractor import ExtractedRef, extract_sensitive_values
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


_FIXTURE_TICKET = {
    "key": "BUG-123",
    "fields": {
        "summary": "Login fails for users with phone numbers missing leading zero",
        "issuetype": {"name": "Bug"},
        "priority": {"name": "High"},
        "status": {"name": "Open"},
        "labels": ["login", "phone-normalization"],
        "components": [{"name": "login-service"}, {"name": "account-service"}],
        "description": "Users in Thailand report login failures. The phone number 812345678 (missing leading 0) causes account lookup to fail. Customer: somchai@example.com, phone: +66812345678. Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736",
        "comment": {
            "comments": [
                {"body": "Checked logs, seeing ACCOUNT_LOOKUP_FAILED for phone hash mismatch. Contact: support@company.com"},
                {"body": "Might be related to BUG-100. The normalizer strips +66 but doesn't add back the leading 0."},
            ]
        },
        "created": "2026-04-30T08:00:00.000+0000",
        "updated": "2026-04-30T10:00:00.000+0000",
        "issuelinks": [],
        "subtasks": [],
    },
}

# Allowlisted Jira REST fields — only these are requested
_JIRA_FIELDS = (
    "summary,issuetype,priority,status,labels,components,"
    "description,comment,created,updated,resolutiondate,"
    "issuelinks,subtasks,parent,assignee,reporter,attachment"
)


def _name(obj: dict | None) -> str:
    return obj.get("name", "") if isinstance(obj, dict) else ""


def _component_names(comps: list | None) -> list[str]:
    if not comps:
        return []
    return [c["name"] for c in comps if isinstance(c, dict) and "name" in c]


def _comment_bodies(comment_field: dict | None) -> list[str]:
    if not comment_field:
        return []
    comments = comment_field.get("comments", [])
    return [c.get("body", "") for c in comments if isinstance(c, dict)]


def _subtask_keys(subtasks: list | None) -> list[str]:
    if not subtasks:
        return []
    return [s["key"] if isinstance(s, dict) else str(s) for s in subtasks]


def _link_summaries(links: list | None) -> list[dict]:
    if not links:
        return []
    out = []
    for link in links:
        if not isinstance(link, dict):
            continue
        entry: dict = {}
        if "type" in link and isinstance(link["type"], dict):
            entry["type"] = link["type"].get("name", "")
        if "outwardIssue" in link and isinstance(link["outwardIssue"], dict):
            entry["outward_key"] = link["outwardIssue"].get("key", "")
        if "inwardIssue" in link and isinstance(link["inwardIssue"], dict):
            entry["inward_key"] = link["inwardIssue"].get("key", "")
        out.append(entry)
    return out


def map_jira_fields(ticket_id: str, raw_issue: dict) -> SanitizedTicketContext:
    """Map raw Jira REST JSON to SanitizedTicketContext (allowlisted fields only)."""
    fields = raw_issue.get("fields", {})
    return SanitizedTicketContext(
        ticket_id=ticket_id,
        summary=fields.get("summary", ""),
        issue_type=_name(fields.get("issuetype")),
        priority=_name(fields.get("priority")),
        status=_name(fields.get("status")),
        labels=fields.get("labels", []),
        components=_component_names(fields.get("components")),
        description_sanitized=fields.get("description", "") or "",
        comments_sanitized=_comment_bodies(fields.get("comment")),
        created=fields.get("created"),
        updated=fields.get("updated"),
        issue_links=_link_summaries(fields.get("issuelinks")),
        subtasks=_subtask_keys(fields.get("subtasks")),
    )


def _to_sensitive_refs(extracted: list[ExtractedRef]) -> list[SensitiveRef]:
    return [SensitiveRef(value_ref=e.value_ref, field_type=e.field_type) for e in extracted]


class JiraConnector:
    """Fetches Jira tickets. Uses real REST API when configured, fixture otherwise."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    @property
    def is_live(self) -> bool:
        return bool(self._settings and self._settings.jira_base_url)

    def fetch_raw(self, ticket_id: str) -> dict:
        """Fetch raw Jira issue JSON. Only called internally by evidence_gate."""
        if not self.is_live:
            return _FIXTURE_TICKET

        s = self._settings
        assert s is not None
        headers = jira_basic_auth_header(s)
        url = f"{s.jira_base_url.rstrip('/')}/rest/api/2/issue/{ticket_id}"
        resp = httpx.get(url, headers=headers, params={"fields": _JIRA_FIELDS}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_and_sanitize(
        self,
        ticket_id: str,
        session_id: str = "",
        sensitive_store: SensitiveValueStore | None = None,
    ) -> tuple[SanitizedTicketContext, list[SensitiveRef]]:
        """Fetch, map allowlisted fields, extract sensitive values, redact."""
        raw = self.fetch_raw(ticket_id)
        ticket = map_jira_fields(ticket_id, raw)

        sensitive_refs: list[SensitiveRef] = []
        if session_id and sensitive_store:
            desc, desc_refs = extract_sensitive_values(
                ticket.description_sanitized, session_id, sensitive_store,
            )
            ticket.description_sanitized = desc
            sensitive_refs.extend(_to_sensitive_refs(desc_refs))

            new_comments = []
            for comment in ticket.comments_sanitized:
                redacted_comment, comment_refs = extract_sensitive_values(
                    comment, session_id, sensitive_store,
                )
                new_comments.append(redacted_comment)
                sensitive_refs.extend(_to_sensitive_refs(comment_refs))
            ticket.comments_sanitized = new_comments

        # Final pass: catch anything the extractor missed in free-text fields.
        # `summary` and `labels` come from allowlisted but still untrusted Jira
        # input — Jira summaries occasionally contain emails/phones pasted from
        # reporters, and labels are agent-visible after this returns.
        ticket.summary = redact_text(ticket.summary)
        ticket.labels = [redact_text(label) for label in ticket.labels]
        ticket.description_sanitized = redact_text(ticket.description_sanitized)
        ticket.comments_sanitized = [redact_text(c) for c in ticket.comments_sanitized]

        return ticket, sensitive_refs
