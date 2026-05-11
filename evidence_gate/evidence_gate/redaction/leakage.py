"""Shared leakage-detection patterns for plan safety + report review."""
import re

PII_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "raw email detected"),
    # Phone: require either a `+` country-code prefix or at least one
    # separator inside. A bare 8-digit run with no separator is not a
    # phone signal and matches auto-generated id tails like
    # `AUD-12345678`, which makes the safety check randomly flag IDs.
    (re.compile(r"\+\d{6,15}\b"), "raw phone number detected"),
    (re.compile(r"\b\d{2,4}[-.\s]\d{3,4}[-.\s]?\d{3,4}\b"), "raw phone number detected"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "raw SSN detected"),
]

CREDENTIAL_PATTERNS = [
    (re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key)\s*[:=]\s*\S+"), "credential assignment detected"),
    (re.compile(r"\b(?:eyJ)[A-Za-z0-9_-]{10,}"), "JWT/token detected"),
    (re.compile(r"(?i)(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{8,}"), "auth header detected"),
]


def collect_text(obj: object, depth: int = 0) -> str:
    """Recursively collect all string values from a dict/list, joined with spaces."""
    if depth > 10:
        return ""
    if isinstance(obj, str):
        return obj + " "
    if isinstance(obj, dict):
        return " ".join(collect_text(v, depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(collect_text(item, depth + 1) for item in obj)
    return ""
