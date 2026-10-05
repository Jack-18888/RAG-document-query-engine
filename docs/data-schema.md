# Data Schema

Reference for the SQLite schema defined in `data/db_init.sql` — the single source of truth, applied idempotently on app startup by `app/storage/db.py` (lifespan). The database file lives at `data/engine.db` (path configurable via settings).

## Storage engine notes

- SQLite accessed asynchronously via **aiosqlite** (shared connection, `row_factory = Row`).
- FTS5 powers BM25 keyword search over chunk text (see `chunks_fts` below).
- Timestamps are ISO-8601 UTC strings (`%Y-%m-%dT%H:%M:%SZ`) written by the repositories, not SQLite's default `CURRENT_TIMESTAMP` format.
- ID conventions: `doc_<12-hex>`, `job_<12-hex>`, `query_<12-hex>` (truncated UUID hex); chunk ids are deterministic `chunk_<doc_id>_<index>`.
- Vectors and document originals live **outside** SQLite: embeddings/vectors in Pinecone (same chunk ids) and uploaded files on disk under `data/uploads/`.

## Tables

### `documents` — metadata + ingestion status

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT | PK, `doc_<12-hex>` |
| `name` | TEXT | original filename |
| `format` | TEXT | `pdf` / `docx` / `html` / `htm` / `md` |
| `size_bytes` | INTEGER | upload size |
| `status` | TEXT | `pending` / `indexed` / `failed` |
| `error_message` | TEXT | null unless `failed` |
| `created_at` | TEXT | ISO-8601 UTC |
| `updated_at` | TEXT | refreshed on status/error changes |

### `chunks` — chunk text + document refs

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT | PK, `chunk_<doc_id>_<index>` |
| `doc_id` | TEXT | FK → `documents.id` |
| `chunk_index` | INTEGER | position within the document |
| `text` | TEXT | chunk body (heading path prepended) |
| `tokens` | INTEGER | word-count estimate, stored at ingest |

The table's implicit `rowid` is the key shared with the FTS index below.

### `chunks_fts` — FTS5 virtual table (BM25 search)

External-content virtual table mirroring `chunks` (`content='chunks'`, `content_rowid='rowid'`). It is **not** written directly; three triggers keep it in sync:

| Trigger | Fires | Action |
|---|---|---|
| `chunks_auto_insert` | AFTER INSERT on `chunks` | index `new.rowid` / `new.text` |
| `chunks_auto_delete` | AFTER DELETE on `chunks` | delete `old.rowid` |
| `chunks_auto_update` | AFTER UPDATE OF `text` | delete old, re-index new |

BM25 ranking queries this table (`ORDER BY bm25(chunks_fts)`).

### `jobs` — ingestion job progress

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT | PK, `job_<12-hex>` |
| `document_id` | TEXT | FK → `documents.id` |
| `stage` | TEXT | `parsing` / `chunking` / `embedding` / `indexing` / `succeeded` / `failed` |
| `chunks_processed` | INTEGER | progress counter |
| `chunks_total` | INTEGER | null until known |
| `error_message` | TEXT | null unless `failed` |
| `created_at` | TEXT | ISO-8601 UTC |
| `updated_at` | TEXT | refreshed on stage changes |

### `queries` — question + generated answer

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT | PK, `query_<12-hex>` |
| `question` | TEXT | the asked question |
| `answer` | TEXT | generated answer (or the canned no-sources message) |
| `created_at` | TEXT | ISO-8601 UTC |

### `query_chunks` — chunks fetched per query

| Column | Type | Notes |
|---|---|---|
| `query_id` | TEXT | FK → `queries.id` |
| `chunk_id` | TEXT | FK → `chunks.id` |
| `score` | REAL | query-specific rerank score (0–1) |

Composite PK (`query_id`, `chunk_id`). Insertion order (`rowid`) preserves citation order.

## Indexes

| Index | Table | Purpose |
|---|---|---|
| `idx_chunks_doc_id` | `chunks` | accelerate per-document lookups/deletes |
| `idx_jobs_document_id` | `jobs` | accelerate per-document job lookups |
| `idx_query_chunks_chunk_id` | `query_chunks` | reverse lookup: which queries referenced a chunk |

## Relationships

```
documents 1 ──── N chunks        documents 1 ──── N jobs
                   │ 1
                   │
                   N
               query_chunks N ──── 1 queries
```

The `query_chunks → chunks` link is *soft*: query sources are reconstructed by join (`query_repo.get_sources`), so deleting a chunk/document silently drops that citation from historical query details.

## Gotchas

- **FKs are declared but not enforced.** `PRAGMA foreign_keys` is never enabled, so `ON DELETE CASCADE` clauses are inert. Deletes are therefore explicit in the repositories (e.g. `query_repo.delete` removes `query_chunks` before `queries`; document deletion removes chunks before the document row). This is a deliberate, codebase-wide convention.
- `db_init.sql` is idempotent — rerunning it is safe (all objects use `IF NOT EXISTS`).
