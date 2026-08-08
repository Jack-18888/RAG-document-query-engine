"""Parser for ``.pdf`` files built on pypdf."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.parsers.base import Paragraph, ParsedDocument, Parser, ParserError
from app.parsers.registry import register


def _group_paragraphs(lines: list[str]) -> list[str]:
    """Merge consecutive non-empty lines into paragraphs, split on blank lines."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
        else:
            current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


@register("pdf")
class PdfParser(Parser):
    """Parse PDF documents into paragraphs (headings are not detected)."""

    def parse(self, path: Path) -> ParsedDocument:
        """Extract text from the PDF file at ``path``.

        Raises :class:`ParserError` when the file cannot be read or its text
        cannot be extracted.
        """
        try:
            reader = PdfReader(str(path))
        except PdfReadError as exc:
            raise ParserError(f"cannot read pdf file: {exc}") from exc

        lines: list[str] = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                raise ParserError(f"cannot extract text from pdf: {exc}") from exc
            lines.extend(page_text.splitlines())

        paragraphs = _group_paragraphs(lines)
        blocks = [Paragraph(text) for text in paragraphs]
        return ParsedDocument(
            text="\n\n".join(paragraphs),
            blocks=blocks,
        )
