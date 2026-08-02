# RAG Document Query Engine — Backend

## Overview

A self-hosted backend for a RAG (Retrieval-Augmented Generation) document query engine: upload your own documents (PDF, Word, HTML, Markdown), then ask natural-language questions and get answers with source citations. Built for a single personal user running locally — no auth, no tenants, no extra infrastructure. The frontend lives in a sibling `frontend/` repository and talks to this backend over REST.

## Goals / success criteria

- Ingest a personal library of PDF/docx/HTML/Markdown documents and keep them queryable with accurate, citable answers.
- Every answer includes the source chunks and documents it was drawn from.
- Runs locally with hosted services (DeepSeek for chat, Pinecone for vectors + embeddings + reranking) and local SQLite for metadata — no self-hosted model or vector infrastructure.

## Requirements

**Must-haves (v1):** ingest the four formats above via background jobs with progress; hybrid retrieval (BM25 keyword + vector) with cross-encoder reranking; query API returning answer + source citations; document management (list + status, delete, re-index); stateless queries; REST API.

**Nice-to-haves (later):** images/OCR support, multi-turn conversations, provider-agnostic LLM config, CLI wrapper.

**Out of scope:** multi-user auth/tenancy, Docker deployment, images/OCR, conversation history.

See [docs/requirements.md](docs/requirements.md) for the full list.

## More documentation

- [AGENTS.md](AGENTS.md) — how AI coding agents should work in this repo
- [docs/architecture.md](docs/architecture.md) — technical approach
- [docs/requirements.md](docs/requirements.md) — full requirements detail
- [docs/rag-workflow.md](docs/rag-workflow.md) — ingestion/query pipelines, chunking, retrieval numbers, retries
- [docs/endpoints.md](docs/endpoints.md) — API contract
- [docs/risks-and-open-questions.md](docs/risks-and-open-questions.md) — assumptions, open questions, risks
