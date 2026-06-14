"""
Content redaction service for secure messaging.

Redacts sensitive patterns from messages before logging or sending to providers.
"""
from __future__ import annotations

import re


# Sensitive patterns to redact (case-insensitive matching)
SENSITIVE_PATTERNS = [
    r"password\s*[=:]\s*[^\s&]+",
    r"passwd\s*[=:]\s*[^\s&]+",
    r"pwd\s*[=:]\s*[^\s&]+",
    r"token\s*[=:]\s*[^\s&]+",
    r"secret\s*[=:]\s*[^\s&]+",
    r"api[_-]?key\s*[=:]\s*[^\s&]+",
    r"authorization\s*[=:]\s*[^\s&]+",
    r"cookie\s*[=:]\s*[^\s&]+",
    r"set-cookie\s*[=:]\s*[^\s&]+",
    r"private[_-]?key\s*[=:]\s*[^\s&]+",
    r"client[_-]?secret\s*[=:]\s*[^\s&]+",
    r'"password"\s*:\s*"[^"]+"',
    r'"token"\s*:\s*"[^"]+"',
    r'"secret"\s*:\s*"[^"]+"',
    r'"api[_-]?key"\s*:\s*"[^"]+"',
    r'"authorization"\s*:\s*"[^"]+"',
]

# HTTP header patterns (case-insensitive)
HEADER_PATTERNS = [
    (r"(?i)(authorization:\s*bearer\s+)[^\s]+", r"\1***REDACTED***"),
    (r"(?i)(authorization:\s*basic\s+)[^\s]+", r"\1***REDACTED***"),
    (r"(?i)(cookie:\s*)[^\r\n]+", r"\1***REDACTED***"),
    (r"(?i)(set-cookie:\s*)[^\r\n]+", r"\1***REDACTED***"),
]

REDACTION_MARKER = "***REDACTED***"


def redact_sensitive_content(content: str) -> str:
    """
    Redact sensitive patterns from content.

    Replaces sensitive key/value patterns and HTTP headers with ***REDACTED***.
    Handles key=value, key: value, JSON "key": "value", and HTTP headers.

    Args:
        content (str): Original content that may contain sensitive data.

    Returns:
        str: Content with sensitive patterns redacted.

    Side Effects:
        None.
    """
    if not content:
        return content

    result = content

    # Redact key=value and key:value patterns
    for pattern in SENSITIVE_PATTERNS:
        try:
            result = re.sub(
                pattern,
                lambda m: f"{m.group(0).split('=')[0].split(':')[0]}={REDACTION_MARKER}"
                if "=" in m.group(0)
                else f"{m.group(0).split(':')[0]}: {REDACTION_MARKER}",
                result,
                flags=re.IGNORECASE,
            )
        except re.error:
            # Skip invalid patterns
            continue

    # Handle JSON-style patterns separately for better accuracy
    json_patterns = [
        (r'(?i)("password"\s*:\s*")[^"]+("', r"\1***REDACTED***\2"),
        (r'(?i)("token"\s*:\s*")[^"]+("', r"\1***REDACTED***\2"),
        (r'(?i)("secret"\s*:\s*")[^"]+("', r"\1***REDACTED***\2"),
        (r'(?i)("api[_-]?key"\s*:\s*")[^"]+("', r"\1***REDACTED***\2"),
        (r'(?i)("authorization"\s*:\s*")[^"]+("', r"\1***REDACTED***\2"),
    ]

    for pattern, replacement in json_patterns:
        try:
            result = re.sub(pattern, replacement, result)
        except re.error:
            continue

    # Redact HTTP headers
    for pattern, replacement in HEADER_PATTERNS:
        try:
            result = re.sub(pattern, replacement, result)
        except re.error:
            continue

    return result
