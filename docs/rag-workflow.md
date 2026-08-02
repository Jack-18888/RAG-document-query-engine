# RAG Workflows

Reference for how the engine actually processes documents and queries — the pipelines, numbers, and failure semantics agreed during design. Keep this in sync with the code.

## Conventions used below

- Job = one ingestion run for one uploaded file. Jobs run on an in-process thread pool (bounded concurrency, no external queue). Uploaded original is stored at `data/uploads/<doc_id><ext>`.
- Chunk = a unit of text with an id, stored in SQLite; its embedding is a vector in Pinecone sharing the chunk id.
- Pinecone index: serverless (free tier, AWS `us-east-1`), dimension 1024, metric cosine; every vector carries metadata: `doc_id` (indexed), and optionally `chunk_id`/`page` later. Namespaces: none (single default namespace).
- Hosted inference: embeddings via `POST /embed` (`llama-text-embed-v2`, 1024-dim, `input_type` = `passage` for docs / `query` for questions); reranking via `POST /rerank` (`bge-reranker-v2-m3`). All hosted calls are mocked in tests.

## 1. Ingestion workflow

```
upload (POST /documents)
  → create document row (status=pending) + job row (status=pending)
  → save original to data/uploads/
  → enqueue job → respond 202 with job id (document visible with status=pending)
job worker (thread pool):
  → status=parsing    parse by extension (see parsers/)
        parse failure → status=failed (fail fast, no retry)
  → status=chunking   structure-aware chunking (see chunking rules)
  → status=embedding  embed chunks via Pinecone inference, `input_type=passage`, batch size ~32 (model limit 96), sequential batches
  → status=indexing   upsert vectors into Pinecone (batch ~100), insert chunk rows + FTS5 rows in SQLite, mark doc status=indexed, job status=succeeded
```

- Document + job both expose `status`; document status is the user-facing view (`pending` / `indexed` / `failed`), job holds progress detail (`stage`, `error_message`).
- Progress: jobs report the stage and count of chunks processed; percentages are derived client-side where needed.

### Retry & failure semantics

- **Transient errors** (embedding/rerank API errors, DeepSeek errors, network, Pinecone rate limits): retry up to 3 attempts with exponential backoff (e.g., 1s → 4s → 16s), then mark job `failed` with `error_message`.
- **Parse errors** (unreadable/corrupt file, unsupported format): fail fast — no retries; `error_message` explains the reason; original file is kept so the user can inspect/re-upload.
- **Partial index** is not tolerated by default: if embedding or indexing fails for part of the chunks, the whole job retries; only after retries are exhausted does the job fail (stale vectors for that doc, if any were written, are cleaned up on re-ingest via metadata filter delete).

## 2. Chunking rules

- Structure-aware, not fixed-size: split on document structure first (headings in markdown/HTML, paragraphs in PDF/docx), then cap size.
- Target: ~500 tokens per chunk with ~50 tokens overlap (sentence-level overlap where possible).
- **Never cut a sentence in two** — if a chunk reaches the limit mid-sentence, the sentence is kept whole and the chunk may exceed the limit. Only split mid-sentence as a last resort for pathological input (e.g., an unbroken multi-thousand-token block), and note that in code comments only if needed.
- Overlap is applied between adjacent chunks so sentence context isn't lost at boundaries.
- Deterministic: same input → same chunks (stable ids derived from doc_id + chunk index).

## 3. Query workflow

```
POST /queries
  → embed question via Pinecone inference (`input_type=query`, 1024-dim)
  → vector search:        top 10 by cosine similarity (Pinecone, filtered by nothing — whole library)
  → BM25 search:          top 10 by FTS5 (SQLite)
  → fusion:               Reciprocal Rank Fusion (RRF, k=60) over the union; take top 20
  → rerank:               hosted bge-reranker-v2-m3 over the fused top 20 (top_n=3, rank_fields=["text"], truncate=END)
  → keep top 3            chunks as context
  → chat completion       DeepSeek (deepseek-chat, OpenAI-compatible), system prompt + the 3 chunks + question
  → respond               answer text + structured source list
```

