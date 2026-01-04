"""
Custom exception classes for CBZ Convertor.
"""


class CBZConvertorError(Exception):
    """Base exception for CBZ Convertor errors."""
    pass


class ChapterExtractionError(CBZConvertorError):
    """Raised when chapter number cannot be extracted from filename."""
    pass


class InvalidJSONError(CBZConvertorError):
    """Raised when JSON structure is invalid."""
    pass


class CBZProcessingError(CBZConvertorError):
    """Raised when CBZ file processing fails."""
    pass

