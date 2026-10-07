"""Grounds LLM answers in retrieved source excerpts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.generation.deepseek_client import DeepSeekClient
from app.retrieval.retrieval_service import NO_SOURCES_MESSAGE, RetrievedChunk

SYSTEM_PROMPT = (
    "You are a precise research assistant. Answer the user's question using ONLY the "
    "provided source excerpts below. Do not invent facts, citations, or sources. If the "
    "excerpts do not contain the answer, say clearly that the answer is not found in the "
    "provided sources. Base your answer strictly on the excerpts."
)


@dataclass(frozen=True)
class Source:
    """A cited source backing part of an answer."""

    chunk_id: str
    doc_id: str
    doc_name: str
    excerpt: str
    score: float


@dataclass(frozen=True)
class Answer:
    """A generated answer plus the sources it used."""

    answer: str
    sources: list[Source]


class AnswerService:
    """Generates citations-aware answers from retrieved chunks."""

    def __init__(
        self, chat_client: DeepSeekClient, sleep: Callable[[float], Awaitable[None]] | None = None
    ) -> None:
        """Bind to a chat client; ``sleep`` is injectable for testing."""
        self._chat_client = chat_client
        self._sleep = sleep

    async def answer(self, question: str, chunks: list[RetrievedChunk]) -> Answer:
        """Answer ``question`` strictly from ``chunks``.

        Returns the no-sources answer when ``chunks`` is empty. The model is
        asked to answer only from the provided excerpts, and every chunk is
        returned as a :class:`Source` for citation.
        """
        if not chunks:
            return Answer(answer=NO_SOURCES_MESSAGE, sources=[])

        excerpts = "\n\n".join(f"[{i + 1}] {chunk.text}" for i, chunk in enumerate(chunks))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Sources:\n{excerpts}\n\n"
                    f"Question: {question}\n\n"
                    "Answer using only the sources above."
                ),
            },
        ]
        answer_text = await self._chat_client.chat(messages, sleep=self._sleep)

        sources = [
            Source(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_name=chunk.doc_name,
                excerpt=chunk.text,
                score=chunk.score,
            )
            for chunk in chunks
        ]
        return Answer(answer=answer_text, sources=sources)
