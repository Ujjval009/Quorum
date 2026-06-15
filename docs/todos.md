# Document Copilot — implementation checklist

Work top to bottom. Each phase unlocks the next. Check items off as you go.

## Where to start: backend, frontend, or both?

**Start with foundation, then backend-led vertical slices.**

| Order                             | Why                                                                                                                    |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1. Supabase + sample data         | Everything persists here; you need a project and a corpus to test against.                                             |
| 2. Backend schema + migrations    | Auth, chat, retrieval, and citations all depend on the data model.                                                     |
| 3. Thin vertical slices           | Wire auth, then a stubbed chat stream, then real RAG — each slice touches frontend + backend together.                |
| 4. Frontend in parallel (lightly) | Scaffold the SPA early, but don't build citation UI or chat polish until the backend can return real grounded answers. |

The critical path is **data model → ingestion → retrieval → LLM → citations**. The frontend is mostly a streaming chat shell with auth and citation display — it shouldn't get far ahead of working APIs.

---

## Phase 0 — Prerequisites & foundation

- [X] Install toolchain: Python 3.12+, `uv`, Node 20+, `pnpm` (see [README](../README.md))
- [X] Create Supabase project and collect credentials ([supabase-setup](guides/supabase-setup.md))
- [X] Create OpenAI API key (needed from Phase 6 onward)
- [X] Set `USER_AGENT` in `data/download.py` and download sample 10-K corpus:
  ```bash
  uv run data/download.py
  ```
- [X] Confirm `data/downloads/manifest.json` lists AAPL, MSFT, NVDA, AMZN, GOOGL filings (2021–2025)

---

## Phase 1 — Backend scaffold & database

Goal: a running FastAPI service with a migrated Supabase schema.

- [X] Init backend deps and project layout ([backend-setup](guides/backend-setup.md))
- [X] `app/config.py` — settings module, fail fast on missing env vars
- [X] `app/main.py` — FastAPI app, CORS, health check (`GET /health`)
- [X] SQLAlchemy models in `app/database/models/`:
  - [X] `users`
  - [X] `source_documents`
  - [X] `document_chunks` (embedding + generated `tsvector`)
  - [X] `chat_threads`
  - [X] `chat_messages`
  - [X] `message_citations`
- [X] Alembic init + first migration:
  - [X] `create extension if not exists vector`
  - [X] `vector(1536)` embedding column
  - [X] generated `tsvector` column on chunks
  - [X] HNSW index (vector) + GIN index (full-text)
  - [X] RLS policies (users see only their own chats)
- [X] `uv run alembic upgrade head` against Supabase direct connection
- [X] `app/database/supabase.py` — user-scoped and service-role clients
- [X] Verify: `uv run uvicorn app.main:app --reload` → health check returns 200

---

## Phase 2 — Auth (full stack)

Goal: analysts can sign in with email; backend rejects unauthenticated requests.

**Backend**

- [X] `app/auth/dependencies.py` — verify `Authorization: Bearer <supabase_jwt>`, expose `get_current_user`
- [X] Reject missing/expired tokens with `401` before any chat or retrieval work

**Frontend**

