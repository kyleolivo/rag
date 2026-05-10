# Condo RAG — Roadmap

Bite-sized chunks in build order. Each chunk is sized to be a single focused
session. Every chunk lists *Goal · Scope · Decisions to wrestle with · Done
when*, so you can pick one up cold.

C3 (retrieval & ranking) is intentionally the deepest section — it's the
focus area, and several sub-chunks each warrant their own session.

---

## C1 — Ingestion v0

**Goal**: turn a folder of PDFs into rows in Postgres.

**Scope**:
- Walk a `docs/` directory.
- pypdf-based text extraction with per-page positions.
- Fixed-size chunking (~500 tok, 50 tok overlap).
- `documents` and `chunks` tables.
- Content-hash idempotency (re-running on the same folder is a no-op).

**Out of scope**: OCR for scanned PDFs (tracked, not built); embeddings (C2);
fancy structure-aware chunkers (revisit in C3 if eval demands).

**Decisions to wrestle with**:
- Chunk size & overlap — affects every downstream metric.
- Token counting — `tiktoken` vs. embedding-model-specific tokenizer?
- Metadata to keep — page numbers, section headings, doc type. Richer now
  = more retrieval moves later.
- Scanned-PDF detection — fall back to OCR or skip with a warning?

**Done when**: `python ingest.py docs/` populates `documents` and `chunks`
for a sample folder; re-running on the same folder is a no-op.

---

## C2 — Embedding & indexing v0

**Goal**: top-k dense retrieval works end-to-end.

**Scope**:
- Pluggable `Embedder` interface; one concrete implementation
  (Voyage `voyage-3` or OpenAI `text-embedding-3-large`).
- HNSW index in pgvector.
- `search(query, k) -> list[Chunk]` returning top-k chunks with scores.

**Out of scope**: hybrid, rerank, query rewriting (all in C3).

**Decisions**:
- Embedding model & dimension (cost vs. quality, 1024 vs. 3072).
- Distance metric (cosine vs. inner product) — usually dictated by model.
- HNSW params (`m`, `ef_construction`, `ef_search`) — start with defaults,
  note recall/latency trade-off.
- Batch size for the embedding API call.

**Done when**: an ad-hoc CLI query returns 5 plausible chunks against the
sample corpus.

---

## C3 — Retrieval & ranking (deep dive)

The focus area. Broken into sub-sessions; each is a standalone chunk.

### C3a — Hybrid search

Add Postgres FTS on `chunks.text`. Implement Reciprocal Rank Fusion (RRF)
over dense top-N + FTS top-N. Compare hybrid vs. dense-only on a small
hand-built query set.

**Decisions**: RRF `k` constant; per-source weighting; FTS tokenization
config (`english`, custom stopwords for condo jargon).

### C3b — Query rewriting / expansion

Use a small LLM call to rewrite the question into 2–3 retrieval-friendly
variants (e.g. "What's our deductible on water damage?" →
`["water damage deductible", "insurance policy water claim deductible amount"]`)
and union the results.

**Decisions**: when to bypass rewriting (latency cost on every query);
caching rewrites by question hash.

### C3c — Reranking

Add a cross-encoder rerank pass: top-N candidates → top-k. Compare a hosted
reranker (Voyage rerank, Cohere) against Claude Haiku 4.5 as a reranker.

**Decisions**: N for rerank input (50? 100?); latency budget; whether to
ship at all (gate on the golden-set delta).

### C3d — Metadata filters & boosts

Detect query intent ("What does the bylaws say about X" →
`filter doc_type = 'bylaws'`). Add per-doc-type boosts (recent meeting
minutes weighted higher for "what did they decide" queries).

**Decisions**: rule-based vs. LLM-based intent detection; how to express
boosts (additive on score vs. multiplicative on rank).

### C3e — Retrieval metrics

Build a 30-question golden set with the ideal source documents/chunks
marked. Compute recall@k, MRR, nDCG. This becomes the regression bar for
every retrieval change above.

**Done when**: a single command prints retrieval metrics and a per-query
breakdown for the golden set.

---

## C4 — Generation

**Goal**: produce cited, grounded answers.

**Scope**:
- Prompt template + chunk formatting.
- Refusal path when retrieved context is weak.
- Structured output (JSON: `answer`, `cited_chunk_ids`); render
  human-readable citations server-side from chunk metadata.
- Anthropic SDK with prompt caching on the system prompt.

**Decisions**:
- How much context to include (top-k value, total token budget).
- Model tiering — Sonnet 4.6 default, Haiku 4.5 for cheap path.
- How to handle conflicting chunks (e.g. amended bylaws).

**Done when**: end-to-end query returns an answer with at least one cited
chunk; refuses gracefully when retrieved chunks are off-topic.

---

## C5 — Eval harness

**Goal**: any change to retrieval or generation produces a comparable score.

**Scope**:
- Extend the golden set with ideal answers.
- LLM-as-judge (Haiku 4.5) for answer quality.
- Combined retrieval + generation report.
- Per-question cost & latency tracking.

**Decisions**: judge prompt design (judges are notoriously biased); how to
score subjective questions; whether to wire into CI.

**Done when**: `make eval` produces a report with current vs. previous run
scores.

---

## C6 — Serving

**Goal**: usable from a UI or `curl`.

**Scope**:
- FastAPI app: `POST /query`, `POST /reindex`, `GET /healthz`.
- Pydantic request/response schemas.
- Structured logging of `(query, retrieved_chunk_ids, answer, latency_ms,
  cost_usd)`.
- Tiny static HTML page that hits `/query`.

**Decisions**: streaming responses?; how to surface citations in the UI;
rate limiting (probably not for v1).

**Done when**: `uvicorn app:app` runs and questions can be asked through
the browser.

---

## Open questions (defer, don't block)

- OCR strategy for scanned PDFs (Tesseract vs. cloud OCR vs. Claude vision).
- Versioning when bylaws are amended — show "as of date X"?
- Multi-doc summarization ("summarize the last 3 board meetings").
