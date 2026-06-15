# Backend — agent notes

This is the FastAPI service for Document Quorum. Read [../AGENTS.md](../AGENTS.md) first — universal building rules live there. This file adds backend-specific conventions.

## Stack

- Python 3.12+
- FastAPI + uvicorn
- Pydantic v2 + pydantic-settings
- `httpx` for outbound HTTP
- `pytest` for tests
- Supabase Python client (DB + auth)
- SQLAlchemy models + Alembic migrations for database schema changes
- OpenAI SDK for LLM & embeddings
- `redis[hiredis]` for rate limiting
- Supabase `pgvector` for semantic search and Postgres full-text search for keyword retrieval. Hybrid search runs vector and full-text queries separately, then fuses ranked results in Python with Reciprocal Rank Fusion.
- `structlog` for logging
- `uv` for dependency + project management

## Dependency policy

See universal policy in [../AGENTS.md](../AGENTS.md). Backend-specific:

- **Prefer stdlib:** `pathlib`, `datetime`, `uuid`, `enum`, `dataclasses`, `asyncio`, `collections`, `itertools`, `json`, `urllib`.
- **Not OK without justification:** `python-dateutil`, `toolz`, `funcy`, `more-itertools`, small JSON/string micro-libs, "ergonomic" wrappers on top of declared SDKs.
- Dev deps (test/lint/build) have a looser bar but still pick widely-used, low-footprint tools (`pytest`, `ruff`).

## Layout

```
backend/
├── pyproject.toml
├── Dockerfile
├── railway.toml              # Railway healthcheck config
├── alembic.ini
├── alembic/
│   ├── env.py                # Imports app database metadata for autogenerate
│   └── versions/             # Reviewed migration files
├── scripts/
│   └── ingest_html.py        # SEC filing ingestion pipeline
├── tests/
│   ├── test_extraction.py
│   ├── test_rag.py
│   ├── test_retrieval.py
│   ├── test_risk_diff.py
│   ├── test_auth.py
│   ├── test_retrieval_eval.py # 19 retrieval quality tests
│   ├── smoke_test_queries.py
│   └── eval_suite.py          # 52 regression eval queries (mark: eval)
└── app/
    ├── main.py                # FastAPI entrypoint + startup validation + correlation ID
    ├── config.py              # Pydantic settings — single source of truth for env
    ├── api/
    │   ├── chat.py            # Threads + ask + streaming + rate limiter
    │   ├── auth.py            # Login/signup + rate limiter
    │   └── documents.py       # SEC filing browser
    ├── core/
    │   ├── deps.py            # FastAPI DI (get_current_profile, get_db)
    │   ├── logging.py         # JSONRenderer (production) / ConsoleRenderer (dev)
    │   └── rate_limiter.py    # Redis-backed sliding-window rate limiter
    ├── domain/
    │   ├── extraction.py      # Financial fact extraction (Python, not LLM)
    │   ├── rag.py             # Answer generation + citation building
    │   ├── retrieval.py       # Hybrid search + RRF fusion + metadata filtering
    │   ├── coverage.py        # Evidence coverage validation
    │   ├── workflows.py       # Intent-aware prompt selection
    │   ├── comparison.py      # Multi-ticker comparison
    │   ├── revenue_mix.py
    │   └── risk_diff.py
    ├── models/
    │   ├── base.py            # Engine, SessionLocal, TimestampMixin, UUIDMixin
    │   ├── document.py        # SourceDocument, DocumentChunk
    │   ├── chat.py            # ChatThread, ChatMessage, MessageCitation
    │   └── profile.py
    └── schemas/               # Pydantic request/response models
```

## Code style (backend-specific)

- **Type hints on public functions and module-level things.** Don't annotate every local.
- **Async by default in request-path code.** Don't run blocking I/O on the event loop. Tempfile + small synchronous file reads are OK (they're fast); network calls must be async.
- **Use `async def` for all route handlers** and any I/O service function.
- **Validate at boundaries only.** HTTP input is validated by Pydantic models. External API responses are validated when parsed. Internal callers are trusted.

## Configuration

- `app.config.settings` is the single source of truth. Import settings where needed; never call `os.getenv` in app code, never call `load_dotenv`.
- If a third-party SDK reads `os.environ` directly, add the mirror in `config.py` — don't sprinkle `setdefault` elsewhere.
- Fail fast on startup when required env vars are missing.

## Database migrations

- Alembic is the source of truth for schema changes. Do not change production tables manually in the Supabase dashboard.
- SQLAlchemy models describe normal tables and columns. Alembic autogenerate creates candidate migrations, but every generated migration must be reviewed before applying.
- Supabase/Postgres-specific features belong in explicit migration operations: `create extension vector`, generated `tsvector` columns, HNSW/GIN indexes, RLS enablement, and RLS policies.
- Alembic must use the direct/session database connection, not the Supabase transaction pooler URL.
- Run migrations from `backend/` with `uv run alembic upgrade head`.

## Tests

- **Prefer unit over integration.** Mock at the service boundary.
- Fast suite (`pytest -m "not eval"`) must stay green — 138 tests, no network, no DB required.
- Eval tests go behind `@pytest.mark.eval` and require a running backend + live DB + LLM API key.
- Retrieval eval tests (`test_retrieval_eval.py`) validate 19 quality metrics: Recall@5, MRR, Prec@5, cross-company contamination, chunk metadata integrity.
- Tests live next to what they test (`retrieval.py` → `test_retrieval.py`).

## Anti-patterns (rejected)

- `os.getenv` / `load_dotenv` in modules.
- Wrapping FastAPI responses in custom envelope classes.
- Over-catching `Exception` just to log and re-raise; let it propagate.
- Shared state through globals instead of FastAPI `app.state` or DI.
- Silent fallbacks that hide real config errors.
- `render_as_string(hide_password=True)` for SQLAlchemy `create_engine` — pass the URL object directly instead.
- Mocking the LLM in unit tests without also testing the grounding contract — the prompt is the product.
