# Quorum

AI-powered SEC Filing Analyst — query 10-K filings in natural language and get source-grounded answers with structured financial tables, growth analysis, and citations.

## How it works

1. **Ingest** — SEC 10-K HTML filings are parsed into Item-based sections, chunked, embedded (Ollama `nomic-embed-text`), and stored in PostgreSQL + pgvector.
2. **Retrieve** — Hybrid search (vector similarity + full-text with RRF fusion) retrieves relevant chunks, filtered by detected tickers and intent.
3. **Extract** — Financial metrics (revenue by segment, growth rates, CAGR, margins, revenue shares) are extracted deterministically from chunk text with Python regex, not by the LLM.
4. **Generate** — Structured tables are rendered first, then the LLM (Groq Llama 3 70B) generates narrative sections: Executive Summary, Key Findings, Detailed Analysis, Analyst Takeaway.
5. **Verify** — Evidence is validated pre-generation (coverage gaps trigger re-expansion), citations are deduplicated and ticker-scoped.

## Features

- **Structured financial data** — Revenue by category, revenue mix, key financial metrics, growth rates, CAGR — all computed in Python, not hallucinated by the LLM
- **Multi-company comparison** — Side-by-side tables across tickers (e.g., AAPL vs MSFT)
- **Cloud segment analysis** — AWS, Azure, Google Cloud segment queries routed to specific financial data
- **Risk factor diff** — Cross-year comparison of risk factors (added, removed, expanded, reduced)
- **Cross-company contamination prevention** — Three-layer defense: SQL filter → post-fusion filter → API filter
- **Citation integrity** — Every statement grounded in specific chunks with ticker, fiscal year, section title, and excerpt
- **Graceful degradation** — LLM rate limits return pre-computed tables with a friendly message instead of crashing
- **Streaming responses** — Real-time token streaming with thread persistence on disconnect

## Stack

| Layer       | Technology                          |
| ----------- | ----------------------------------- |
| Backend     | Python 3.14 + FastAPI               |
| Frontend    | React 19 + TypeScript 6 + Vite 8    |
| Database    | PostgreSQL + pgvector (Supabase)    |
| Auth        | Supabase Auth                       |
| ORM         | SQLAlchemy + Alembic                |
| LLM         | Groq (Llama 3.3 70B)                |
| Embeddings  | Ollama `nomic-embed-text` (local)   |

## Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (optional)
- Supabase project (PostgreSQL + pgvector)
- Groq API key
- Ollama running locally with `nomic-embed-text` model

### Backend

```bash
cd backend
uv sync
cp .env.example .env   # fill in your credentials
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker

```bash
docker compose up --build
```

## Ingesting filings

```bash
cd backend
uv run python scripts/ingest_html.py
```

This reads HTML filings from `data/downloads/manifest.json`, parses SEC 10-K items, chunks text, generates embeddings, and writes to the database.

## Tests

```bash
cd backend
# Fast unit tests (no network)
uv run pytest -v -m "not eval"

# Full eval suite (requires running backend + Groq API key)
uv run pytest tests/eval_suite.py -v -m eval
```

## Project structure

```
quorum/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py            # Pydantic settings (single env source)
│   │   ├── api/                 # HTTP routers (chat, auth, documents)
│   │   ├── domain/
│   │   │   ├── extraction.py    # Financial fact extraction from chunks
│   │   │   ├── rag.py           # Answer generation + citation building
│   │   │   ├── retrieval.py     # Hybrid search + RRF fusion + intent
│   │   │   ├── coverage.py      # Evidence coverage validation
│   │   │   └── workflows.py     # Intent-aware prompt selection
│   │   ├── models/              # SQLAlchemy models
│   │   └── schemas/             # Pydantic schemas
│   ├── scripts/
│   │   └── ingest_html.py       # SEC filing ingestion pipeline
│   ├── tests/
│   │   ├── test_extraction.py
│   │   ├── test_rag.py
│   │   ├── test_retrieval.py
│   │   ├── eval_suite.py        # 52 regression eval queries
│   │   └── ...
│   ├── alembic/                 # Database migrations
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/          # React components
│   │   ├── api/                 # API client
│   │   └── lib/                 # Supabase client
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
└── docker-compose.yml
```
