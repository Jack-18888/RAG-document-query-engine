"""Parser for ``.docx`` files built on python-docx."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.base import Heading, ParsedDocument, Parser, ParserError
from app.parsers.base import Paragraph as TextParagraph
from app.parsers.registry import register

_HEADING_STYLE = re.compile(r"^Heading (\d+)$", re.IGNORECASE)
_TITLE_STYLES = {"title", "subtitle"}


def _heading_level(paragraph: Paragraph) -> int | None:
    """Return the 1-based heading level for a paragraph, or None if it is body text."""
    style = paragraph.style
    if style is not None:
        name = (style.name or "").strip()
        match = _HEADING_STYLE.match(name)
        if match:
            return int(match.group(1))
        if name.lower() in _TITLE_STYLES:
            return 1
    p_pr = paragraph._p.pPr
    if p_pr is not None and p_pr.outlineLvl is not None:
        return p_pr.outlineLvl.val + 1
    return None


def _iter_body_items(doc: DocumentObject):
    """Yield the document body's top-level paragraphs and tables in order."""
    parent = doc._body
    for child in parent._element.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _table_to_blocks(table: Table) -> list[TextParagraph]:
    """Flatten a table into one paragraph per non-empty row (cells joined by " | ")."""
    blocks: list[TextParagraph] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        text = " | ".join(cell for cell in cells if cell)
        if text:
            blocks.append(TextParagraph(text))
    return blocks


def _parse_docx(doc: DocumentObject) -> ParsedDocument:
    """Convert a python-docx ``Document`` into heading/paragraph blocks."""
    blocks: list[Heading | TextParagraph] = []
    for item in _iter_body_items(doc):
        if isinstance(item, Paragraph):
            level = _heading_level(item)
            text = item.text.strip()
            if not text:
                continue
            if level is not None:
                blocks.append(Heading(level=level, text=text))
            else:
                blocks.append(TextParagraph(text))
        else:
            blocks.extend(_table_to_blocks(item))
    return ParsedDocument(
        text="\n\n".join(block.text for block in blocks),
        blocks=blocks,
    )


@register("docx")
class DocxParser(Parser):
    """Parse ``.docx`` documents into headings and paragraphs."""

    def parse(self, path: Path) -> ParsedDocument:
        """Read and normalize the ``.docx`` file at ``path``.

        Raises :class:`ParserError` when the file cannot be read.
        """
        try:
            doc = Document(str(path))
        except Exception as exc:
            raise ParserError(f"cannot read docx file: {exc}") from exc
        return _parse_docx(doc)
