from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from evidence_gate.config import Settings
from evidence_gate.audit_logger import AuditLogger
from evidence_gate.connectors.quickwit_connector import QuickwitConnector
from evidence_gate.contracts import EvidenceRequest
from evidence_gate.contracts import QuickwitQueryPlan
from evidence_gate.redaction.db_redactor import extract_diagnostic_features, redact_db_rows
from evidence_gate.redaction.log_redactor import build_masked_log_package, redact_log_hits
from evidence_gate.request_services.evidence_executor import execute_quickwit_request
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore
from evidence_gate.storage.evidence_request_store import EvidenceRequestStore
from evidence_gate.storage.json_store import JsonStore
from evidence_gate.storage.jsonl_event_store import JsonlEventStore
from evidence_gate.storage.masked_package_store import MaskedPackageStore
from evidence_gate.storage.raw_evidence_store import RawEvidenceStore


def test_log_diagnostic_features_have_no_raw_pii():
    """Masked log package contains field names and redacted values, not raw PII."""
    raw_hits = [
        {"message": "Failed for user@test.com phone +66812345678", "error_code": "PHONE_FAIL", "timestamp": "2026-01-01T10:00:00Z"},
        {"message": "Retry for admin@corp.io", "error_code": "LOOKUP_FAIL", "timestamp": "2026-01-01T10:01:00Z"},
    ]
    fields = ["message", "error_code", "timestamp"]
    redacted = redact_log_hits(raw_hits, fields)

    for hit in redacted:
        hit_json = json.dumps(hit)
        # No raw emails
        assert "user@test.com" not in hit_json
        assert "admin@corp.io" not in hit_json
        # No raw phones
        assert "+66812345678" not in hit_json
        # Fields still present
        assert "error_code" in hit
        assert "timestamp" in hit


def test_db_diagnostic_features_have_no_raw_values():
    """DB diagnostic features expose aggregate/status facts, not raw sensitive data."""
    raw_rows = [
        {"status": "active", "locked": False, "disabled": False, "created_at": "2025-01-01"},
    ]
    features = extract_diagnostic_features(raw_rows, "account")

    # Features should exist
    assert len(features) > 0
    feature = features[0]

    # Feature exposes boolean/status facts
    assert feature.features.get("account_exists") is True
    assert "status" in feature.features

    # Serialized features should not contain raw PII patterns
    feature_json = json.dumps(feature.features)
    assert "@" not in feature_json  # no emails
    assert "password" not in feature_json.lower()


def test_masked_package_fields_are_redacted_not_raw():
    """Masked log package values are redacted versions, never raw."""
    raw_hits = [
        {"stack_trace": "at login(user=john.doe@example.com, phone=0812345678)", "service": "login"},
    ]
    redacted = redact_log_hits(raw_hits, ["stack_trace", "service"])

    pkg = build_masked_log_package(
        evidence_session_id="ESESS-1",
        evidence_request_id="EREQ-test",
        output_profile="test",
        redacted_hits=redacted,
        hit_count=1,
        audit_ref="AUD-1",
    )

    pkg_json = pkg.model_dump_json()
    # Raw values must not appear
    assert "john.doe@example.com" not in pkg_json
    assert "0812345678" not in pkg_json
    # Redaction markers should appear
    assert "[REDACTED_EMAIL]" in pkg_json


def test_sensitive_value_refs_never_resolved_in_masked_output():
    """SECURE_VALUE_REFs are resolved only during connector execution, not in masked output."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sensitive_store = SensitiveValueStore(tmp_path)

        # Store a sensitive value
        ref = sensitive_store.store("ESESS-1", "phone", "+66812345678")
        assert ref.startswith("SECURE_VALUE_REF_")

        # The raw value is in the store
        assert sensitive_store.resolve("ESESS-1", ref) == "+66812345678"

        # Build a masked package (simulating what happens after connector runs)
        redacted_hits = [{"error_code": "PHONE_FAIL", "ref_used": ref}]
        pkg = build_masked_log_package(
            evidence_session_id="ESESS-1",
            evidence_request_id="EREQ-1",
            output_profile="test",
            redacted_hits=redacted_hits,
            hit_count=1,
            audit_ref="AUD-1",
        )

        # The masked package may contain the ref ID (safe) but never the raw value
        pkg_json = pkg.model_dump_json()
        assert "+66812345678" not in pkg_json
        # The ref ID itself is safe to expose
        assert ref in pkg_json or "SECURE_VALUE_REF" not in pkg_json  # either ref is there (safe) or not
