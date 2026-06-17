# Quorum

**AI-powered SEC Filing Analyst** — query 10-K filings in natural language, get source-grounded answers with structured financial tables, growth analysis, and citations.

---

## Quick start

```bash
# Backend
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev

# Or everything with Docker
docker compose up --build
```

Requires: PostgreSQL (Supabase), [Groq API key](https://console.groq.com), HuggingFace token.

---

## Pipeline

```
┌────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌────────┐
│ Ingest │ → │ Retrieve │ → │ Extract   │ → │ Generate │ → │ Verify │
│ 10-Ks  │   │ (hybrid) │   │ (Python)  │   │ (tables) │   │ (cites)│
└────────┘   └──────────┘   └───────────┘   └──────────┘   └────────┘
```

1. **Ingest** — Parse SEC 10-K HTML into sections, chunk, embed (HuggingFace `sentence-transformers/multi-qa-mpnet-base-dot-v1`), store in pgvector.
2. **Retrieve** — Hybrid search (vector + full-text, fused via RRF) with metadata pre-filtering.
3. **Extract** — Revenue, CAGR, margins, mix — computed deterministically via Python regex, never by the LLM.
4. **Generate** — Pre-computed tables first, then LLM narrative (Executive Summary, Key Findings, Analysis, Takeaway).
5. **Verify** — Coverage gaps trigger re-expansion; citations deduplicated and ticker-scoped.

---

## Key features

| Feature | Details |
|---------|---------|
| **Structured financials** | Revenue, CAGR, margins, mix — computed in Python, not hallucinated |
| **Multi-company comparison** | Side-by-side tables across tickers (AAPL vs MSFT vs NVDA) |
| **Cloud segment analysis** | AWS, Azure, Google Cloud routed to segment-specific data |
| **Risk factor diff** | Cross-year: added, removed, expanded, reduced risk language |
| **Contamination prevention** | 3-layer defense: SQL filter → post-fusion → API filter |
| **Citation integrity** | Every claim grounded with ticker, year, section, excerpt |
| **Graceful degradation** | LLM down → pre-computed tables with friendly message |
| **Streaming** | Token-by-token with thread persistence on disconnect |

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12 + FastAPI |
| Frontend | React 19 + TypeScript 6 + Vite 8 |
| Database | PostgreSQL + pgvector (Supabase) |
| Auth | Supabase Auth |
| ORM | SQLAlchemy + Alembic |
| LLM | Groq (Llama 3.3 70B) |
| Embeddings | HuggingFace Inference API (`sentence-transformers/multi-qa-mpnet-base-dot-v1`) |
| Rate limiting | Redis (shared across workers; in-memory fallback) |

---

## Setup

### Prerequisites

| Dependency | For | How |
|------------|-----|-----|
| Python 3.12+ | Backend | `uv python install` |
| Node.js 20+ | Frontend | `fnm install 20` |
| Docker | Full stack (optional) | `docker compose up` |
| Supabase project | DB + Auth | [supabase.com](https://supabase.com) |
| Groq API key | LLM | [console.groq.com](https://console.groq.com) |
| HuggingFace token | Embeddings | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |

### Backend

```bash
cp backend/.env.example backend/.env   # fill in credentials
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload   # → http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                             # → http://localhost:5173
```

### Docker

```bash
docker compose up --build               # Redis → Backend → Frontend
```

### Ingesting filings

```bash
cd backend
uv run python scripts/ingest_html.py
```

Reads `data/downloads/manifest.json`, parses SEC 10-K items, chunks, batch-embeds via HuggingFace, and writes to the database.

---

## Deployment

### Backend (Render)

| Config | Value |
|--------|-------|
| Build | `backend/Dockerfile` |
| Port | 8000 |
| Health | `/health` |
| Env | `EMBEDDING_PROVIDER=huggingface`, `HF_TOKEN=...`, all Supabase + Groq vars |

### Frontend (Vercel)

| Config | Value |
|--------|-------|
| Framework | Vite |
| Build command | `npm run build` |
| Output dir | `dist` |
| Env | `VITE_API_URL=https://backend.onrender.com` |

SPA routing handled by `vercel.json` rewrites rule.

---

## Testing

```bash
cd backend

# 138 unit tests (no network)
uv run pytest -v -m "not eval"

# 19 retrieval quality tests
uv run pytest tests/test_retrieval_eval.py -v

# 61 full eval suite tests (requires backend + LLM key)
uv run pytest tests/eval_suite.py -v -m eval
```

---

## Production hardening

| Category | Implementation |
|----------|---------------|
| **Auth** | All endpoints authenticated; Supabase errors sanitized |
| **Secrets** | `hide_password=True` on all DB URLs; no hardcoded creds |
| **Rate limiting** | Redis sliding window (auth 10/min, chat 30/min); in-memory fallback |
| **Connection pool** | `pool_size=20, max_overflow=10, pool_timeout=30` |
| **N+1 prevention** | `selectinload` for thread → messages → citations |
| **Input limits** | 10 MB request body cap; 120s LLM timeout |
| **Security headers** | CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy |
| **Logging** | JSON structured (`QUORUM_ENV=production`); correlation IDs on every request |
| **Container** | Non-root `quorum` user in Dockerfile |
| **Request tracing** | Correlation ID middleware; included in 500 error responses |
| **Startup validation** | DB connectivity checked on boot |

---

## Environment variables

All configuration lives in `backend/.env`. The full list:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SUPABASE_URL` | Yes | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | — | Supabase public anon key (frontend-safe) |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | — | Supabase secret key (backend only) |
| `GROQ_API_KEY` | Yes | — | Groq or OpenRouter API key for LLM |
| `DB_HOST` | Yes | `localhost` | PostgreSQL host |
| `DB_PORT` | — | `5432` | PostgreSQL port |
| `DB_NAME` | — | `postgres` | Database name |
| `DB_USER` | Yes | `postgres` | Database user |
| `DB_PASSWORD` | Yes | — | Database password |
| `REDIS_URL` | — | `redis://localhost:6379/0` | Redis connection string |
| `ALLOWED_ORIGINS` | — | `http://localhost:5173` | CORS origins (comma-separated) |
| `GROQ_LLM_MODEL` | — | `llama-3.3-70b-versatile` | LLM model name |
| `LLM_BASE_URL` | — | `https://api.groq.com/openai/v1` | Override for OpenRouter etc. |
| `EMBEDDING_PROVIDER` | — | `huggingface` | Embedding provider (`huggingface` or `ollama`) |
| `EMBEDDING_MODEL` | — | `sentence-transformers/multi-qa-mpnet-base-dot-v1` | Embedding model name |
| `EMBEDDING_DIMENSIONS` | — | `768` | Vector dimensions |
| `HF_TOKEN` | — | — | HuggingFace API token |
| `OLLAMA_BASE_URL` | — | `http://localhost:11434/v1` | Ollama API endpoint (fallback) |
| `QUORUM_ENV` | — | `development` | `production` enables JSON logging |

---

## Design decisions

| Decision | Rationale |
|----------|-----------|
| **Python regex for financials, not LLM** | Numbers hallucinate easily. CAGR, margins, revenue mix are computed deterministically from chunk text. The LLM only writes narrative around pre-verified tables. |
| **Hybrid search (vector + FTS)** | Vector search finds semantic matches; full-text search catches exact ticker names, section headers, and year references. RRF fusion combines both without tuning weights. |
| **Metadata pre-filtering, not post-filtering** | Extracting tickers and fiscal years from the query and applying them as SQL `WHERE` clauses prevents cross-company contamination before ranking — much cheaper than filtering 100+ results after fusion. |
| **Redis-backed rate limiting** | In-memory dicts reset on restart and don't share across workers. Redis sorted sets provide accurate sliding windows that survive deploys and scale horizontally. |
| **Structured tables before LLM narrative** | The most valuable output (numbers) is computed first and always returned, even if the LLM call fails. The narrative is secondary. |
| **HuggingFace over Ollama for production** | HF Inference API requires no local GPU, works serverless, and uses the same `sentence-transformers` model (768d). Ollama remains a local dev fallback. |
| **Batch embedding during ingestion** | HuggingFace's API supports batching, reducing the number of API calls by ~100x vs individual embedding calls. |

---

## Project structure

```
quorum/
├── AGENTS.md
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint + startup validation
│   │   ├── config.py            # Pydantic settings (single env source)
│   │   ├── api/                 # HTTP routers (chat, auth, documents)
│   │   ├── domain/
│   │   │   ├── extraction.py    # Financial fact extraction (Python, not LLM)
│   │   │   ├── rag.py           # Answer generation + citation building
│   │   │   ├── retrieval.py     # Hybrid search + RRF + metadata filters
│   │   │   ├── embeddings.py    # Ollama/HuggingFace embedding providers
│   │   │   ├── coverage.py      # Evidence coverage validation
│   │   │   └── workflows.py     # Intent-aware prompt selection
│   │   ├── core/
│   │   │   ├── rate_limiter.py  # Redis-backed sliding-window rate limiter
│   │   │   ├── logging.py       # JSON structured logging
│   │   │   └── deps.py          # FastAPI DI
│   │   ├── models/              # SQLAlchemy models
│   │   └── schemas/             # Pydantic schemas
│   ├── scripts/ingest_html.py   # SEC filing ingestion pipeline
│   ├── tests/                   # 157 tests (138 unit + 19 retrieval eval)
│   ├── alembic/                 # Database migrations
│   ├── Dockerfile
│   ├── railway.toml
│   └── pyproject.toml
├── frontend/
│   ├── src/                     # React components, API client, Supabase client
│   ├── vercel.json              # Vercel deployment config (SPA rewrites)
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── docker-compose.yml           # Backend + frontend + Redis
└── data/downloads/              # Raw SEC HTML filings + manifest.json
```

---

## Example queries

Try these after ingesting the SEC filing corpus:

```
What was Apple's total revenue in 2024?
Compare AWS, Azure, and Google Cloud revenue over the last 3 years
How did NVIDIA's Data Center revenue grow from 2021 to 2025?
What risk factors did Amazon add in 2024?
Compare margins for AAPL, MSFT, and GOOGL
What percentage of Apple's revenue comes from iPhone?
```

---

## License

Proprietary — Driftwood Capital internal use. Not licensed for redistribution.
