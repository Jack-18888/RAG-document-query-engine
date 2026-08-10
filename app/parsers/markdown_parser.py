"""Parser for ``.md`` files built on mistune."""

from __future__ import annotations

from pathlib import Path

import mistune

from app.parsers.base import Heading, Paragraph, ParsedDocument, Parser
from app.parsers.registry import register

_markdown = mistune.Markdown()


def _inline_text(node: dict) -> str:
    """Concatenate the raw text of a node's inline children."""
    parts: list[str] = []
    for child in node.get("children", []):
        if child.get("type") == "text":
            parts.append(child.get("raw", ""))
        elif "children" in child:
            parts.append(_inline_text(child))
    return "".join(parts)


def _block_text(node: dict) -> str:
    """Return a node's rendered text, falling back to raw content."""
    text = _inline_text(node)
    if text:
        return text
    return node.get("raw", "").strip()


def _walk(node: dict, blocks: list[Heading | Paragraph]) -> None:
    """Recursively convert a mistune AST node into heading/paragraph blocks."""
    kind = node.get("type")
    if kind == "heading":
        blocks.append(Heading(level=node["attrs"]["level"], text=_block_text(node)))
    elif kind == "paragraph":
        blocks.append(Paragraph(_block_text(node)))
    elif kind == "list":
        for item in node.get("children", []):
            if item.get("type") == "list_item":
                blocks.append(Paragraph(_block_text(item)))
    elif kind == "block_code":
        blocks.append(Paragraph(node.get("raw", "").strip()))
    elif kind in {"blockquote", "footnotes"}:
        for child in node.get("children", []):
            if isinstance(child, dict):
                _walk(child, blocks)


def _parse(text: str) -> ParsedDocument:
    """Parse markdown source text into a normalized document."""
    blocks: list[Heading | Paragraph] = []
    nodes, _ = _markdown.parse(text)
    for node in nodes:
        if isinstance(node, dict):
            _walk(node, blocks)
    return ParsedDocument(
        text="\n\n".join(block.text for block in blocks),
        blocks=blocks,
    )


@register("md")
class MarkdownParser(Parser):
    """Parse Markdown documents into headings and paragraphs."""

    def parse(self, path: Path) -> ParsedDocument:
        """Read and normalize the Markdown file at ``path``."""
        text = path.read_text(encoding="utf-8")
        return _parse(text)
