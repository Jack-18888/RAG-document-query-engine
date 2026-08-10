"""Parser registry facade.

Importing this package imports all format-specific parser modules so their
``@register`` decorators populate the registry.
"""

from app.parsers import docx_parser, html_parser, markdown_parser, pdf_parser  # noqa: F401
from app.parsers.base import (
    Heading,
    Paragraph,
    ParsedDocument,
    Parser,
    ParserError,
    UnsupportedFormatError,
)
from app.parsers.registry import get_parser, parse, supported_extensions

__all__ = [
    "Heading",
    "Paragraph",
    "ParsedDocument",
    "Parser",
    "ParserError",
    "UnsupportedFormatError",
    "get_parser",
    "parse",
    "supported_extensions",
]
