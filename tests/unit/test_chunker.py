from app.chunking.chunker import (
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    _overlap_tail,
    chunk_document,
    estimate_tokens,
    split_sentences,
)
from app.parsers import parse
from app.parsers.base import Heading, Paragraph, ParsedDocument


def _parsed(blocks):
    text = "\n\n".join(b.text for b in blocks)
    return ParsedDocument(text=text, blocks=blocks)


def _md(tmp_path, content: str) -> ParsedDocument:
    path = tmp_path / "doc.md"
    path.write_text(content, encoding="utf-8")
    return parse("md", path)


# --- sentence splitting ---


def test_split_sentences():
    text = "First sentence. Second one! Third? Last without punct"
    assert split_sentences(text) == [
        "First sentence.",
        "Second one!",
        "Third?",
        "Last without punct",
    ]


def test_split_sentences_handles_blank():
    assert split_sentences("  ") == []


def test_estimate_tokens_counts_words():
    assert estimate_tokens("") == 0
    assert estimate_tokens("one two three") == 3


# --- structure preservation ---


def test_respects_heading_boundaries(tmp_path):
    content = "# One\n\ntext a.\n\n# Two\n\ntext b.\n\n# Three\n\ntext c."
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    assert [c.text for c in chunks] == [
        "One text a.",
        "Two text b.",
        "Three text c.",
    ]


def test_heading_path_prepended_to_chunks(tmp_path):
    content = "# Section\n\n## Sub\n\nbody text here."
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    assert chunks[0].text == "Section | Sub body text here."


def test_heading_level_replaces_path(tmp_path):
    blocks = [
        Heading(level=1, text="Grand"),
        Heading(level=2, text="Sub A"),
        Paragraph("alpha text."),
        Heading(level=2, text="Sub B"),
        Paragraph("beta text."),
    ]
    chunks = chunk_document(_parsed(blocks), "doc_1")

    assert chunks[0].text == "Grand | Sub A alpha text."
    assert chunks[1].text == "Grand | Sub B beta text."


# --- size capping ---


def test_large_paragraph_split_at_sentence_boundaries(tmp_path):
    sentences = [f"Sentence number {i} with a bit of extra filler text here." for i in range(50)]
    content = " ".join(sentences)
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.tokens <= TARGET_TOKENS + 20


def test_no_sentence_is_split(tmp_path):
    long_sentence = " ".join(["word"] * 2000)
    content = f"{long_sentence}. Second sentence."
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    assert len(chunks) == 2
    assert chunks[0].tokens == 2000
    assert "word" * 1 in chunks[0].text
    assert "word." in chunks[0].text
    assert "Second sentence." in chunks[1].text


def test_unbroken_pathological_block_becomes_one_chunk(tmp_path):
    unbroken = " ".join(["w"] * 5000)
    content = f"{unbroken}"
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    assert len(chunks) == 1
    assert chunks[0].tokens == 5000


# --- overlap ---


def test_overlap_between_adjacent_chunks(tmp_path):
    sentences = [
        f"Filler sentence {i} containing many ordinary words used for chunking tests here today."  # noqa: E501
        for i in range(100)
    ]
    content = " ".join(sentences)
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    if len(chunks) < 2:
        raise AssertionError("expected multiple chunks")

    first_last_words = chunks[0].text.split()[-OVERLAP_TOKENS:]
    second_text = chunks[1].text
    shared = set(first_last_words) & set(second_text.split())
    assert len(shared) > 0
    assert len(first_last_words) <= OVERLAP_TOKENS


def test_overlap_tail_limits_tokens():
    buffer = _overlap_tail_with_sentences(
        ["aaaa " + "b " * 20, "ccc " + "d " * 10, "e"],
        OVERLAP_TOKENS,
    )
    assert buffer.tokens <= OVERLAP_TOKENS
    assert buffer.sentences[-1] == "e"


def _overlap_tail_with_sentences(sentences, overlap):
    from app.chunking.chunker import _Buffer

    buffer = _Buffer(sentences=sentences, tokens=sum(estimate_tokens(s) for s in sentences))
    return _overlap_tail(buffer, overlap)


# --- determinism ---


def test_deterministic_ids(tmp_path):
    content = "# Title\n\nparagraph one.\n\n## Sub\n\nparagraph two."
    doc_a = _md(tmp_path, content)
    chunks_a = chunk_document(doc_a, "doc_1")
    chunks_b = chunk_document(doc_a, "doc_1")

    assert [c.id for c in chunks_a] == [c.id for c in chunks_b]
    assert [c.text for c in chunks_a] == [c.text for c in chunks_b]
    assert chunks_a[0].id == "chunk_doc_1_0"


def test_same_input_same_ids_different_doc_ids(tmp_path):
    content = "# Title\n\nbody."
    chunks_1 = chunk_document(_md(tmp_path, content), "doc_a")
    chunks_2 = chunk_document(_md(tmp_path, content), "doc_b")

    assert chunks_1[0].id == "chunk_doc_a_0"
    assert chunks_2[0].id == "chunk_doc_b_0"


# --- misc ---


def test_empty_document_yields_no_chunks(tmp_path):
    content = ""
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    assert chunks == []


def test_paragraph_only_document(tmp_path):
    content = "Just a single paragraph with a few words."
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    assert len(chunks) == 1
    assert chunks[0].doc_id == "doc_1"
    assert chunks[0].tokens == 8


def test_heading_only_document_produces_no_chunks(tmp_path):
    content = "# Only Heading"
    chunks = chunk_document(_md(tmp_path, content), "doc_1")

    assert chunks == []
