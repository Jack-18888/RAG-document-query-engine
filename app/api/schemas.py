"""Pydantic request/response schemas for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel


class DocumentOut(BaseModel):
    """Summary of a stored document."""

    id: str
    name: str
    format: str
    size_bytes: int
    status: str
    error_message: str | None
    created_at: str
    updated_at: str


class DocumentDetail(DocumentOut):
    """Document summary plus how many chunks were indexed for it."""

    chunk_count: int


class JobOut(BaseModel):
    """Status snapshot of an ingestion job."""

    id: str
    document_id: str
    stage: str
    chunks_processed: int
    chunks_total: int | None
    error_message: str | None
    created_at: str
    updated_at: str


class UploadResponse(BaseModel):
    """Response to a document upload: the new document and its job."""

    document: DocumentOut
    job: JobOut


class ReindexResponse(BaseModel):
    """Response to a reindex request: the new ingestion job."""

    job: JobOut


class DocumentListResponse(BaseModel):
    """Paginated/plain list of documents."""

    documents: list[DocumentOut]


class QueryRequest(BaseModel):
    """A natural-language question to answer from the library."""

    question: str = ""


class SourceOut(BaseModel):
    """A single cited source attached to an answer."""

    chunk_id: str
    doc_id: str
    doc_name: str
    excerpt: str
    score: float


class QueryResponse(BaseModel):
    """An answer plus the sources it was derived from."""

    answer: str
    sources: list[SourceOut]
