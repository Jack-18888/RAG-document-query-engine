"""Heading-aware document chunking with token targets and sentence overlap."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.parsers.base import Heading, ParsedDocument
from app.storage.chunk_repo import Chunk

TARGET_TOKENS = 500
OVERLAP_TOKENS = 50

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    """Rough token estimate: whitespace-separated word count."""
    return len(text.split())


def split_sentences(text: str) -> list[str]:
    """Split text into sentences on sentence-ending punctuation."""
    parts = _SENTENCE_SPLIT.split(text.strip())
    return [part.strip() for part in parts if part.strip()]


@dataclass
class _Buffer:
    """Accumulated sentences and their running token count."""

    sentences: list[str]
    tokens: int


def _make_buffer() -> _Buffer:
    """Create an empty buffer."""
    return _Buffer(sentences=[], tokens=0)


def chunk_document(
    parsed: ParsedDocument,
    doc_id: str,
    *,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """Split a parsed document into heading-aware chunks.

    Each chunk carries its current heading path as a prefix. Headings always
    start a new chunk. Paragraphs are appended until adding one would exceed
    ``target_tokens``; oversized paragraphs are split by sentence. When a chunk
    is flushed, the trailing sentences (up to ``overlap_tokens``) are carried
    into the next chunk to preserve context across boundaries.
    """
    chunks: list[Chunk] = []
    buffer = _make_buffer()
    heading_levels: list[int] = []
    heading_texts: list[str] = []

    def heading_path_text() -> str:
        """Render the current heading path (e.g. "Ch1 | Section A")."""
        return " | ".join(heading_texts)

    def heading_path_tokens() -> int:
        """Token count of the heading path prefix."""
        return estimate_tokens(heading_path_text())

    def flush() -> None:
        """Emit the current buffer as a chunk and keep an overlapping tail."""
        nonlocal buffer
        if not buffer.sentences:
            return
        prefix = heading_path_text()
        body = " ".join(buffer.sentences)
        text = f"{prefix} {body}" if prefix else body
        chunk_index = len(chunks)
        chunks.append(
            Chunk(
                id=f"chunk_{doc_id}_{chunk_index}",
                doc_id=doc_id,
                chunk_index=chunk_index,
                text=text,
                tokens=estimate_tokens(text),
            )
        )
        buffer = _overlap_tail(buffer, overlap_tokens)

    def update_heading(level: int, text: str) -> None:
        """Record a heading, trimming deeper headings that it supersedes."""
        while heading_levels and heading_levels[-1] >= level:
            heading_levels.pop()
            heading_texts.pop()
        heading_levels.append(level)
        heading_texts.append(text)

    for block in parsed.blocks:
        if isinstance(block, Heading):
            flush()
            update_heading(block.level, block.text)
            buffer = _make_buffer()
        else:
            text = block.text.strip()
            if not text:
                continue
            block_tokens = estimate_tokens(text)
            prefix_tokens = heading_path_tokens()
            if buffer.sentences and buffer.tokens + prefix_tokens + block_tokens > target_tokens:
                flush()
            if block_tokens <= target_tokens:
                buffer.sentences.append(text)
                buffer.tokens += block_tokens
            else:
                for sentence in split_sentences(text):
                    sentence_tokens = estimate_tokens(sentence)
                    if buffer.sentences and buffer.tokens + sentence_tokens > target_tokens:
                        flush()
                    buffer.sentences.append(sentence)
                    buffer.tokens += sentence_tokens
    flush()

    return chunks


def _overlap_tail(buffer: _Buffer, overlap_tokens: int) -> _Buffer:
    """Take the trailing sentences (up to ``overlap_tokens``) as the next buffer."""
    tail = _make_buffer()
    for sentence in reversed(buffer.sentences):
        sentence_tokens = estimate_tokens(sentence)
        if tail.tokens + sentence_tokens > overlap_tokens:
            break
        tail.sentences.insert(0, sentence)
        tail.tokens += sentence_tokens
    return tail
