# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project overview

Backend for a self-hosted RAG document query engine: ingest PDF/docx/HTML/Markdown documents, then answer natural-language questions with source citations. FastAPI + uvicorn, DeepSeek API for chat, Pinecone for vectors plus hosted inference (embeddings and reranking), SQLite + FTS5 for metadata and BM25 search, in-process thread pool for ingestion jobs, pytest with mocks. Single personal user — no auth. See [README.md](README.md) for the full brief.

## Setup & commands

- Install: `pip install -r requirements.txt` into the existing `.venv`.
- Config: copy `.env.example` to `.env` and fill in `PINECONE_API_KEY`, `PINECONE_INDEX`, and `DEEPSEEK_API_KEY` (`.env` is never committed or read by agents — see `opencode.json`).
- Run/dev: `uvicorn app.main:app --reload` from the `.venv`.
- Test: `pytest` — the full suite must pass with no live API keys (LLM/embedding calls are mocked).
- Lint/format: `ruff check .` and `ruff format --check .` (ruff 0.16.1, pinned in `requirements.txt`).

## Code style & conventions

- Python, FastAPI, async where appropriate; follow existing patterns in neighboring files.
- File/folder organization: layer-based, one top-level package per concern inside `app/` — `api/` (routers + Pydantic schemas), `parsers/` (one module per format), `chunking/`, `embeddings/`, `retrieval/` (vector, bm25, fusion, reranker), `generation/`, `storage/` (db + repositories), `jobs/` (ingestion worker). Uploaded originals live under `data/uploads/`, SQLite at `data/engine.db`. Tests mirror the layout under `tests/unit/` and `tests/integration/`.
- No comments unless asked; keep code self-documenting.
- Never hardcode or log API keys, model secrets, or `.env` contents.

## Testing expectations

- Every addition (feature, fix, or behavior change) must include corresponding tests — no code without tests.
- Run `pytest` before considering a change done; all tests must pass.
- Tests must use mocks for all hosted API calls — no live keys, no network, no cost.
- Add or update tests alongside feature changes.

## Git / PR conventions

- Branch lifecycle: create feature branches from `develop`, merge them to `qa` for testing, and finally merge to `main` via PR — never skip `qa`.
- Keep commits small, focused, and descriptive — one logical change per commit.
- Commit messages: imperative mood, short subject line (≤ ~50 chars), e.g. `add ingestion pipeline` or `fix chunk overlap bug`. Add a body only when the subject needs context.
- Branch naming: `feature/<short-name>`, `fix/<short-name>`, or `chore/<short-name>`.
- Never commit generated or local-only files (`.env`, `.venv`, caches).
- Only commit when explicitly asked to.

## Documentation upkeep

- Continuously maintain the docs as part of the build process: whenever a decision is made or a TBD is resolved, update [docs/architecture.md](docs/architecture.md) and [docs/risks-and-open-questions.md](docs/risks-and-open-questions.md) in the same change that resolves it.
- Keep adding useful reference material to the docs during conversation and building — e.g., pipeline details, schemas, gotchas, and the reasoning behind choices — so future sessions can rely on them instead of re-deriving context.
- Keep [README.md](README.md) in sync with what the project actually does, and never leave the docs contradicting the code.

## Guardrails — things agents should never do without asking

- Never commit secrets: API keys, `.env` contents, or `.pem`/`.key` files. Keys live only in environment/config.
- Never add new dependencies without asking first — especially heavy ones (e.g., torch, sentence-transformers for the reranker).
- Never leave the test suite failing.
- Never modify anything under `../frontend` — this is the backend repo only; frontend is a separate repository.
- Do not deploy, publish, or expose the server beyond localhost.

## More context

- [README.md](README.md) — vision, requirements
- [docs/architecture.md](docs/architecture.md) — technical decisions
- [docs/rag-workflow.md](docs/rag-workflow.md) — ingestion/query pipelines, chunking rules, retrieval numbers, retries, citations
- [docs/endpoints.md](docs/endpoints.md) — API contract, request/response shapes, error semantics
- [docs/risks-and-open-questions.md](docs/risks-and-open-questions.md) — known risks and assumptions
