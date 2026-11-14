"""Indian mobile number handling shared by registration and profile completion."""

import re

# Spaces and hyphens are what people type between digit groups; a leading +91 is the country code.
_SEPARATORS = re.compile(r"[\s-]")
# re.ASCII: without it \d also matches digits from other scripts (e.g. Devanagari), which we must not store.
_INDIAN_MOBILE = re.compile(r"^[6-9]\d{9}$", re.ASCII)


def normalize_phone(value: str) -> str:
    """Strip separators and a leading +91, returning the bare number (not yet validated)."""
    text = _SEPARATORS.sub("", value)
    return text[3:] if text.startswith("+91") else text


def validate_indian_mobile(value: str) -> str:
    """Return the normalized 10-digit number or raise ValueError (pydantic turns that into a 422)."""
    number = normalize_phone(value)
    if not _INDIAN_MOBILE.fullmatch(number):
        raise ValueError("Enter a valid 10-digit Indian mobile number starting with 6, 7, 8 or 9")
    return number
