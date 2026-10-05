from __future__ import annotations

import pytest

from app.parsers import get_parser, parse
from app.parsers.base import Paragraph, ParserError
from app.parsers.pdf_parser import PdfParser


def _make_pdf(objects: list[str]) -> bytes:
    body = b"%PDF-1.4\n"
    offsets: list[int] = []
    for index, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{index} 0 obj\n".encode() + content.encode() + b"\nendobj\n"
    xref_offset = len(body)
    body += f"xref\n0 {len(objects) + 1}\n".encode()
    body += b"0000000000 65535 f \n"
    for offset in offsets:
        body += f"{offset:010d} 00000 n \n".encode()
    body += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return body


def _simple_pdf(text: str) -> bytes:
    pages = (
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        pages,
        f"<< /Length {len(text) + 44} >>\nstream\nBT /F1 12 Tf 72 720 Td ({text}) Tj ET\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    return _make_pdf(objects)


def test_registry_resolves_pdf(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(_simple_pdf("Hello from pdf"))
    assert isinstance(get_parser("pdf"), PdfParser)
    assert isinstance(get_parser(".pdf"), PdfParser)


def test_extracts_text_in_page_order(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(_simple_pdf("First page text."))
    parsed = parse("pdf", path)

    assert parsed.text == "First page text."
    assert parsed.blocks == [Paragraph("First page text.")]


def test_extracts_multiple_paragraphs(tmp_path):
    text = "First paragraph line.\n\nSecond paragraph line."
    path = tmp_path / "doc.pdf"
    path.write_bytes(_simple_pdf(text))
    parsed = parse("pdf", path)

    assert parsed.blocks == [
        Paragraph("First paragraph line."),
        Paragraph("Second paragraph line."),
    ]


def test_empty_page_produces_empty_blocks(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(_simple_pdf(""))
    parsed = parse("pdf", path)

    assert parsed.text == ""
    assert parsed.blocks == []


def test_corrupt_file_raises_parser_error(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"this is not a pdf")

    with pytest.raises(ParserError):
        parse("pdf", path)


def test_truncated_pdf_raises_parser_error(tmp_path):
    path = tmp_path / "truncated.pdf"
    data = _simple_pdf("Some content")
    path.write_bytes(data[: len(data) // 2])

    with pytest.raises(ParserError):
        parse("pdf", path)
