from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from app.parsers.base import Heading, Paragraph, ParsedDocument, Parser
from app.parsers.registry import register

_IGNORED_TAGS = {"script", "style", "nav", "noscript", "template", "head"}
_HEADING_LEVELS = {f"h{i}": i for i in range(1, 7)}


class _ContentExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Heading | Paragraph] = []
        self._ignore_depth = 0
        self._heading_stack: list[int] = []
        self._text: list[str] = []
        self._current_heading: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _IGNORED_TAGS:
            self._ignore_depth += 1
        elif tag in _HEADING_LEVELS:
            self._flush_text()
            self._current_heading = _HEADING_LEVELS[tag]
        elif tag in {"p", "div", "li", "tr", "blockquote", "pre", "section"}:
            self._flush_text()

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORED_TAGS:
            self._ignore_depth = max(0, self._ignore_depth - 1)
        elif tag in _HEADING_LEVELS:
            self._flush_text()
            self._current_heading = None
        elif tag in {"p", "div", "li", "tr", "blockquote", "pre", "section"}:
            self._flush_text()

    def handle_data(self, data: str) -> None:
        if self._ignore_depth == 0:
            text = " ".join(data.split())
            if text:
                self._text.append(text)

    def _flush_text(self) -> None:
        text = " ".join(self._text).strip()
        self._text = []
        if not text:
            return
        if self._current_heading is not None:
            self.blocks.append(Heading(level=self._current_heading, text=text))
        else:
            self.blocks.append(Paragraph(text))


@register("html")
@register("htm")
class HtmlParser(Parser):
    def parse(self, path: Path) -> ParsedDocument:
        content = path.read_text(encoding="utf-8", errors="replace")
        extractor = _ContentExtractor()
        extractor.feed(content)
        blocks = extractor.blocks
        return ParsedDocument(
            text="\n\n".join(block.text for block in blocks),
            blocks=blocks,
        )
