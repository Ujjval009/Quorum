# Quorum Architecture

## Purpose

Quorum is an AI-powered SEC filing analyst that provides grounded answers from a curated 10-K corpus. Every answer is generated from retrieved source passages, every factual claim is citable, and the system fails clearly when the corpus does not support an answer.

## High-Level Architecture

```
┌──────────┐     ┌───────────┐     ┌────────────┐
│ Browser  │────→│  FastAPI  │────→│ PostgreSQL │
│ React    │     │  Uvicorn  │     │ + pgvector │
│ Vite     │     │  Redis    │     │ Supabase   │
└──────────┘     └─────┬─────┘     └────────────┘
                       │
               ┌───────▼───────┐
               │   Groq LLM    │
               │  Llama 3.3 70B│
               └───────────────┘
                       │
               ┌───────▼───────┐
               │  HuggingFace  │
               │  Inference API│
               │ (embeddings)  │
               └───────────────┘
```

**Two core paths:**

1. **Ingestion** — Parse SEC 10-K HTML → extract sections → chunk → embed (HuggingFace) → store in pgvector
2. **Query** — User question → hybrid search (vector + FTS, RRF fusion) → deterministic extraction → tables first, LLM narrative second → citation building

## Stack

| Layer | Tech | Purpose |
|-------|------|---------|
| Frontend | React 19 + TypeScript 6 + Vite 8 | SPA, routing, streaming chat UI |
| Backend | Python 3.12 + FastAPI | API, retrieval, LLM orchestration |
| Database | PostgreSQL + pgvector (Supabase) | Vectors, full-text search, chat persistence |
| Auth | Supabase Auth | Email login, JWT sessions |
| LLM | Groq (Llama 3.3 70B) | Answer generation |
| Embeddings | HuggingFace Inference API | Vector embeddings for search |
| Rate limiting | Redis (in-memory fallback) | Sliding window per user |

## Request Flow

1. User authenticates via Supabase Auth (JWT)
2. User query → Vite dev server / nginx → FastAPI
3. FastAPI verifies JWT via Supabase, extracts ticker/year from query text
4. Intent detection routes to appropriate workflow (revenue_mix, financial_metrics, etc.)
5. Hybrid search runs two parallel queries:
   - pgvector cosine similarity on chunk embeddings
   - Postgres full-text search on chunk text
6. RRF fusion combines results; metadata pre-filtering prevents cross-company contamination
7. Deterministic extraction computes financial metrics from returned chunks (Python regex, no LLM)
8. Structured tables are rendered (always returned first, even on LLM failure)
9. LLM generates narrative answer grounded in citations
10. Answer + citations streamed to browser via SSE; persisted to DB

## Data Model

### Core tables

- `profiles` — one row per authenticated user, keyed by Supabase `auth.users.id`
- `chat_threads` — thread metadata, owner, title, timestamps
- `chat_messages` — user and assistant messages in order
- `message_citations` — normalized citation records linked to assistant messages
- `source_documents` — original document records with filing metadata
- `document_chunks` — chunk text, metadata, embeddings, and generated full-text search vectors

### Indexes

- HNSW on `embedding` (cosine distance) for vector search
- GIN on `search_vector` (tsvector) for full-text search
- B-tree on `(ticker, fiscal_year)` for metadata filtering

## Deployment

- **Backend:** Render (Docker, `backend/Dockerfile`)
- **Frontend:** Vercel (Vite build, SPA rewrites in `vercel.json`)
- **Database:** Supabase (hosted PostgreSQL + pgvector)
- **Embeddings:** HuggingFace Inference API (no GPU needed)

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Python regex for financials, not LLM** | Numbers hallucinate easily. CAGR, margins, revenue mix are computed deterministically. |
| **Hybrid search (vector + FTS)** | Vector finds semantic matches; full-text catches exact ticker/section names. RRF fusion combines both. |
| **Metadata pre-filtering** | Extract tickers/years from query → SQL `WHERE` clauses before ranking. Prevents cross-company contamination. |
| **Tables before narrative** | Structured data is the primary output, LLM narrative is secondary. Tables render even if LLM fails. |
| **HuggingFace for production embeddings** | Serverless Inference API, no local GPU required. Ollama remains a local dev fallback. |
| **Batch embedding during ingestion** | ~100x fewer API calls vs individual embedding, using HuggingFace's batch `feature_extraction`. |
