import tempfile
from pathlib import Path

from evidence_gate.redaction.pii_extractor import extract_sensitive_values
from evidence_gate.storage.sensitive_value_store import SensitiveValueStore


def test_extracts_email():
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        text, refs = extract_sensitive_values(
            "Contact user@example.com for help", "ESESS-1", store,
        )

        assert "user@example.com" not in text
        assert len(refs) == 1
        assert refs[0].field_type == "email"
        assert "SECURE_VALUE_REF_email_" in refs[0].value_ref
        # Ref appears in replaced text
        assert refs[0].value_ref in text

        # Sensitive store can resolve it
        resolved = store.resolve("ESESS-1", refs[0].value_ref)
        assert resolved == "user@example.com"


def test_extracts_phone():
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        text, refs = extract_sensitive_values(
            "Call +66812345678 now", "ESESS-1", store,
        )

        assert "+66812345678" not in text
        phone_refs = [r for r in refs if r.field_type == "phone_number"]
        assert len(phone_refs) >= 1


def test_deduplicates_same_value():
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        text, refs = extract_sensitive_values(
            "Email user@test.com and also user@test.com again", "ESESS-1", store,
        )

        # Same email appears twice but should produce only one ref
        assert len(refs) == 1
        assert text.count(refs[0].value_ref) == 2


def test_extracts_multiple_types():
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        text, refs = extract_sensitive_values(
            "User alice@corp.com called from +66812345678", "ESESS-1", store,
        )

        assert "alice@corp.com" not in text
        assert "+66812345678" not in text
        types = {r.field_type for r in refs}
        assert "email" in types
        assert "phone_number" in types


def test_preserves_non_pii_text():
    with tempfile.TemporaryDirectory() as tmp:
        store = SensitiveValueStore(Path(tmp))
        text, refs = extract_sensitive_values(
            "Error ACCOUNT_LOOKUP_FAILED at endpoint /api/login", "ESESS-1", store,
        )

        assert "ACCOUNT_LOOKUP_FAILED" in text
        assert "/api/login" in text
        assert len(refs) == 0