- **Fusion:** RRF score = Σ 1/(k + rank), k = 60. No score normalization needed; order-independent across BM25/vector score scales.
- **Reranker:** Pinecone hosted `bge-reranker-v2-m3` (max 100 docs, 1024 tokens per query+doc pair). `truncate=END` is passed explicitly because the model default (`NONE`) would error on long chunks.
- **Top-k:** 10 + 10 → 20 → 3. Deliberately lean: 3 chunks keep LLM token cost low and citations precise.
- **Empty result:** if neither search returns candidates (or the doc library is empty), respond with a message explaining no sources were found — no LLM call is made.
- **Synchronous:** the endpoint blocks until DeepSeek finishes; expect tens of seconds on long answers.

### Prompt & citations

- System prompt: instructs the model to answer using only the provided chunks, to say so when the chunks don't contain the answer, and not to invent citations.
- **Citation format:** structured, not inline. The API response contains:
  - `answer`: the generated text (no marker tokens).
  - `sources`: list of `{chunk_id, doc_id, doc_name, excerpt, score}` for the 3 context chunks — the frontend renders citations/links itself.
- The LLM is asked to base its answer only on the provided chunks; source attribution is positional (the chunks given), not parsed from the model output.

## 4. Document management flows

- **List + status:** read documents table (id, name, format, size, status, created_at, updated_at) — no Pinecone call.
- **Delete:** one transaction — delete vector batch(es) from Pinecone via metadata filter `doc_id == X` (requires `doc_id` to be an indexed metadata field), then delete chunk rows + FTS5 rows + document row in SQLite, then delete the original file.
- **Re-index:** delete old vectors via metadata filter, reset status to `pending`, enqueue a new job, re-run ingest pipeline on the stored original (no re-upload needed).
- **Job progress:** `GET /jobs/<id>` returns stage, chunk counts, error message.

## 5. Failure modes & error surfacing

| Failure | Where | Behavior |
|---|---|---|
| Corrupt/unreadable file | parsing | job → failed, error_message set, no retry |
| Embedding API error | embedding | 3 retries with backoff, then failed |
| Pinecone unavailable | indexing | 3 retries with backoff, then failed |
| Rerank/DeepSeek unavailable | query | 3 retries with backoff, then 503 with retryable message |
| BM25/vector no results | query | no LLM call; response says no sources found |

## 6. Decisions & rationale

- **Structure-aware chunking over fixed-size:** preserves semantic boundaries (headings/paragraphs), which measurably improves retrieval and citation precision; the no-sentence-splitting rule trades a slightly larger chunk count for never-garbled text.
- **Retry transient, fail parse:** API/network errors are recoverable and common; a corrupt file will never become readable by retrying.
- **RRF over weighted scores:** no cross-system score calibration, robust, well-understood.
- **Hosted bge-reranker-v2-m3 over a local model:** one platform for vectors + inference (single API key, no torch/sentence-transformers install), and better cross-encoder quality than a tiny local model; the trade-off is per-call inference cost against the free-tier monthly rerank-unit cap.
- **DeepSeek for chat:** cheap, OpenAI-compatible API (`deepseek-chat`), plenty of quality for grounded Q&A from 3 chunks.
- **Pinecone inference for embeddings (`llama-text-embed-v2`, 1024-dim):** removes OpenAI embeddings from the stack; dimension 1024 balances free-tier storage against quality (the model supports 384–2048).
- **Metadata filter delete over id-tracking/namespaces:** single-call cleanup, no extra bookkeeping, single namespace keeps queries simple.
- **Structured sources over inline markers:** avoids relying on the LLM to emit citation tokens (which is flaky); frontend owns rendering.
