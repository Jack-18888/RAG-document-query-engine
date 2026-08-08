"""Shared parser interfaces and document block model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ParserError(Exception):
    """Raised when a document cannot be parsed (corrupt/unreadable)."""


class UnsupportedFormatError(Exception):
    """Raised when no parser is registered for a file extension."""


@dataclass(frozen=True)
class Heading:
    """A document heading with its nesting level (1-based)."""

    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    """A plain paragraph of text."""

    text: str


@dataclass(frozen=True)
class ParsedDocument:
    """Normalized document content: flat text plus a block list."""

    text: str
    blocks: list[Heading | Paragraph]


class Parser:
    """Base class for format-specific parsers.

    Subclasses must implement :meth:`parse`, which reads a file at ``path``
    and returns a normalized :class:`ParsedDocument`.
    """

    def parse(self, path: Path) -> ParsedDocument:
        """Parse the file at ``path`` into a normalized document."""
        raise NotImplementedError
