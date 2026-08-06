from __future__ import annotations

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    name: str
    format: str
    size_bytes: int
    status: str
    error_message: str | None
    created_at: str
    updated_at: str


class DocumentDetail(DocumentOut):
    chunk_count: int


class JobOut(BaseModel):
    id: str
    document_id: str
    stage: str
    chunks_processed: int
    chunks_total: int | None
    error_message: str | None
    created_at: str
    updated_at: str


class UploadResponse(BaseModel):
    document: DocumentOut
    job: JobOut


class ReindexResponse(BaseModel):
    job: JobOut


class DocumentListResponse(BaseModel):
    documents: list[DocumentOut]


class QueryRequest(BaseModel):
    question: str = ""


class SourceOut(BaseModel):
    chunk_id: str
    doc_id: str
    doc_name: str
    excerpt: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
