from __future__ import annotations

from pathlib import Path

import mistune

from app.parsers.base import Heading, Paragraph, ParsedDocument, Parser
from app.parsers.registry import register

_markdown = mistune.Markdown()


def _inline_text(node: dict) -> str:
    parts: list[str] = []
    for child in node.get("children", []):
        if child.get("type") == "text":
            parts.append(child.get("raw", ""))
        elif "children" in child:
            parts.append(_inline_text(child))
    return "".join(parts)


def _block_text(node: dict) -> str:
    text = _inline_text(node)
    if text:
        return text
    return node.get("raw", "").strip()


def _walk(node: dict, blocks: list[Heading | Paragraph]) -> None:
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
    def parse(self, path: Path) -> ParsedDocument:
        text = path.read_text(encoding="utf-8")
        return _parse(text)