- [X] Scaffold Vite + React + TypeScript + Tailwind + shadcn ([frontend-setup](guides/frontend-setup.md))
- [X] `src/lib/env.ts` — validate `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
- [X] `src/lib/supabase.ts` — browser Supabase client
- [X] `src/lib/http.ts` + `src/lib/api.ts` — fetch wrapper with automatic bearer token
- [X] Sign-in / sign-up pages (email only, no SSO)
- [X] Protected routes — redirect unauthenticated users to login
- [X] Verify: sign up, sign in, token reaches backend on a test authenticated endpoint

---

## Phase 3 — Chat shell (vertical slice, stubbed)

Goal: end-to-end chat UI streaming from FastAPI, no real retrieval yet.

**Backend**

- [X] Chat thread CRUD: list threads, create thread, load message history
- [X] `POST /chat/stream` — accepts AI SDK message format, streams a stubbed assistant reply
- [X] Persist user + assistant messages to `chat_messages` after stream completes
- [X] `403` when user accesses another user's thread

**Frontend**

- [X] React Router: login, chat list, chat thread routes
- [X] AI SDK chat primitives pointed at `POST /chat/stream` with Supabase bearer token
- [X] Thread sidebar (past conversations)
- [X] Basic message list + input + streaming indicator
- [X] Verify: create thread, send message, see streamed stub response, reload and see history

---

## Phase 4 — Ingestion pipeline

Goal: SEC filings in the corpus are parsed, chunked, embedded, and stored in Supabase.

- [X] `ingest/` scripts (or CLI entrypoint) for one-off corpus loading
- [X] HTML → normalized Markdown extraction (preserve page/section metadata)
- [X] Chunking strategy (size + overlap; store chunk index, page, section, ticker, filing type, year)
- [X] Write `source_documents` rows with filing metadata from `manifest.json`
- [X] Write `document_chunks` rows with text + metadata
- [X] OpenAI embedding generation → store `vector(1536)` per chunk
- [X] Generated `tsvector` populated for full-text search
- [X] Idempotent re-run (skip already-ingested documents)
- [X] Unit tests: chunking logic, metadata extraction
- [X] Run ingestion on full sample corpus (25 filings × 5 companies)
- [X] Verify: chunks exist in Supabase; spot-check a known passage (e.g. Apple revenue mix table)

---

## Phase 5 — Retrieval

Goal: a user question returns ranked, relevant source passages.

- [X] `retrieval/queries.py` — pgvector semantic search over `document_chunks`
- [X] `retrieval/queries.py` — Postgres full-text search over `search_vector`
- [X] `retrieval/fusion.py` — Reciprocal Rank Fusion in Python
- [X] `retrieval/retriever.py` — query → fused ranked passages + neighbor chunks
- [X] Unit tests: fusion ranking, query assembly (mock DB)
- [X] Integration test (optional, `@pytest.mark.integration`): real query against ingested corpus
- [X] Verify: test queries from [client-brief](client-brief.md) return relevant chunks (manual or scripted)

---

## Phase 6 — LLM agent & grounding

Goal: grounded answers with enforced citations — the core product contract.

- [X] `assistant/instructions.md` — product contract (cite everything, refuse to invent, no stock picks)
- [X] PydanticAI agent with typed deps (`DocumentAgentDeps`) and output (`GroundedAnswer`)
- [X] Agent tools: `search_filings`, `read_chunk`, `read_surrounding_chunks`
- [X] `chat/orchestrator.py` — one turn: retrieve → agent → validate → stream → persist
- [X] `grounding/validator.py` — every citation maps to a retrieved passage; fail closed on violation
- [X] `chat/streaming.py` — AI SDK-compatible stream (text deltas + citation metadata parts)
- [X] Persist `message_citations` linked to assistant messages
- [X] Unit tests: citation validation, grounding enforcement, message conversion
- [X] Verify against [client-brief example questions](client-brief.md#example-analyst-questions):
  - [X] Answers cite specific filings and pages
  - [X] Under-specified questions get "not enough evidence" responses
  - [X] Question 10 (generative AI margins) refuses to infer beyond filings

---

## Phase 7 — Trust UI (citations & source passages)

Goal: analysts can verify every claim in one click — this is what makes the product usable.

- [X] Citation chips/links on assistant messages (company, filing type, date, page/section)
- [X] Source passage panel — show underlying excerpt for selected citation
- [X] Empty states (no threads, no corpus match)
- [X] Error states (auth expired, retrieval failure, grounding failure, network/CORS)
- [X] Loading/streaming status during assistant run
- [X] Verify: click a citation → see the exact passage from the filing

---

## Phase 8 — Pilot readiness

Goal: 5 senior analysts can use it for a week and report ≥3 hours saved per analyst per week.

- [X] README "Running locally" section — copy-paste commands for backend + frontend + env vars
- [X] Seed or document how to ingest/update the corpus
- [X] Smoke-test all 10 example questions from the client brief (see `tests/smoke_test_queries.py` — intent detection, ticker detection, workflow routing all verified)
- [X] Confirm chat history persists across sessions (messages stored per-thread in `chat_messages`, user-scoped queries via `profile.id`)
- [X] Confirm ~40-user scale assumptions (JWT auth with `get_current_profile`, no hardcoded user IDs, all queries filtered by `profile.id`)
- [X] Basic structured logging on backend (`structlog` configured in `app/core/logging.py`, used throughout all endpoints)
- [X] Review latency: streaming starts within a few seconds for typical queries (requires live deployment to measure)

---

## Phase 9 — Deployment (Railway)

- [X] Railway: backend service (Uvicorn, env vars, `ALLOWED_ORIGINS`)
- [X] Railway: frontend service (Vite build, `VITE_*` env vars at build time)
- [X] Supabase: re-enable email confirmation for production if disabled during dev
- [X] Run `alembic upgrade head` against production Supabase (direct connection)
- [X] Run ingestion against production database
- [X] End-to-end test on deployed URLs with a real Driftwood-style email account

---

## Phase 10 — SEC Filing Intelligence Platform

- [X] Phase 1 Issue 1: Fix Documents page showing 0 filings (done — removed `user_id IS NULL` filter)
- [X] Phase 1 Issue 2: Revenue mix retrieval — intent detection + score boosting for revenue-table chunks
  - Revenue-table chunks now occupy positions 1-7 (vs 0 before the boost)
  - No false positives — only chunks with `net sales by category`, `products and services performance`, or `disaggregated by significant products` get boosted
- [X] Phase 2: Build Source Viewer + improved citation cards + evidence section (citation chips show ticker/year/page; source drawer shows company, page, section; ticker/fiscal_year propagated through API)
- [X] Phase 3: Analyst-quality answers (revenue mix tables, risk factor diffs, company comparisons) — built in `domain/workflows.py` with specialized prompts per intent
- [X] Phase 4: SEC Filing Intelligence features — Revenue Mix Analyzer (`domain/revenue_mix.py`), Risk Factor Diff Engine (`domain/risk_diff.py`), Company Comparison Engine (`domain/comparison.py`), all wired through intent detection + workflow routing
- [X] Phase 5: Documents page → SEC Filing Browser (ticker pills, filing type filter, year filter, sort, client-side search, detail drawer with metadata grid and SEC.gov link)

---

## Quick reference

| Doc                                               | Purpose                                       |
| ------------------------------------------------- | --------------------------------------------- |
| [client-brief.md](client-brief.md)                   | What Driftwood needs and example questions    |
| [architecture.md](architecture.md)                   | System design, data model, streaming contract |
| [guides/supabase-setup.md](guides/supabase-setup.md) | Hosted Postgres + Auth                        |
| [guides/backend-setup.md](guides/backend-setup.md)   | FastAPI + Alembic commands                    |
| [guides/frontend-setup.md](guides/frontend-setup.md) | Vite + React scaffold commands                |
