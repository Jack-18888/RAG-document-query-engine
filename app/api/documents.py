from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi import File as FileParam

from app.api.schemas import (
    DocumentDetail,
    DocumentListResponse,
    DocumentOut,
    JobOut,
    ReindexResponse,
    UploadResponse,
)
from app.config import get_settings
from app.jobs.worker import JobExecutor
from app.parsers import supported_extensions
from app.storage import chunk_repo, document_repo, job_repo

router = APIRouter(tags=["documents"])


def _executor(request: Request) -> JobExecutor:
    return request.app.state.job_executor


async def _stream_to_temp(file: UploadFile) -> tuple[Path, int]:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(dir=upload_dir, prefix=".upload-", suffix=".tmp")
    os.close(fd)
    temp_path = Path(temp_name)

    size_limit = settings.max_upload_size_mb * 1024 * 1024
    total = 0
    with Path(temp_name).open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > size_limit:
                out.close()
                temp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"file exceeds the size limit of {settings.max_upload_size_mb} MB",
                )
            out.write(chunk)
    if total == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    return temp_path, total


@router.post("/documents", status_code=202, response_model=UploadResponse)
async def upload_document(
    file: Annotated[UploadFile, FileParam()],
    executor: Annotated[JobExecutor, Depends(_executor)],
) -> UploadResponse:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    ext = suffix.lstrip(".")
    if ext not in supported_extensions():
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file extension: {suffix or 'none'}",
        )

    temp_path, size_bytes = await _stream_to_temp(file)
    document = await document_repo.create(name=filename, fmt=ext, size_bytes=size_bytes)
    job = await job_repo.create(document_id=document["id"])

    settings = get_settings()
    dest = Path(settings.upload_dir) / f"{document['id']}{suffix}"
    temp_path.replace(dest)

    executor.enqueue(job["id"], dest)
    return UploadResponse(document=DocumentOut(**document), job=JobOut(**job))


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    documents = await document_repo.list_all()
    return DocumentListResponse(documents=[DocumentOut(**d) for d in documents])


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: str) -> DocumentDetail:
    document = await document_repo.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    chunk_count = await chunk_repo.count_by_document(doc_id)
    return DocumentDetail(**document, chunk_count=chunk_count)


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str) -> None:
    document = await document_repo.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")

    settings = get_settings()
    from app.embeddings.pinecone_client import get_pinecone_client
    from app.retrieval.vector_repo import VectorRepository

    try:
        vector_repo = VectorRepository(get_pinecone_client())
        await vector_repo.delete_by_document(doc_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"vector service unavailable: {exc}",
        ) from exc
    await chunk_repo.delete_by_document(doc_id)
    await document_repo.delete(doc_id)

    ext = Path(document["name"]).suffix
    stored = Path(settings.upload_dir) / f"{doc_id}{ext}"
    stored.unlink(missing_ok=True)


@router.post("/documents/{doc_id}/reindex", status_code=202, response_model=ReindexResponse)
async def reindex_document(
    doc_id: str,
    executor: Annotated[JobExecutor, Depends(_executor)],
) -> ReindexResponse:
    document = await document_repo.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")

    from app.embeddings.pinecone_client import get_pinecone_client
    from app.retrieval.vector_repo import VectorRepository

    try:
        vector_repo = VectorRepository(get_pinecone_client())
        await vector_repo.delete_by_document(doc_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"vector service unavailable: {exc}",
        ) from exc
    await chunk_repo.delete_by_document(doc_id)

    await document_repo.update(doc_id, status="pending", error_message=None)
    job = await job_repo.create(document_id=doc_id)

    settings = get_settings()
    ext = Path(document["name"]).suffix
    stored = Path(settings.upload_dir) / f"{doc_id}{ext}"
    if not stored.exists():
        raise HTTPException(status_code=404, detail="stored original file not found")
    executor.enqueue(job["id"], stored)

    return ReindexResponse(job=JobOut(**job))
