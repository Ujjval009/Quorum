# Agent Instructions

## Stack

- **Backend:** Python 3.12 + FastAPI
- **Frontend:** React + TypeScript + Vite
- **Database:** PostgreSQL + pgvector (Supabase)
- **Auth:** Supabase Auth
- **LLM:** Groq (Llama 3 70B)
- **Embeddings:** Ollama / HuggingFace / Google

## Repo layout

```
quorum/
├── AGENTS.md
├── README.md
├── data/
├── docs/
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI entrypoint
│   │   ├── config.py     # Pydantic settings
│   │   ├── api/          # HTTP routers
│   │   ├── core/         # Dependencies, logging
│   │   ├── domain/       # Business logic
│   │   ├── models/       # SQLAlchemy models
│   │   └── schemas/      # Pydantic schemas
│   ├── alembic/          # Migrations
│   ├── tests/
│   └── pyproject.toml
└── frontend/
```

## Rules

- Type hints everywhere.
- Small focused functions.
- No `os.getenv` in app code — use `app.config.settings`.
- Validate at boundaries only (HTTP input, external APIs, DB writes).
- Async by default in request-path code.
