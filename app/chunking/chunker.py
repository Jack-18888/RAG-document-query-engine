from __future__ import annotations

import re
from dataclasses import dataclass

from app.parsers.base import Heading, Paragraph, ParsedDocument
from app.storage.chunk_repo import Chunk

TARGET_TOKENS = 500
OVERLAP_TOKENS = 50

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    return len(text.split())


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text.strip())
    return [part.strip() for part in parts if part.strip()]


@dataclass
class _Buffer:
    sentences: list[str]
    tokens: int


def _make_buffer() -> _Buffer:
    return _Buffer(sentences=[], tokens=0)


def chunk_document(
    parsed: ParsedDocument,
    doc_id: str,
    *,
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer = _make_buffer()
    heading_levels: list[int] = []
    heading_texts: list[str] = []

    def heading_path_text() -> str:
        return " | ".join(heading_texts)

    def heading_path_tokens() -> int:
        return estimate_tokens(heading_path_text())

    def flush() -> None:
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
        elif isinstance(block, Paragraph):
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
    tail = _make_buffer()
    for sentence in reversed(buffer.sentences):
        sentence_tokens = estimate_tokens(sentence)
        if tail.tokens + sentence_tokens > overlap_tokens:
            break
        tail.sentences.insert(0, sentence)
        tail.tokens += sentence_tokens
    return tail
