"""Hybrid retrieval: vector + BM25 fusion followed by hosted reranking."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.embeddings.embedding_service import INPUT_TYPE_QUERY, EmbeddingService
from app.embeddings.pinecone_client import PineconeClient
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.reranker import Reranker
from app.retrieval.vector_repo import VectorRepository
from app.storage import bm25_repo, chunk_repo, document_repo

VECTOR_TOP_K = 10
BM25_TOP_K = 10
FUSION_TOP_K = 20
RERANK_TOP_N = 3

NO_SOURCES_MESSAGE = "No relevant sources found in the library."


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieved chunk with citation metadata and relevance score."""

    chunk_id: str
    doc_id: str
    doc_name: str
    text: str
    score: float


class RetrievalError(Exception):
    """Raised when hosted retrieval fails."""


class RetrievalService:
    """Runs the hybrid retrieval pipeline for a question."""

    def __init__(self, client: PineconeClient, sleep=None) -> None:
        """Bind to a Pinecone client; ``sleep`` is injectable for testing."""
        self._client = client
        self._sleep = sleep

    async def retrieve(self, question: str) -> list[RetrievedChunk]:
        """Retrieve the most relevant chunks for ``question``.

        Pipeline: embed the question, query Pinecone, run BM25 over the FTS
        index, fuse both rankings with RRF, load the fused candidate chunks,
        then rerank them with the hosted reranker. Returns an empty list when
        nothing relevant is found.
        """
        embeddings = EmbeddingService(self._client, sleep=self._sleep)
        vector_repo = VectorRepository(self._client, sleep=self._sleep)
        reranker = Reranker(self._client, sleep=self._sleep)

        async def _get_vector_matches():
            query_vector = (await embeddings.embed([question], INPUT_TYPE_QUERY))[0]
            return await vector_repo.query(query_vector, top_k=VECTOR_TOP_K)

        vector_matches, bm25_ids = await asyncio.gather(
            _get_vector_matches(), bm25_repo.search(question, k=BM25_TOP_K)
        )

        vector_ids = [match["chunk_id"] for match in vector_matches]

        fused = reciprocal_rank_fusion([vector_ids, bm25_ids])[:FUSION_TOP_K]
        if not fused:
            return []

        candidate_ids = [chunk_id for chunk_id, _ in fused]
        candidates = await chunk_repo.get_by_ids(candidate_ids)
        if not candidates:
            return []

        texts = [chunk.text for chunk in candidates]
        reranked = await reranker.rerank(question, texts, top_n=RERANK_TOP_N)
        if not reranked:
            return []

        results: list[RetrievedChunk] = []
        for result in reranked:
            chunk = candidates[result.index]
            doc = await document_repo.get(chunk.doc_id)
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    doc_name=doc["name"] if doc else chunk.doc_id,
                    text=chunk.text,
                    score=result.score,
                )
            )
        return results
