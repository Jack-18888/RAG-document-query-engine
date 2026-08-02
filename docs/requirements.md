# Requirements & Scope

## Must-haves (v1)

- **Ingestion** of PDF, docx, HTML, and Markdown documents (no images embedded for now).
- **Background ingestion jobs** — upload returns immediately with a job id; parsing, chunking, and embedding run in the background; progress is pollable.
- **Hybrid retrieval** — BM25 keyword search fused with vector similarity, then cross-encoder reranking for the final top-k.
- **Query endpoint** — returns a generated answer plus source citations (which chunks and source documents it used).
- **Document management** — list documents with ingestion status (indexed / pending / failed), delete a document and its chunks, re-index a document, and view job progress.
- **REST API** via FastAPI, serving the sibling frontend.
- **Stateless queries** — each query is independent; no conversation history.

## Nice-to-haves (later)

- Image/OCR support in documents.
- Multi-turn conversation history.
- Provider-agnostic LLM/embedding configuration (any OpenAI-compatible endpoint).
- Thin CLI wrapper over the API.

## Explicitly out of scope

- Multi-user authentication, roles, or tenant isolation (single personal user).
- Docker/container deployment.
- Self-hosted LLM serving (hosted API only).
- Images, scanned documents, or OCR.

## Users & permissions

Single personal user. No accounts, no auth layer — the API runs locally. API keys are held in a `.env` file, never in code.

## Constraints

- Runs locally on one machine (Windows dev environment), launched from the existing `.venv` with uvicorn.
- Metadata, chunks, jobs, and BM25 stay in local SQLite; vectors live in hosted Pinecone.
- Configuration via `.env` (API keys, model names).
- Respect hosted-API costs: embeddings and chat calls should not be made wastefully.
- Scale is personal — thousands of chunks, not millions.
