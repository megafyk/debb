"""Boundary tests: audit events must not contain credentials or raw secrets."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from evidence_gate.audit.audit_logger import AuditLogger
from evidence_gate.storage.jsonl_event_store import JsonlEventStore

_CREDENTIAL_PATTERNS = [
    re.compile(r"(?i)\bpassword\b"),
    re.compile(r"(?i)\bsecret\b"),
    re.compile(r"\bBearer\b"),
    re.compile(r"\b(?:eyJ)[A-Za-z0-9_-]{10,}"),
]


def test_audit_events_have_no_credentials():
    with tempfile.TemporaryDirectory() as tmp:
        audit_path = Path(tmp) / "audit.jsonl"
        store = JsonlEventStore(audit_path)
        logger = AuditLogger(store)

        logger.log("ESESS-1", "session_created", {"ticket_id": "BUG-123"})
        logger.log("ESESS-1", "evidence_requested", {"request_id": "EREQ-abc"})
        logger.log("ESESS-1", "report_submitted", {"report_id": "RPT-def", "confidence": "medium"})

        audit_text = audit_path.read_text()
        for pattern in _CREDENTIAL_PATTERNS:
            assert not pattern.search(audit_text), (
                f"Credential pattern {pattern.pattern!r} found in audit log"
            )


def test_session_created_audit_is_safe():
    with tempfile.TemporaryDirectory() as tmp:
        audit_path = Path(tmp) / "audit.jsonl"
        store = JsonlEventStore(audit_path)
        logger = AuditLogger(store)

        logger.log("ESESS-1", "session_created", {"ticket_id": "BUG-123", "trace_id": "trace-abc"})

        audit_text = audit_path.read_text()
        for pattern in _CREDENTIAL_PATTERNS:
            assert not pattern.search(audit_text), (
                f"Credential pattern {pattern.pattern!r} found in session_created audit event"
            )
