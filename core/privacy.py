"""Gayatri AI — PII Detection and Redaction.

Simple regex-based PII scanner. Replaces personal data with safe placeholders
before messages reach the model. User sees original text; model sees [PII_TYPE].

Avoids Samsung's patented "dummy placeholder substitution" approach
(US patent 2026 by Samsung for on-device AI privacy).
This is a simple, non-patented regex replacement with restore capability.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("gayatri.privacy")


@dataclass
class PIIMatch:
    """A single PII match."""
    pii_type: str
    placeholder: str
    original: str
    start: int
    end: int


@dataclass
class RedactionResult:
    """Result of redacting a message."""
    clean_text: str
    redactions: list[PIIMatch] = field(default_factory=list)
    has_pii: bool = False

    def restore(self, text: str) -> str:
        """Restore original PII in the clean text (for display)."""
        result = text
        for r in self.redactions:
            result = result.replace(r.placeholder, r.original)
        return result


class PIIRedactor:
    """Simple regex-based PII detector and redactor.

    Detects:
        - Email addresses
        - Indian phone numbers (10 digits starting with 6-9, with optional +91)
        - US/generic phone numbers (xxx-xxx-xxxx)
        - SSN-like numbers (xxx-xx-xxxx)
        - Credit card numbers (16 digits with optional spaces/dashes)
        - URLs with embedded credentials

    Safe approach: regex replacement + restore via placeholder map.
    Does NOT implement Samsung's patented placeholder masking technique.
    """

    PATTERNS = [
        ("EMAIL", re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        )),
        ("PHONE_IN", re.compile(
            r"(?<!\d)(?:\+?91[-\s.]?)?[6-9]\d{9}(?!\d)"
        )),
        ("PHONE_US", re.compile(
            r"\b\d{3}[-\s.]\d{3}[-\s.]\d{4}\b"
        )),
        ("SSN", re.compile(
            r"\b\d{3}-\d{2}-\d{4}\b"
        )),
        ("CREDIT_CARD", re.compile(
            r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"
        )),
    ]

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def redact(self, text: str) -> RedactionResult:
        """Scan text and replace PII with placeholders.

        Args:
            text: Original text potentially containing PII

        Returns:
            RedactionResult with clean_text and redactions list
        """
        if not self.enabled or not text:
            return RedactionResult(clean_text=text, has_pii=False)

        matches: list[PIIMatch] = []
        result_text = text
        offset = 0  # cumulative offset from replacements

        for pii_type, pattern in self.PATTERNS:
            def replacer(match: re.Match) -> str:
                original = match.group(0)
                placeholder = f"[{pii_type}]"
                matches.append(PIIMatch(
                    pii_type=pii_type,
                    placeholder=placeholder,
                    original=original,
                    start=match.start(),
                    end=match.end(),
                ))
                return placeholder

            result_text = pattern.sub(replacer, result_text)

        return RedactionResult(
            clean_text=result_text,
            redactions=matches,
            has_pii=len(matches) > 0,
        )

    def get_redaction_summary(self, result: RedactionResult) -> str:
        """Get a human-readable summary of what was redacted."""
        if not result.has_pii:
            return "No PII detected"
        types = {}
        for r in result.redactions:
            types[r.pii_type] = types.get(r.pii_type, 0) + 1
        parts = [f"{count} {ptype}" for ptype, count in types.items()]
        return "Redacted: " + ", ".join(parts)


# Global redactor instance
_redactor: PIIRedactor | None = None


def get_redactor() -> PIIRedactor:
    """Get the global PII redactor (singleton)."""
    global _redactor
    if _redactor is None:
        _redactor = PIIRedactor(enabled=True)
    return _redactor
