from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.chunking.chunker import chunk_document
from app.embeddings.embedding_service import INPUT_TYPE_PASSAGE, EmbeddingService
from app.embeddings.pinecone_client import get_pinecone_client
from app.parsers import ParserError, parse
from app.retrieval.vector_repo import VectorRepository
from app.storage import chunk_repo, document_repo, job_repo


async def ingest_job(job_id: str, document_path: Path) -> None:
    job = await job_repo.get(job_id)
    if job is None:
        return
    doc_id = job["document_id"]
    document = await document_repo.get(doc_id)
    if document is None:
        return

    try:
        await job_repo.update(job_id, stage="parsing")
        parsed = parse(document["format"], document_path)
    except ParserError as exc:
        await _fail(job_id, doc_id, str(exc))
        return

    await job_repo.update(job_id, stage="chunking")
    chunks = chunk_document(parsed, doc_id)
    await job_repo.update(job_id, stage="embedding", chunks_total=len(chunks))

    embedding_service = EmbeddingService(get_pinecone_client())
    vector_repo = VectorRepository(get_pinecone_client())
    try:
        vectors = await embedding_service.embed(
            [chunk.text for chunk in chunks],
            input_type=INPUT_TYPE_PASSAGE,
        )
        await job_repo.update(job_id, stage="indexing", chunks_processed=len(chunks))
        await chunk_repo.insert_many(chunks)
        await vector_repo.upsert([chunk.id for chunk in chunks], vectors, doc_id)
    except Exception as exc:
        await _fail(job_id, doc_id, str(exc))
        return

    await document_repo.update(doc_id, status="indexed")
    await job_repo.update(job_id, stage="succeeded", chunks_processed=len(chunks))


async def _fail(job_id: str, doc_id: str, message: str) -> None:
    await document_repo.update(doc_id, status="failed", error_message=message)
    await job_repo.update(job_id, stage="failed", error_message=message)


def _run_ingest(job_id: str, document_path: Path) -> None:
    asyncio.run(ingest_job(job_id, document_path))


class JobExecutor:
    def __init__(self, max_workers: int) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers)

    def enqueue(self, job_id: str, document_path: Path) -> None:
        self._pool.submit(_run_ingest, job_id, document_path)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)
