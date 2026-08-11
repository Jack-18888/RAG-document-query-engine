# Technical Approach

## Stack

- **Python 3.14** (existing `.venv`), **FastAPI** served by **uvicorn**.
- **DeepSeek API** (OpenAI-compatible, `api.deepseek.com`) for chat generation, model `deepseek-v4-flash` (non-thinking mode — extractive RAG answers). API key via `.env`. Client: official `openai` SDK.
- **Pinecone** (hosted, serverless, free tier) for vector storage plus hosted inference: `llama-text-embed-v2` embeddings (dim 1024, cosine) and `bge-reranker-v2-m3` reranking. Client: official `pinecone` SDK (`AsyncPinecone`). Because `AsyncPinecone` is bound to the event loop that creates it, `PineconeClient` caches one client + index handle **per running event loop** and closes handles whose loop has closed — so the FastAPI main loop and each ingestion job's `asyncio.run` loop never share a client bound to a closed loop.
- **SQLite + FTS5** for metadata and BM25 keyword search, accessed async via **aiosqlite**.
- **Parsing libraries:** `mistune` for Markdown (AST-based, structure-aware), `python-docx` for `.docx`, `pypdf` for `.pdf`; HTML parsed with the stdlib `html.parser`.
- **Config**: `pydantic-settings` reads `.env` into a typed `Settings` (see `app/config.py`); loaded lazily via `get_settings()` dependency so tests never require `.env`. Configurable knobs: `job_max_workers` (ingestion concurrency, default 2) and `max_upload_size_mb` (upload limit, default 50).
- **pytest + pytest-asyncio** with mocked hosted-API calls for testing (no live keys, no torch/sentence-transformers anywhere); `httpx` provides the `TestClient` transport.
- **ruff 0.16.1** for lint + format (configured in `pyproject.toml`).
- **Ingestion jobs** run in an in-process thread pool (`app/jobs/worker.py`); each job runs its own event loop via `asyncio.run` and reuses the shared SQLite connection. Concurrency bounded by `job_max_workers` (default 2, configurable via settings).

## Where it runs

Locally, single machine, launched with uvicorn from the `.venv`. Serves the REST API only; the sibling `frontend/` repo is the UI.

## Data

- One SQLite database file at `data/engine.db` containing: documents table (metadata + ingestion status), chunks table (text + document refs), FTS5 index for keyword search, ingestion job records with progress, and query history — a `queries` table (question + generated answer) plus a `query_chunks` relation table (query → fetched chunk with its rerank score). The schema lives in `data/db_init.sql` (single source of truth) and is applied idempotently by `app/storage/db.py` on app startup (lifespan); the database path is configurable via settings. See [docs/data-schema.md](docs/data-schema.md) for the full schema reference.
- Vectors are upserted into a Pinecone index (one vector per chunk, id = chunk id); every vector carries `doc_id` (indexed metadata, for filter deletes). Chunk text and metadata stay in SQLite.
- Uploaded originals are stored on disk under `data/uploads/` (gitignored).
- No local model files of any kind: embeddings and reranking come from Pinecone inference; chat from DeepSeek.
- Pinecone index: serverless, AWS `us-east-1` (free-tier region), dimension 1024, metric cosine, **pre-created by the user**; index name comes from the `PINECONE_INDEX` env var (see [docs/risks-and-open-questions.md](docs/risks-and-open-questions.md)).

## Code layout

Layer-based, one top-level package per concern under `app/`: `api/` (routers + schemas), `parsers/` (one module per format, a registry dispatching by extension, plus a shared `ParsedDocument` model of text + structural blocks), `chunking/`, `embeddings/`, `retrieval/` (vector, bm25, fusion, reranker), `generation/`, `storage/` (db + repositories), `jobs/` (ingestion worker). Tests mirror the layout under `tests/unit/` and `tests/integration/`.

## Integrations

- **DeepSeek API** (OpenAI-compatible chat completions) for answer generation.
- **Pinecone**: serverless vector index + inference (embed `/embed`, rerank `/rerank`) — needs API key + network at ingest and query time.
- Sibling `frontend/` repository consuming the REST API.

## Pipeline

1. **Ingest:** upload → job created (thread pool) → parse (per format) → chunk → embed via Pinecone inference (`input_type=passage`) → store chunks + FTS5 rows in SQLite, upsert vectors into Pinecone → mark indexed.
2. **Query:** embed question via Pinecone inference (`input_type=query`) → vector search + BM25 search → RRF fuse → `bge-reranker-v2-m3` rerank → top 3 chunks → DeepSeek chat → return answer + sources.

## Constraints

- Ingestion jobs run in-process (thread pool) — no external queue/Redis; concurrency is bounded by the pool size.
- SQLite holds local metadata/keyword search; everything else depends on hosted services (Pinecone + DeepSeek) — network and API keys required.
- Free tier: single serverless index; monthly caps on embedding tokens and rerank units (see docs/risks-and-open-questions.md).

See [docs/rag-workflow.md](docs/rag-workflow.md) for the concrete pipelines (chunking rules, retrieval top-k, fusion, retries, citations).
