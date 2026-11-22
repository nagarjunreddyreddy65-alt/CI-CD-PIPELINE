"""String utilities, formatting, and sanitization."""

import re


def sanitize_string(text: str) -> str:
    """Strips leading/trailing whitespace and removes control characters."""
    if not isinstance(text, str):
        return ""
    # Strip non-printable ASCII
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)
    return cleaned.strip()


def slugify(text: str) -> str:
    """Converts a string into a URL-friendly slug."""
    text = sanitize_string(text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def truncate(text: str, max_length: int = 50, ellipsis: str = "...") -> str:
    """Truncates text to maximum length with ellipsis."""
    if len(text) <= max_length:
        return text
    cutoff = max_length - len(ellipsis)
    return text[:cutoff] + ellipsis
