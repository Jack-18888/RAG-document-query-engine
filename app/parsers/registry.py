from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.parsers.base import ParsedDocument, Parser, UnsupportedFormatError

ParserFactory = Callable[[], Parser]

_REGISTRY: dict[str, ParserFactory] = {}


def register(extension: str) -> Callable[[ParserFactory], ParserFactory]:
    def decorator(factory: ParserFactory) -> ParserFactory:
        _REGISTRY[extension.lower().lstrip(".")] = factory
        return factory

    return decorator


def get_parser(extension: str) -> Parser:
    key = extension.lower().lstrip(".")
    factory = _REGISTRY.get(key)
    if factory is None:
        raise UnsupportedFormatError(f"unsupported file extension: {extension}")
    return factory()


def parse(extension: str, path: Path) -> ParsedDocument:
    return get_parser(extension).parse(path)


def supported_extensions() -> frozenset[str]:
    return frozenset(_REGISTRY)
