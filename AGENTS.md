# Agent Instructions

## Stack

- **Backend:** Python 3.14 + FastAPI
- **Frontend:** React 19 + TypeScript 6 + Vite 8
- **Database:** PostgreSQL + pgvector (Supabase)
- **Auth:** Supabase Auth
- **LLM:** Groq (Llama 3.3 70B)
- **Embeddings:** Ollama `nomic-embed-text` (local)
- **Rate Limiting:** Redis (shared across workers; in-memory fallback)

## Repo layout

```
quorum/
├── AGENTS.md
├── README.md
├── docker-compose.yml             # Local: backend + frontend + redis
├── data/
│   └── downloads/                 # Raw SEC HTML filings + manifest.json
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── railway.toml               # Railway healthcheck config
│   ├── .env.example
│   ├── alembic/
│   ├── scripts/
│   │   └── ingest_html.py         # SEC filing ingestion pipeline
│   ├── tests/
│   │   ├── test_extraction.py
│   │   ├── test_rag.py
│   │   ├── test_retrieval.py
│   │   ├── test_risk_diff.py
│   │   ├── test_auth.py
│   │   ├── test_retrieval_eval.py # 19 retrieval quality tests
│   │   ├── smoke_test_queries.py
│   │   └── eval_suite.py          # 52 regression eval queries (mark: eval)
│   └── app/
│       ├── main.py                # FastAPI entrypoint + startup validation
│       ├── config.py              # Pydantic settings (single env source)
│       ├── api/
│       │   ├── chat.py            # Threads + ask + streaming + rate limiter
│       │   ├── auth.py            # Login/signup + rate limiter
│       │   └── documents.py       # SEC filing browser
│       ├── core/
│       │   ├── deps.py            # FastAPI DI
│       │   ├── logging.py         # JSON logging (production) / console (dev)
│       │   └── rate_limiter.py    # Redis-backed sliding-window rate limiter
│       ├── domain/
│       │   ├── extraction.py      # Financial fact extraction (Python, not LLM)
│       │   ├── rag.py             # Answer generation + citation building
│       │   ├── retrieval.py       # Hybrid search + RRF fusion + intent + metadata filtering
│       │   ├── coverage.py        # Evidence coverage validation
│       │   ├── workflows.py       # Intent-aware prompt selection
│       │   ├── comparison.py      # Multi-ticker comparison
│       │   ├── revenue_mix.py
│       │   └── risk_diff.py
│       ├── models/
│       │   ├── base.py            # Engine, SessionLocal, TimestampMixin, UUIDMixin
│       │   ├── document.py        # SourceDocument, DocumentChunk
│       │   ├── chat.py            # ChatThread, ChatMessage, MessageCitation
│       │   └── profile.py
│       └── schemas/
└── frontend/
    ├── package.json
    ├── Dockerfile
    ├── Dockerfile.railway          # Railway-optimised (no certs, plain HTTP)
    ├── nginx.conf                  # Local: HTTPS + self-signed certs
    ├── nginx.conf.railway          # Railway: plain HTTP (TLS at edge)
    ├── certs/
    │   ├── localhost.crt           # Self-signed TLS cert for local dev
    │   └── localhost.key
    └── src/
        ├── App.tsx
        ├── components/
        │   ├── Chat.tsx            # Main chat interface + streaming
        │   ├── AuthContext.tsx
        │   ├── Login.tsx
        │   ├── Signup.tsx
        │   └── Documents.tsx
        ├── api/quorum.ts
        └── lib/supabase.ts
```

## Rules

- Type hints everywhere. Async by default in request-path code.
- No `os.getenv` in app code — use `app.config.settings`.
- Validate at boundaries only (HTTP input, external APIs, DB writes).
- **Financial metrics must be computed in Python, never by the LLM** — growth rates, CAGR, margins, revenue shares are deterministic extraction in `extraction.py`.
- **Structured tables must be rendered before LLM narrative** — pre-computed tables are always the primary output, LLM narrative is secondary.
- **Cross-company contamination must be prevented** — three-layer defense: SQL filter → post-fusion filter → API filter.
- **Citation integrity** — every citation must carry ticker, fiscal_year, section_title, excerpt. No duplicate chunk IDs.
- **All tests must pass** before merging. Run `pytest -m "not eval"` for fast checks.

## Key architecture

- **Pipeline:** Ingest → Retrieve (hybrid search + RRF) → Extract (deterministic) → Generate (tables first, then LLM) → Verify (coverage + citations)
- **Intent detection** maps queries to workflows: `revenue_mix`, `financial_metrics`, `company_comparison`, `risk_factor_diff`, `ai_disclosure`, `segment`, `general`
- **Metadata pre-filtering** — `extract_filters(query)` returns tickers + fiscal years using `TICKER_ALIASES` map; applied as SQL `WHERE` pre-filter in both vector and FTS searches
- **Segment queries** (AWS, Azure, Google Cloud) must never fall back to total-company metrics
- **Evidence expansion** — if coverage validation finds gaps, `expand_coverage()` broadens the search
- **Rate limit resilience** — LLM failures return pre-computed tables with a friendly message; streaming saves messages in `finally` block to survive client disconnects
- **Request tracing** — correlation ID generated per request via middleware; included in 500 error responses
- **Startup validation** — DB connectivity checked on boot; logs `database=True|False`

## Common commands

```bash
# Backend
uv run uvicorn app.main:app --reload              # dev server
uv run pytest -v -m "not eval"                     # fast unit tests (138 tests)
uv run pytest tests/eval_suite.py -v -m eval       # full eval suite
uv run ruff check .                                # lint
uv run alembic upgrade head                        # migrations

# Frontend
npm run dev                                        # dev server
npm run build                                      # production build

# Ingestion
uv run python scripts/ingest_html.py               # ingest SEC filings

# Docker (local dev — includes Redis)
docker compose up --build

# Railway (production)
# Backend: build from backend/Dockerfile + railway.toml
# Frontend: build from frontend/Dockerfile.railway
# Add PostgreSQL + Redis plugins in Railway dashboard
```

## Production hardening checklist

- Auth on all API endpoints (no public data)
- DB passwords hidden from logs (`hide_password=True`)
- Connection pool: `pool_size=20, max_overflow=10, pool_timeout=30`
- N+1 queries eliminated (`selectinload` for thread + messages + citations)
- Non-root `quorum` user in Dockerfile
- Request body size limit (10 MB)
- LLM call timeout (120s)
- Redis-backed rate limiting (auth: 10/min, chat: 30/min per user)
- In-memory fallback when Redis unavailable
- HTTPS via self-signed certs (replace with Let's Encrypt for real prod)
- HTTP→HTTPS redirect + HSTS + strong TLS ciphers
- Security headers (CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy, Referrer-Policy)
- Gzip compression on nginx
- Correlation IDs on all requests
- JSON structured logging (`QUORUM_ENV=production`)
- Startup DB health check
- CORS scoped to `ALLOWED_ORIGINS`
- No hardcoded credentials in scripts/tests
