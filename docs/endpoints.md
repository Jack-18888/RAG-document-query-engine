# API Endpoint Contract

Reference contract for the REST API. All routes are served at the root; errors use FastAPI's default `{"detail": "<message>"}` shape. There is no auth — single personal user, localhost only.

## Conventions

- IDs: `doc_<12-hex>`, `job_<12-hex>`, and `query_<12-hex>` (truncated UUID hex); chunk ids are deterministic `chunk_<doc_id>_<index>`.
- Timestamps: ISO-8601 UTC strings.
- Documents have a user-facing `status`; jobs carry stage-level progress.
- Upload size limit: 50 MB per file (configurable via settings).

## Status / stage values

`status` and `stage` are plain string fields (not typed enums):

| Field | Values |
|---|---|
| `document.status` | `pending` · `indexed` · `failed` |
| `job.stage` | `parsing` · `chunking` · `embedding` · `indexing` · `succeeded` · `failed` |

## Endpoints

### `POST /documents` — upload a document

Multipart form, field `file` (allowed: `.pdf`, `.docx`, `.html`, `.htm`, `.md`).

- **202** — accepted. Ingestion runs in the background thread pool; the document is immediately visible with `status=pending`.

```json
{
  "document": {
    "id": "doc_a1b2c3",
    "name": "report.pdf",
    "format": "pdf",
    "size_bytes": 524288,
    "status": "pending",
    "created_at": "2026-08-02T10:00:00Z",
    "updated_at": "2026-08-02T10:00:00Z",
    "error_message": null
  },
  "job": {
    "id": "job_d4e5f6",
    "document_id": "doc_a1b2c3",
    "stage": "parsing",
    "chunks_processed": 0,
    "chunks_total": null,
    "error_message": null,
    "created_at": "2026-08-02T10:00:00Z",
    "updated_at": "2026-08-02T10:00:00Z"
  }
}
```

- **400** — unsupported file extension or empty file.
- **413** — file exceeds the size limit.

### `GET /documents` — list documents

- **200** — all documents, newest first.

```json
{ "documents": [ { "id": "doc_a1b2c3", "name": "report.pdf", "format": "pdf", "size_bytes": 524288, "status": "indexed", "created_at": "...", "updated_at": "...", "error_message": null } ] }
```

### `GET /documents/{id}` — document detail

- **200** — full document plus `chunk_count` (0 when not yet indexed) and, on failure, `error_message`.
- **404** — unknown id.

### `DELETE /documents/{id}` — delete a document

Deletes Pinecone vectors via metadata filter (`doc_id == <id>`), then SQLite rows (chunks + FTS5 + document), then the stored original.

- **204** — deleted.
- **404** — unknown id.
- **503** — vector service unavailable (delete did not proceed).

### `POST /documents/{id}/reindex` — re-index a document

Runs the pipeline again on the stored original (no re-upload). Old vectors are cleared first via metadata filter.

- **202** — `{ "job": { ... } }` with a fresh job.
- **404** — unknown id, or the stored original file is missing.
- **503** — vector service unavailable.

### `GET /jobs/{id}` — job status

- **200** — job with current `stage`, chunk counters (`chunks_processed`, `chunks_total`), and `error_message` on failure.
- **404** — unknown id.

### `POST /queries` — ask a question

Body: `{ "question": "<string>" }`. Synchronous — blocks until the answer is generated (may take tens of seconds; the frontend should show a loading state). Every answered query (including the no-sources case) is persisted to SQLite along with the chunks that were fetched for it.

- **200** — answer plus structured sources (the top 3 reranked chunks) and the new query's metadata:

```json
{
  "id": "query_ab12cd34ef56",
  "question": "What is the retention period?",
  "answer": "The retention policy requires invoices to be kept for 7 years.",
  "created_at": "2026-08-02T10:00:00Z",
  "sources": [
    { "chunk_id": "chunk_doc_a1b2c3_0", "doc_id": "doc_a1b2c3", "doc_name": "report.pdf", "excerpt": "Invoices must be retained for a period of 7 years...", "score": 0.89 }
  ]
}
```

- **200, no sources found** — no LLM call is made; `answer` is a canned message ("No relevant sources found in the library."), `sources` is empty, and the query is still stored.
- **400** — missing or empty `question`.
- **503** — a required hosted service (Pinecone/DeepSeek) is unavailable; includes a retryable detail message. Failed queries are **not** persisted.

### `GET /queries` — list queries

- **200** — all stored queries, newest first (lightweight: id, question, created_at; use the detail endpoint for answers/sources):

```json
{ "queries": [ { "id": "query_ab12cd34ef56", "question": "What is the retention period?", "created_at": "..." } ] }
```

### `GET /queries/{id}` — query detail

- **200** — full query (id, question, answer, created_at) plus `sources`, reconstructed by joining `query_chunks` → `chunks` → `documents`. A chunk that has since been deleted is omitted.
- **404** — unknown id.

### `DELETE /queries/{id}` — delete a query

Deletes the query row and its `query_chunks` relations.

- **204** — deleted.
- **404** — unknown id.

### `GET /health` — liveness

- **200** — `{ "status": "ok" }`. No external calls; purely process liveness.

## Implementation notes

- Query pipeline order: embed question (`input_type=query`) → Pinecone top-10 → FTS5 BM25 top-10 → RRF fusion → hosted `bge-reranker-v2-m3` rerank → top 3 → DeepSeek chat → synchronous response.
- `sources[].score` is the rerank score (0–1, higher = more relevant).
- All hosted calls are mocked in tests; no endpoint test ever hits a live key.
