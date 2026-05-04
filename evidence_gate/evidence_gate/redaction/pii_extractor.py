from __future__ import annotations

import re
from typing import NamedTuple

from evidence_gate.sessions.sensitive_value_store import SensitiveValueStore


class ExtractedRef(NamedTuple):
    value_ref: str
    field_type: str
    raw_value: str


# Patterns that identify extractable sensitive values
_EXTRACTORS = [
    ("email", re.compile(r"\b([\w.+-]+@[\w-]+\.[\w.-]+)\b")),
    ("phone_number", re.compile(r"(\+?\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4})")),
]


def extract_sensitive_values(
    text: str,
    session_id: str,
    sensitive_store: SensitiveValueStore,
) -> tuple[str, list[ExtractedRef]]:
    """Extract PII from text, store as secure refs, return redacted text and refs."""
    refs: list[ExtractedRef] = []
    seen: dict[str, str] = {}  # raw_value -> value_ref (dedup)

    for field_type, pattern in _EXTRACTORS:
        def _replace(match: re.Match, _ft: str = field_type) -> str:
            raw = match.group(0)
            if raw in seen:
                ref = seen[raw]
            else:
                ref = sensitive_store.store(session_id, _ft, raw)
                seen[raw] = ref
                refs.append(ExtractedRef(value_ref=ref, field_type=_ft, raw_value=raw))
            return f"[{ref}]"

        text = pattern.sub(_replace, text)

    return text, refs
