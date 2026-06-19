from __future__ import annotations

import re


# Simple PII patterns for MVP.
# Phone matchers require a real signal (`+` country prefix, a separator, or
# the Vietnamese 0-mobile prefix). A bare 8-13 digit run is NOT treated as a
# phone: that shape collides with Unix-ms timestamps (e.g. `startTime`,
# `endTime` in STANDARD_LOG payloads), and over-redacting those destroys
# engineer-useful timing data.
_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\+\d{6,15}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b\d{2,4}[-.\s]\d{3,4}[-.\s]?\d{3,4}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b0\d{9,10}\b"), "[REDACTED_PHONE]"),
    # Vietnamese international format embedded in JSON / logs (no `+` prefix):
    # `"msisdn":"84974515324"`. The 11-12 digit start-with-84 shape was
    # observed leaking through Quickwit message bodies and Metabase
    # log_central rows in TTSTK-3919 and XLSCVD-218 evidence packages.
    # Length stays under 13 to avoid colliding with Unix-ms timestamps.
    (re.compile(r"\b84\d{9,10}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b(?:eyJ|Bearer\s+eyJ)[A-Za-z0-9_-]+\.?[A-Za-z0-9_-]*\.?[A-Za-z0-9_-]*\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"), "[REDACTED_CREDENTIAL]"),
]


def redact_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: object) -> object:
    """Recursively redact strings inside dicts/lists; leave other types alone."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        # Redact string keys too: log/DB payloads sometimes key a nested object
        # by the PII itself (e.g. a per-MSISDN or per-email map), and an
        # unredacted key would flow into the masked package verbatim.
        return {
            (redact_text(k) if isinstance(k, str) else k): redact_value(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value
