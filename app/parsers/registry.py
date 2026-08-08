"""Registry mapping file extensions to their parser classes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.parsers.base import ParsedDocument, Parser, UnsupportedFormatError

ParserFactory = Callable[[], Parser]

_REGISTRY: dict[str, ParserFactory] = {}


def register(extension: str) -> Callable[[ParserFactory], ParserFactory]:
    """Decorator that registers a parser class for the given extension."""

    def decorator(factory: ParserFactory) -> ParserFactory:
        _REGISTRY[extension.lower().lstrip(".")] = factory
        return factory

    return decorator


def get_parser(extension: str) -> Parser:
    """Instantiate the parser registered for ``extension``.

    Raises :class:`UnsupportedFormatError` when no parser is registered.
    """
    key = extension.lower().lstrip(".")
    factory = _REGISTRY.get(key)
    if factory is None:
        raise UnsupportedFormatError(f"unsupported file extension: {extension}")
    return factory()


def parse(extension: str, path: Path) -> ParsedDocument:
    """Parse the file at ``path`` using the parser for ``extension``."""
    return get_parser(extension).parse(path)


def supported_extensions() -> frozenset[str]:
    """Return the set of registered, supported file extensions."""
    return frozenset(_REGISTRY)
