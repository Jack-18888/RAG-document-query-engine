# Roadmap 1 — Backend v1

Goal: ship the complete v1 backend for the RAG document query engine — ingest PDF/docx/HTML/Markdown via background jobs, answer natural-language questions with source citations, and manage documents — with the full test suite green and docs matching the code.

Machine-readable task breakdown: [tasks-1.json](tasks-1.json).

## Scope

**In scope (v1 must-haves):**
- Ingestion of PDF, docx, HTML, Markdown via background jobs with pollable progress
- Hybrid retrieval: BM25 (SQLite FTS5) fused with vector similarity (Pinecone), reranked by hosted `bge-reranker-v2-m3`
- Query endpoint returning an answer (DeepSeek `deepseek-v4-flash`, non-thinking) plus the top-3 source chunks
- Document management: list + status, detail, delete, re-index, job progress
- Stateless queries; REST API for the sibling frontend

**Out of scope for Roadmap 1:** images/OCR, conversation history, auth, provider-agnostic LLM config, Docker, CLI.

## Phase map

| Phase | Focus | Tasks |
|---|---|---|
| 1 — Foundation | SQLite schema + FTS5 + repositories | T01–T05 |
| 2 — Parsers | per-format text/structure extraction | T06–T09 |
| 3 — Chunking | structure-aware chunker | T10 |
| 4 — Embeddings & vectors | Pinecone client, embedding, vector repo, reranker | T11–T14 |
| 5 — Ingestion jobs | thread-pool worker, retries, progress | T15–T16 |
| 6 — Retrieval | vector + BM25 + RRF + rerank orchestration | T17 |
| 7 — Generation | DeepSeek client, prompts, answer assembly | T18–T19 |
| 8 — API layer | all endpoints wiring the above | T20–T25 |
| 9 — Hardening & docs | error semantics, limits, docs sync, final verification | T26–T27 |

## Build order and dependency rules

- Phases 1–4 are mostly independent and can proceed in parallel once the storage schema (T01) and parser contract (T06) are fixed — they are the two stable interfaces everything else builds on.
- Phase 5 (jobs) depends on T01–T04 (repos), T06–T09 (parsers), T10 (chunking), T12 (embedding), T13 (vector upsert).
- Phase 6 (retrieval) depends on T05 (BM25), T12 (query embedding), T13 (vector query), T14 (rerank).
- Phase 7 depends on T17 (retrieval output) + T18 (chat client).
- Phase 8 depends on all prior phases.
- Every task is testable in isolation with mocks for Pinecone/DeepSeek — no live keys required.

## Definition of done (per task)

A task is done only when all of the following hold:

1. Code follows the existing layer structure under `app/` (`api/`, `parsers/`, `chunking/`, `embeddings/`, `retrieval/`, `generation/`, `storage/`, `jobs/`).
2. Its acceptance criteria (in tasks-1.json) all pass.
3. Unit/integration tests are added or updated and `pytest` passes.
4. `ruff check .` and `ruff format --check .` are clean.
5. Any decision or TBD it resolves is reflected in `docs/architecture.md` / `docs/risks-and-open-questions.md` in the same change.

## Roadmap 1 definition of done

- All tasks T01–T27 are complete; the full `pytest` suite passes with only mocked hosted calls.
- The API implements every endpoint in `docs/endpoints.md` with the documented status codes and response shapes.
- `docs/rag-workflow.md`, `docs/endpoints.md`, `docs/architecture.md`, and `README.md` match the code (no stale TBDs).
- A local smoke run (real .env keys) confirms: upload → job succeeds → query returns an answer with sources.
