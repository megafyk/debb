from __future__ import annotations

import httpx

from evidence_gate.app.config import Settings
from evidence_gate.connectors.auth import jira_basic_auth_header
from evidence_gate.connectors.jira_field_mapper import map_jira_fields
from evidence_gate.contracts.evidence_session import SensitiveRef
from evidence_gate.contracts.sanitized_ticket import SanitizedTicketContext
from evidence_gate.redaction.jira_redactor import redact_text
from evidence_gate.redaction.pii_extractor import ExtractedRef, extract_sensitive_values
from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore


# Fixture data for testing / when no Jira configured
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

# Jira REST fields to request (only allowlisted)
_JIRA_FIELDS = (
    "summary,issuetype,priority,status,labels,components,"
    "description,comment,created,updated,resolutiondate,"
    "issuelinks,subtasks,parent,assignee,reporter,attachment"
)


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
        """Fetch, map allowlisted fields, extract sensitive values, redact, return sanitized context."""
        raw = self.fetch_raw(ticket_id)
        ticket = map_jira_fields(ticket_id, raw)

        sensitive_refs: list[SensitiveRef] = []

        # Extract sensitive values if we have a session + store
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

        # Final pass: catch anything the extractor missed
        ticket.description_sanitized = redact_text(ticket.description_sanitized)
        ticket.comments_sanitized = [redact_text(c) for c in ticket.comments_sanitized]

        return ticket, sensitive_refs


def _to_sensitive_refs(extracted: list[ExtractedRef]) -> list[SensitiveRef]:
    return [
        SensitiveRef(value_ref=e.value_ref, field_type=e.field_type)
        for e in extracted
    ]
