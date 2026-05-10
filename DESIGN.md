# Condo RAG — System Design

A RAG system over the documents of a single condo building (bylaws, rules &
regs, insurance policies, financial statements, board meeting minutes, vendor
contracts, maintenance reports). Built primarily as a vehicle for learning
AI system design, with retrieval & ranking as the area of greatest depth.

## Problem & users

- **One user, one building.** No auth, no multi-tenancy.
- **Corpus**: ~50–500 PDFs, mix of digitally-generated and scanned. Single-digit
  GB total. Updates infrequent (monthly-ish: new meeting minutes, an amended
  policy).
- **Use cases**:
  - "What's the pet policy?"
  - "What's our deductible on water-damage claims?"
  - "When was the last roof inspection and what did it find?"
  - "What was decided about the pool fence at the last board meeting?"

## Functional requirements

- Natural-language Q&A over the corpus.
- Every claim in the answer must cite the source document (and ideally page
  / section).
- Refuse — say "I don't know based on the provided documents" — when the
  retrieved context doesn't support an answer.
- Re-ingestion on demand when documents are added or replaced.

## Non-functional requirements

| Dimension     | Target (v1)                                          |
|---------------|------------------------------------------------------|
| Latency       | p95 < 5s end-to-end on warm cache                    |
| Cost          | < $0.05 per query (embeddings + LLM, amortized)      |
| Correctness   | No fabricated policy claims — refusal preferred      |
| Freshness     | On-demand reindex; not real-time                     |
| Scale (v1)    | ≤ 1M chunks, single user                             |

## Out of scope (v1)

Auth, multi-tenant / multi-building, document-upload UI, write-back actions
(filing maintenance requests), real-time updates, conversation memory.

## High-level architecture

```mermaid
flowchart LR
    subgraph Ingestion[Ingestion - offline batch]
        A[docs/ folder PDFs] --> B[Parser]
        B --> C[Chunker]
        C --> D[Embedder]
        D --> E[(Postgres + pgvector)]
        C --> E
    end
    subgraph Query[Query path - online]
        Q[User question] --> R[Query rewriter]
        R --> S[Hybrid retriever<br/>dense + FTS]
        E -.read.-> S
        S --> RR[Reranker]
        RR --> G[Generator<br/>Claude w/ cited prompt]
        G --> ANS[Answer + citations]
    end
    subgraph Eval[Eval - offline]
        GS[Golden Q&A set] --> EVAL[Run pipeline + score]
        EVAL --> REPORT[recall@k, MRR,<br/>LLM-judge score]
    end
```

## Components

**Ingestion pipeline (offline batch).** Walks a `docs/` directory, classifies
each file (text-PDF vs. scanned/image-heavy), parses to text with per-page
positions, splits into chunks with overlap, embeds, and writes to Postgres.
Idempotent on a content hash so re-runs only embed new or changed chunks.

**Index (Postgres + pgvector).** A single Postgres instance holds:
- `documents` — metadata (path, title, doc type, sha256, ingested_at).
- `chunks` — text + page span + `embedding vector(1024)` + `tsv tsvector`
  for full-text search.
- HNSW index on the vector column; GIN on the tsvector.

**Retriever.** Given a query: optionally rewrite/expand → hybrid search
(dense top-N ⊕ FTS top-N, fused via Reciprocal Rank Fusion) → optional
cross-encoder rerank → return top-k chunks with scores and metadata.

**Generator.** Takes the question and top-k chunks and prompts Claude
(Sonnet 4.6 by default) with strict citation rules and a refusal escape hatch.
Output is structured (JSON with `answer` and `cited_chunk_ids`) so citations
are rendered server-side from chunk metadata rather than trusted from the
LLM's free text. System prompt is prompt-cached.

**Eval harness (offline).** Hand-built golden set of ~30
`(question, ideal-answer-spans, ideal-citation-doc)` tuples. Computes
recall@k / MRR for retrieval and LLM-as-judge (Haiku 4.5) for answer
quality. Run on every "release" of the pipeline to catch regressions.

**API (FastAPI).** `POST /query` returns answer + citations;
`POST /reindex` triggers ingestion. No auth in v1.

## Stack

- **Python** — interview default, rich ecosystem.
- **PostgreSQL + pgvector** — picked over Pinecone/Weaviate because (a) it
  forces interesting design discussions about ANN index types (HNSW vs.
  IVFFlat) and hybrid search in one system, and (b) it's trivially
  swappable later, which is itself a useful trade-off conversation.
- **Embeddings** — start with a hosted model (Voyage `voyage-3` or OpenAI
  `text-embedding-3-large`) behind a pluggable interface, so we can compare
  to a local `sentence-transformers` model later.
- **Generation** — Claude Sonnet 4.6 (with Haiku 4.5 for cheap eval loops).
  Anthropic SDK with prompt caching on the system prompt.
- **API** — FastAPI.
- **Parsing** — `pypdf` for text PDFs; `unstructured` or Claude vision for
  scanned/complex docs (covered as a decision in C1).

## Data model (sketch)

```
documents(id, path, title, doc_type, sha256, page_count, ingested_at)
chunks(id, document_id, page_start, page_end, text,
       embedding vector(1024), tsv tsvector,
       token_count, embedding_model)
queries(id, question, retrieved_chunk_ids[], answer,
        latency_ms, cost_usd, ts)
```

`embedding_model` on `chunks` lets us dual-index during a model migration
without losing the old embeddings.

## Key trade-offs (the meaty bits)

- **Chunk size.** Small chunks (~200 tok) → precise retrieval but lose
  context. Large chunks (~1000 tok) → context but noisier retrieval. Plan:
  start at 500 tok with 50 tok overlap, revisit after eval.
- **Dense-only vs. hybrid.** Condo docs are full of named entities
  ("Article XII", "Pool Rules", specific dollar amounts). Keyword recall
  matters; hybrid is worth the extra system. Covered in C3a.
- **Rerank or not.** Cross-encoder rerank usually moves precision@k but
  costs 100–300ms and money. Plan: gate it behind eval — only ship if
  the golden set says it helps.
- **Citations.** Free-form citations from the LLM are unreliable. Constrain
  output (JSON with `cited_chunk_ids`) and render the human-readable
  citation server-side from chunk metadata.
- **pgvector vs. dedicated vector DB.** pgvector trades raw ANN performance
  for one-system simplicity and free hybrid search. At our scale (≤1M
  chunks) this is the right call; at 100M chunks we'd revisit.
- **Embedding model lock-in.** Changing models means a full re-embed.
  Mitigation: pluggable embedder; record `embedding_model` per chunk.

See `ROADMAP.md` for the bite-sized chunks of work that build this out.
