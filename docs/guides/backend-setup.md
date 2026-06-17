# Backend setup

This project uses a separate Python + FastAPI backend because the server is responsible for AI and document-processing work, not just basic web CRUD. Python gives us the strongest ecosystem for ingestion, chunking, embeddings, retrieval, evaluation, and LLM workflows.

## Init

```bash
cd backend
uv sync
```

## Run

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload   # → http://localhost:8000
```

## Database migrations

Alembic owns database schema changes. SQLAlchemy models describe the app tables, and Alembic migrations apply those changes to Supabase Postgres.

Create a migration after changing models:

```bash
uv run alembic revision --autogenerate -m "description"
```

Always review the generated migration. Add explicit operations for Postgres/Supabase features:

- `create extension if not exists vector`
- `vector(768)` columns
- generated `tsvector` columns
- HNSW and GIN indexes

Apply:

```bash
uv run alembic upgrade head
```

## Embedding providers

Two providers are supported:

| Provider | When | Env vars |
|----------|------|----------|
| **HuggingFace** | Production (Render) | `EMBEDDING_PROVIDER=huggingface`, `HF_TOKEN=...` |
| **Ollama** | Local dev fallback | `EMBEDDING_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://localhost:11434/v1` |

Ingestion batch-embeds all chunks for each filing into a single API call.

## Ingesting filings

```bash
cd backend
uv run python scripts/ingest_html.py
```

## Testing

```bash
uv run pytest -v -m "not eval"        # 138 unit tests
uv run pytest tests/eval_suite.py -v -m eval  # full eval (requires LLM key)
uv run ruff check .                   # lint
```
