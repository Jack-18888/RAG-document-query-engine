"""Question-answering endpoints backed by retrieval and generation services."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    QueryDetail,
    QueryListResponse,
    QueryOut,
    QueryRequest,
    QueryResponse,
    SourceOut,
)
from app.embeddings.pinecone_client import get_pinecone_client
from app.generation.answer_service import AnswerService, Source
from app.generation.deepseek_client import DeepSeekClient
from app.retrieval.retrieval_service import NO_SOURCES_MESSAGE, RetrievalService
from app.storage import query_repo

router = APIRouter(tags=["queries"])


def _to_sources(sources: list[Source]) -> list[SourceOut]:
    """Convert answer sources into the API schema."""
    return [
        SourceOut(
            chunk_id=source.chunk_id,
            doc_id=source.doc_id,
            doc_name=source.doc_name,
            excerpt=source.excerpt,
            score=source.score,
        )
        for source in sources
    ]


@router.post("/queries", response_model=QueryResponse)
async def query_documents(payload: QueryRequest) -> QueryResponse:
    """Answer a question using the retrieved library sources.

    Retrieves candidate chunks (vector + BM25 fused and reranked), then asks
    the LLM to answer strictly from those excerpts. Returns the answer with
    source citations, or a "no sources" message when nothing relevant is found,
    and persists the query with its fetched chunks for later reference.
    Raises 400 for empty questions and 503 if retrieval or generation fails.
    """
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        client = get_pinecone_client()
        retrieval = RetrievalService(client)
        chunks = await retrieval.retrieve(question)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"retrieval service unavailable: {exc}",
        ) from exc

    if not chunks:
        record = await query_repo.create(question, NO_SOURCES_MESSAGE, [])
        return QueryResponse(
            id=record["id"],
            question=record["question"],
            answer=record["answer"],
            created_at=record["created_at"],
            sources=[],
        )

    try:
        answer_service = AnswerService(DeepSeekClient())
        answer = await answer_service.answer(question, chunks)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"generation service unavailable: {exc}",
        ) from exc

    record = await query_repo.create(
        question,
        answer.answer,
        [(source.chunk_id, source.score) for source in answer.sources],
    )
    return QueryResponse(
        id=record["id"],
        question=record["question"],
        answer=record["answer"],
        created_at=record["created_at"],
        sources=_to_sources(answer.sources),
    )


@router.get("/queries", response_model=QueryListResponse)
async def list_queries() -> QueryListResponse:
    """List all stored queries, newest first."""
    queries = await query_repo.list_all()
    return QueryListResponse(
        queries=[
            QueryOut(id=q["id"], question=q["question"], created_at=q["created_at"])
            for q in queries
        ]
    )


@router.get("/queries/{query_id}", response_model=QueryDetail)
async def get_query(query_id: str) -> QueryDetail:
    """Return a stored query with its answer and cited sources; 404 if unknown."""
    query = await query_repo.get(query_id)
    if query is None:
        raise HTTPException(status_code=404, detail="query not found")
    sources = await query_repo.get_sources(query_id)
    return QueryDetail(
        id=query["id"],
        question=query["question"],
        answer=query["answer"],
        created_at=query["created_at"],
        sources=[SourceOut(**source) for source in sources],
    )


@router.delete("/queries/{query_id}", status_code=204)
async def delete_query(query_id: str) -> None:
    """Remove a stored query and its fetched-chunk relations; 404 if unknown."""
    if not await query_repo.delete(query_id):
        raise HTTPException(status_code=404, detail="query not found")
