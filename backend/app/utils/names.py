import re
import unicodedata

# Letters (any script), combining marks, spaces and . ' ’ - . Nothing else: no digits, no < > / : @.
_PUNCTUATION = set(" .'’-")

# Something that reads as a web address: "http", "www", or a dot straight into two or more letters ("x.com").
_URL_LIKE = re.compile(r"(?i)\b(?:https?|ftp)\b|\bwww\b|[^\W\d_]\.[^\W\d_]{2,}")

_URL = re.compile(r"(?i)\b(?:https?://|ftp://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|in|io|co|me|app|dev|xyz|link|ly|info)\b\S*")


def _allowed(char: str) -> bool:
    return char.isalpha() or unicodedata.category(char).startswith("M") or char in _PUNCTUATION


def is_valid_name(name: str) -> bool:
    """True when a person's name uses only letters, spaces and . ' - and does not look like a link."""
    text = name.strip()
    return bool(text) and all(_allowed(char) for char in text) and not _URL_LIKE.search(text)


def clean_name(name: str | None, limit: int = 100) -> str:
    """Make a name that came from elsewhere (Google) safe to show: drop link-like words and disallowed characters."""
    words = [word for word in (name or "").split() if not _URL_LIKE.search(word)]
    text = "".join(char for char in " ".join(words) if _allowed(char))
    return " ".join(text.split())[:limit].strip()


def plain_preview(text: str | None, limit: int = 80) -> str:
    """A short plain-text preview of something a member typed: links become the word "link"."""
    flat = " ".join((text or "").split())
    flat = _URL.sub("link", flat)
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."
