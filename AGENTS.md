# Agent Instructions

## Stack

- **Backend:** Python 3.14 + FastAPI
- **Frontend:** React 19 + TypeScript 6 + Vite 8
- **Database:** PostgreSQL + pgvector (Supabase)
- **Auth:** Supabase Auth
- **LLM:** Groq (Llama 3.3 70B)
- **Embeddings:** Ollama `nomic-embed-text` (local)

## Repo layout

```
quorum/
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── data/
│   └── downloads/          # Raw SEC HTML filings + manifest.json
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── .env.example
│   ├── alembic/
│   ├── scripts/
│   │   └── ingest_html.py  # SEC filing ingestion pipeline
│   ├── tests/
│   │   ├── test_extraction.py
│   │   ├── test_rag.py
│   │   ├── test_retrieval.py
│   │   ├── test_risk_diff.py
│   │   ├── test_auth.py
│   │   ├── smoke_test_queries.py
│   │   └── eval_suite.py   # 52 regression eval queries (mark: eval)
│   └── app/
│       ├── main.py         # FastAPI entrypoint
│       ├── config.py       # Pydantic settings
│       ├── api/
│       │   ├── chat.py     # Threads + ask + streaming
│       │   ├── auth.py     # Login/signup + rate limiter
│       │   └── documents.py
│       ├── core/
│       │   ├── deps.py     # FastAPI DI
│       │   └── logging.py
│       ├── domain/
│       │   ├── extraction.py   # Financial fact extraction (Python, not LLM)
│       │   ├── rag.py          # Answer generation + citation building
│       │   ├── retrieval.py    # Hybrid search + RRF fusion + intent
│       │   ├── coverage.py     # Evidence coverage validation
│       │   ├── workflows.py    # Intent-aware prompt selection
│       │   ├── comparison.py   # Multi-ticker comparison
│       │   ├── revenue_mix.py
│       │   └── risk_diff.py
│       ├── models/
│       │   ├── document.py  # SourceDocument, DocumentChunk
│       │   ├── chat.py      # ChatThread, ChatMessage
│       │   └── profile.py
│       └── schemas/
└── frontend/
    ├── package.json
    ├── Dockerfile
    ├── nginx.conf
    └── src/
        ├── App.tsx
        ├── components/
        │   ├── Chat.tsx      # Main chat interface + streaming
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
- **Segment queries** (AWS, Azure, Google Cloud) must never fall back to total-company metrics
- **Evidence expansion** — if coverage validation finds gaps, `expand_coverage()` broadens the search
- **Rate limit resilience** — LLM failures return pre-computed tables with a friendly message; streaming saves messages in `finally` block to survive client disconnects

## Common commands

```bash
# Backend
uv run uvicorn app.main:app --reload              # dev server
uv run pytest -v -m "not eval"                     # fast unit tests
uv run pytest tests/eval_suite.py -v -m eval       # full eval suite
uv run ruff check .                                # lint
uv run alembic upgrade head                        # migrations

# Frontend
npm run dev                                        # dev server
npm run build                                      # production build

# Ingestion
uv run python scripts/ingest_html.py               # ingest SEC filings

# Docker
docker compose up --build
```
