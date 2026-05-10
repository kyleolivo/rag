-- Run once to set up the schema:
--   createdb condo_rag
--   psql condo_rag < db/schema.sql
--
-- C2 will add: chunks.embedding (vector), chunks.tsv (tsvector), HNSW + GIN indexes.

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    path        TEXT NOT NULL,
    title       TEXT,
    doc_type    TEXT,
    sha256      TEXT NOT NULL UNIQUE,
    page_count  INTEGER,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    page_start      INTEGER,
    page_end        INTEGER,
    text            TEXT NOT NULL,
    token_count     INTEGER NOT NULL,
    embedding_model TEXT            -- populated in C2
);
