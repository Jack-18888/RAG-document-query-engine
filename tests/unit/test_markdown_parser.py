import pytest

from app.parsers import get_parser, parse
from app.parsers.base import Heading, Paragraph, UnsupportedFormatError
from app.parsers.markdown_parser import MarkdownParser


def _write(tmp_path, content: str, name: str = "doc.md"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_registry_resolves_md(tmp_path):
    path = _write(tmp_path, "# Hello")
    assert isinstance(get_parser("md"), MarkdownParser)
    assert isinstance(get_parser(".md"), MarkdownParser)
    parsed = parse("md", path)
    assert parsed.blocks == [Heading(level=1, text="Hello")]


def test_registry_rejects_unknown_extension(tmp_path):
    path = _write(tmp_path, "hello", "doc.xyz")
    with pytest.raises(UnsupportedFormatError):
        parse("xyz", path)


def test_atx_headings_and_paragraphs(tmp_path):
    content = (
        "# Title\n"
        "\n"
        "Some paragraph text.\n"
        "\n"
        "## Section One\n"
        "\n"
        "Body of section one.\n"
        "\n"
        "### Subsection\n"
        "\n"
        "Deeper detail."
    )
    parsed = parse("md", _write(tmp_path, content))

    assert parsed.blocks == [
        Heading(level=1, text="Title"),
        Paragraph("Some paragraph text."),
        Heading(level=2, text="Section One"),
        Paragraph("Body of section one."),
        Heading(level=3, text="Subsection"),
        Paragraph("Deeper detail."),
    ]


def test_setext_headings_preserved(tmp_path):
    content = "Setext Heading\n==============\n\nSetext Sub\n-----------\n\nText."
    parsed = parse("md", _write(tmp_path, content))

    assert parsed.blocks == [
        Heading(level=1, text="Setext Heading"),
        Heading(level=2, text="Setext Sub"),
        Paragraph("Text."),
    ]


def test_inline_markup_stripped(tmp_path):
    content = (
        "**bold** and *italic* and `code` and [link](http://example.com) "
        "and ~~strike~~ and <b>html</b>."
    )
    parsed = parse("md", _write(tmp_path, content))

    assert len(parsed.blocks) == 1
    block = parsed.blocks[0]
    assert isinstance(block, Paragraph)
    assert "**" not in block.text
    assert "*" not in block.text
    assert "[" not in block.text
    assert "`" not in block.text
    assert "<b>" not in block.text


def test_inline_markup_keeps_words(tmp_path):
    content = "See the **quick brown fox** and [the docs](http://x)."
    parsed = parse("md", _write(tmp_path, content))

    block = parsed.blocks[0]
    assert isinstance(block, Paragraph)
    assert "quick brown fox" in block.text
    assert "the docs" in block.text


def test_lists_become_paragraphs(tmp_path):
    content = "- first item\n- second item\n- third item"
    parsed = parse("md", _write(tmp_path, content))

    assert parsed.blocks == [
        Paragraph("first item"),
        Paragraph("second item"),
        Paragraph("third item"),
    ]


def test_full_text_is_plain_text_of_blocks(tmp_path):
    content = "# Heading\n\nFirst para.\n\nSecond para."
    parsed = parse("md", _write(tmp_path, content))

    assert parsed.text == "Heading\n\nFirst para.\n\nSecond para."


def test_code_block_text_extracted(tmp_path):
    content = "```python\nprint('hi')\n```\n\nAfter."
    parsed = parse("md", _write(tmp_path, content))

    texts = [block.text for block in parsed.blocks]
    assert any("print('hi')" in t for t in texts)
    assert "After." in texts


def test_empty_document(tmp_path):
    parsed = parse("md", _write(tmp_path, ""))

    assert parsed.blocks == []
    assert parsed.text == ""
