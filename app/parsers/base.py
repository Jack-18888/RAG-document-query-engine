from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ParserError(Exception):
    """Raised when a document cannot be parsed (corrupt/unreadable)."""


class UnsupportedFormatError(Exception):
    """Raised when no parser is registered for a file extension."""


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    blocks: list[Heading | Paragraph]


class Parser:
    def parse(self, path: Path) -> ParsedDocument:
        raise NotImplementedError
