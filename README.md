# Quorum

AI-powered Document Copilot — query SEC filings in natural language and get source-grounded answers with page-level citations.

## Stack

| Layer       | Technology                          |
| ----------- | ----------------------------------- |
| Backend     | Python 3.12 + FastAPI               |
| Frontend    | React + TypeScript + Vite           |
| Database    | PostgreSQL + pgvector (Supabase)    |
| Auth        | Supabase Auth                       |
| ORM         | SQLAlchemy + Alembic                |
| LLM         | Groq (Llama 3 70B)                  |
| Embeddings  | Ollama (local) / HuggingFace / Google |

## Getting started

```bash
cd backend
uv sync
cp .env.example .env   # fill in your credentials
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```
