# Risks & Open Questions

## Assumptions made during setup

- **Single personal user, no auth layer.** Not yet confirmed beyond the "personal / self-hosted" answer.
- **Python is the backend language** — inferred from the existing `.venv` in this directory; not explicitly stated.
- **DeepSeek API for chat generation** (OpenAI-compatible, `deepseek-chat` model assumed — exact model name not confirmed with user; user will provide `DEEPSEEK_API_KEY`).
- **Pinecone for vectors AND hosted inference**: `llama-text-embed-v2` embeddings (1024-dim) + `bge-reranker-v2-m3` rerank — user's explicit choice, replacing the earlier OpenAI-embeddings / local-reranker plans.
- **Free-tier (Starter) Pinecone plan**: single serverless index, AWS `us-east-1` only; monthly caps on embedding tokens and rerank units (verify current limits in the console).
- **Documents have no embedded images** — user stated to assume this for now.
- **Backend docs live in this repo root**; frontend is a separate repository at `../frontend` with its own `.git`.
- **Git conventions set** — feature branches from `develop`, merged to `qa`, then `main` via PR.

## Open questions

- Exact DeepSeek chat model name (assuming `deepseek-chat`; confirm against the user's key/plan).
- Lint/format tooling for the repo (ruff, black, mypy?) — undecided until the stack is scaffolded.
- Pinecone index name and whether the index is pre-created by the user or auto-created by the backend on startup.

## Known risks / dependencies

- **Hosted API cost & availability:** Pinecone and DeepSeek calls are paid (or quota-capped on the free tier) and require network; an outage blocks ingest and query. Costs rise with re-indexing and larger libraries.
- **Free-tier inference caps:** monthly limits on embedding tokens (per model) and rerank units — a large library or heavy re-indexing can exhaust them mid-month; jobs must surface quota errors (`QUOTA_EXCEEDED` / `RESOURCE_EXHAUSTED`) as failed jobs with a clear message.
- **Pinecone embedding gotchas:** `input_type` must be `passage` for documents and `query` for questions (mixing them degrades retrieval); `bge-reranker-v2-m3` truncation defaults to `NONE`, so `truncate=END` must be passed or long chunks error.
- **Token/context limits:** large documents must be chunked well to keep retrieved context within DeepSeek's window; poor chunking degrades answer quality and citations.
- **Format parser variability:** docx/PDF/HTML parsing is imperfect in the wild; parse failures must surface cleanly via ingestion status rather than silently breaking.
