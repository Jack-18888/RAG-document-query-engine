# Risks & Open Questions

## Assumptions made during setup

- **Single personal user, no auth layer.** Not yet confirmed beyond the "personal / self-hosted" answer.
- **Python is the backend language** — inferred from the existing `.venv` in this directory; not explicitly stated.
- **DeepSeek API for chat generation** (OpenAI-compatible, `api.deepseek.com`), model `deepseek-v4-flash` — user-confirmed choice after reviewing the current lineup (`deepseek-v4-flash` vs `deepseek-v4-pro`; flash is ~3x cheaper, 1M context, plenty for RAG answer generation). Both models default to thinking mode; the backend explicitly disables it (`thinking: disabled`) for extractive RAG answers.
- **Pinecone for vectors AND hosted inference**: `llama-text-embed-v2` embeddings (1024-dim) + `bge-reranker-v2-m3` rerank — user's explicit choice, replacing the earlier OpenAI-embeddings / local-reranker plans.
- **Free-tier (Starter) Pinecone plan**: single serverless index, AWS `us-east-1` only; monthly caps on embedding tokens and rerank units — **user confirmed the current limits in the console**. Jobs must surface quota errors (`QUOTA_EXCEEDED` / `RESOURCE_EXHAUSTED`) as failed jobs with a clear message.
- **Pinecone index is pre-created by the user** (not auto-created by the backend); its name is read from the `PINECONE_INDEX` env var.
- **Documents have no embedded images** — user stated to assume this for now.
- **Backend docs live in this repo root**; frontend is a separate repository at `../frontend` with its own `.git`.
- **Git conventions set** — feature branches from `develop`, merged to `qa`, then `main` via PR.

## Open questions

- **httpx vs httpx2:** starlette 1.3.1's `TestClient` emits a deprecation warning advising `httpx2`; tests pass on httpx 0.28.1 today. Revisit when upstream drops httpx support.

## Resolved decisions

- **Storage layer (T01):** SQLite schema (documents/chunks/jobs + FTS5 external-content index) defined in `db_init.sql`, applied idempotently via `app/storage/db.py` on app startup; the chunks table uses its implicit rowid to back the FTS5 index.
- **Retry semantics (T16):** the shared `retry_async` helper does max 3 total attempts with exponential backoff between attempts (1s, then 4s) for transient hosted-API errors; parse errors are never retried.
- **Partial-index guarantee (T15/T27):** the ingestion worker upserts vectors to Pinecone *before* writing SQLite chunk rows, so a failed index leaves no local chunks; a whole-job re-run is not implemented — retries are per API call only. Re-ingest cleans up any stray vectors via metadata-filter delete.
- **Non-thinking mode (T18):** DeepSeek calls send `extra_body={"thinking": {"type": "disabled"}}` so `deepseek-v4-flash` answers extractively without reasoning tokens.

## Known risks / dependencies

- **Hosted API cost & availability:** Pinecone and DeepSeek calls are paid (or quota-capped on the free tier) and require network; an outage blocks ingest and query. Costs rise with re-indexing and larger libraries.
- **Free-tier inference caps:** monthly limits on embedding tokens (per model) and rerank units — a large library or heavy re-indexing can exhaust them mid-month; jobs must surface quota errors (`QUOTA_EXCEEDED` / `RESOURCE_EXHAUSTED`) as failed jobs with a clear message.
- **Pinecone embedding gotchas:** `input_type` must be `passage` for documents and `query` for questions (mixing them degrades retrieval); `bge-reranker-v2-m3` truncation defaults to `NONE`, so `truncate=END` must be passed or long chunks error.
- **Token/context limits:** large documents must be chunked well to keep retrieved context within DeepSeek's window; poor chunking degrades answer quality and citations.
- **Format parser variability:** docx/PDF/HTML parsing is imperfect in the wild; parse failures must surface cleanly via ingestion status rather than silently breaking.
