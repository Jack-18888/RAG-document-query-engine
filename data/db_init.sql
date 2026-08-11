-- Documents (metadata + ingestion status)
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    format TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Chunks (text + document refs); the table's implicit rowid backs the FTS5 index
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    tokens INTEGER NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- FTS5 Virtual Table for Text Search (external-content, mirrors the chunks table)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='rowid'
);

-- Triggers for auto-insert
CREATE TRIGGER IF NOT EXISTS chunks_auto_insert AFTER INSERT ON chunks
BEGIN
    INSERT INTO chunks_fts(rowid, text)
    VALUES (new.rowid, new.text);
END;

-- Triggers for auto-delete
CREATE TRIGGER IF NOT EXISTS chunks_auto_delete AFTER DELETE ON chunks
BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text)
    VALUES ('delete', old.rowid, old.text);
END;

-- Triggers for auto-update
CREATE TRIGGER IF NOT EXISTS chunks_auto_update AFTER UPDATE OF text ON chunks
BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text)
    VALUES ('delete', old.rowid, old.text);

    INSERT INTO chunks_fts(rowid, text)
    VALUES (new.rowid, new.text);
END;

-- Ingestion jobs (stage-level progress)
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'parsing',
    chunks_processed INTEGER NOT NULL DEFAULT 0,
    chunks_total INTEGER,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Queries (question + generated answer)
CREATE TABLE IF NOT EXISTS queries (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Which chunks were fetched for each query (query-specific rerank score)
CREATE TABLE IF NOT EXISTS query_chunks (
    query_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    score REAL NOT NULL,
    PRIMARY KEY (query_id, chunk_id),
    FOREIGN KEY (query_id) REFERENCES queries(id) ON DELETE CASCADE,
    FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_jobs_document_id ON jobs(document_id);
CREATE INDEX IF NOT EXISTS idx_query_chunks_chunk_id ON query_chunks(chunk_id);
