"""
Utility functions for CBZ Convertor.
"""

import sys
from typing import Any, TextIO

EMOJI_PREFIXES = {
    "ok": "✅",
    "done": "🎉",
    "warning": "⚠️",
    "error": "❌",
    "info": "📘",
}

ASCII_PREFIXES = {
    "ok": "OK",
    "done": "Done",
    "warning": "Warning",
    "error": "Error",
    "info": "Info",
}


def stream_supports_emoji(stream: TextIO | None = None) -> bool:
    """Return True when the stream encoding supports writing emoji characters."""
    if stream is None:
        stream = sys.stdout

    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        "✅".encode(encoding)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


def console_prefix(kind: str, stream: TextIO | None = None) -> str:
    """Return an emoji prefix when supported, otherwise an ASCII fallback."""
    if stream_supports_emoji(stream):
        return EMOJI_PREFIXES.get(kind, "")

    return ASCII_PREFIXES.get(kind, "")

def get_nested_value(data: dict, *keys: str, default: Any = None) -> Any:
    """
    Safely extract a value from nested dictionaries.

    Args:
        data: The dictionary to extract from
        *keys: Variable number of keys for nested access
        default: Default value if key path doesn't exist or value is falsy

    Returns:
        The value at the nested key path, or default if not found or falsy

    Examples:
        >>> data = {"series": {"title": "My Series", "language": "en"}}
        >>> get_nested_value(data, "series", "title")
        'My Series'
        >>> get_nested_value(data, "series", "author", default="Unknown")
        'Unknown'
        >>> get_nested_value(data, "series", "title", default="Fallback")
        'My Series'
    """
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]

    # Return default if value is falsy (None, empty string, etc.)
    return current if current else default

