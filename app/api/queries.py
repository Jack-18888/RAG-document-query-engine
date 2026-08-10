"""Question-answering endpoints backed by retrieval and generation services."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import QueryRequest, QueryResponse, SourceOut
from app.embeddings.pinecone_client import get_pinecone_client
from app.generation.answer_service import AnswerService
from app.generation.deepseek_client import DeepSeekClient
from app.retrieval.retrieval_service import NO_SOURCES_MESSAGE, RetrievalService

router = APIRouter(tags=["queries"])


@router.post("/queries", response_model=QueryResponse)
async def query_documents(payload: QueryRequest) -> QueryResponse:
    """Answer a question using the retrieved library sources.

    Retrieves candidate chunks (vector + BM25 fused and reranked), then asks
    the LLM to answer strictly from those excerpts. Returns the answer with
    source citations, or a "no sources" message when nothing relevant is found.
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
        return QueryResponse(answer=NO_SOURCES_MESSAGE, sources=[])

    try:
        answer_service = AnswerService(DeepSeekClient())
        answer = await answer_service.answer(question, chunks)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"generation service unavailable: {exc}",
        ) from exc

    return QueryResponse(
        answer=answer.answer,
        sources=[
            SourceOut(
                chunk_id=source.chunk_id,
                doc_id=source.doc_id,
                doc_name=source.doc_name,
                excerpt=source.excerpt,
                score=source.score,
            )
            for source in answer.sources
        ],
    )
