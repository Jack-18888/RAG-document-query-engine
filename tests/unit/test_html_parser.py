from app.parsers import get_parser, parse
from app.parsers.base import Heading, Paragraph
from app.parsers.html_parser import HtmlParser


def _write(tmp_path, content: str, name: str = "doc.html"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_registry_resolves_html_and_htm(tmp_path):
    path = _write(tmp_path, "<p>hi</p>")
    assert isinstance(get_parser("html"), HtmlParser)
    assert isinstance(get_parser("htm"), HtmlParser)
    parsed = parse("html", path)
    assert parsed.blocks == [Paragraph("hi")]


def test_headings_with_levels(tmp_path):
    content = "<html><body><h1>Title</h1><h2>Section</h2><h6>Deep</h6></body></html>"
    parsed = parse("html", _write(tmp_path, content))

    assert parsed.blocks == [
        Heading(level=1, text="Title"),
        Heading(level=2, text="Section"),
        Heading(level=6, text="Deep"),
    ]


def test_paragraphs_in_order(tmp_path):
    content = "<p>First paragraph.</p><p>Second paragraph.</p>"
    parsed = parse("html", _write(tmp_path, content))

    assert parsed.blocks == [Paragraph("First paragraph."), Paragraph("Second paragraph.")]


def test_script_style_nav_excluded(tmp_path):
    content = (
        "<html><head><style>body { color: red; }</style></head><body>"
        "<script>alert('secret');</script>"
        "<nav>navigation junk</nav>"
        "<p>Real content.</p>"
        "</body></html>"
    )
    parsed = parse("html", _write(tmp_path, content))

    assert parsed.blocks == [Paragraph("Real content.")]


def test_tags_stripped(tmp_path):
    content = "<p>Some <b>bold</b> and <i>italic</i> and <a href='/x'>link</a> text.</p>"
    parsed = parse("html", _write(tmp_path, content))

    assert parsed.blocks == [Paragraph("Some bold and italic and link text.")]


def test_div_and_br_split_paragraphs(tmp_path):
    content = "<div>One</div><div>Two</div><div>Three<br>Four</div>"
    parsed = parse("html", _write(tmp_path, content))

    assert parsed.blocks == [
        Paragraph("One"),
        Paragraph("Two"),
        Paragraph("Three Four"),
    ]


def test_full_text_concatenates_blocks(tmp_path):
    content = "<h1>Title</h1><p>Body text.</p>"
    parsed = parse("html", _write(tmp_path, content))

    assert parsed.text == "Title\n\nBody text."


def test_empty_document(tmp_path):
    parsed = parse("html", _write(tmp_path, ""))

    assert parsed.blocks == []
    assert parsed.text == ""
