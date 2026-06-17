# Quorum — Interview Prep

---

### What is Quorum, and what specific problem does it solve for financial analysts?

Quorum is an AI-powered SEC filing analyst. It lets analysts ask questions about 10-K filings in plain English and get answers backed by citations.

**The problem:** Analysts spend half their week reading filings, copying passages, and comparing numbers year-over-year. That's boring, repetitive, and scales linearly with headcount. Quorum automates the intake work so analysts can focus on actual analysis.

---

### Why did you choose to build an AI-powered SEC analyst rather than a general-purpose RAG chatbot?

Finance has zero tolerance for wrong numbers. If a chatbot says "revenue was $100B" and it's actually $90B, the analyst loses trust immediately.

A general RAG chatbot can be "good enough" for summarization. For financial data, "good enough" gets you fired. Quorum was built specifically so that every number is computed deterministically (Python regex, not LLM), and every claim has a citation back to a specific filing page. This level of reliability only comes from domain-specific design.

---

### Can you walk me through the five-stage pipeline (Ingest, Retrieve, Extract, Generate, Verify)?

1. **Ingest:** Parse raw SEC 10-K HTML → split into sections (Item 1, Item 1A, Item 7, etc.) → chunk into ~4000-char pieces → embed via HuggingFace → store in pgvector.
2. **Retrieve:** Hybrid search (vector similarity + full-text search) → fuse results with RRF → filter by ticker/year extracted from the question.
3. **Extract:** Deterministic Python functions extract revenue, CAGR, margins, and revenue shares from the retrieved chunks. No LLM touches the numbers.
4. **Generate:** Build structured tables first (always returned), then LLM writes narrative around them.
5. **Verify:** Check that every claim has a citation. If coverage is insufficient, expand the search. If still insufficient, warn the user.

---

### What is "deterministic metric extraction," and why is it critical for financial data?

Deterministic extraction means financial numbers are computed by Python code, not by the LLM. The code uses regex patterns to find revenue tables, margin figures, and EPS values directly in the chunk text, then computes CAGR and revenue shares with standard math formulas.

**Why it matters:** LLMs hallucinate numbers. A hallucinated revenue figure could cause an analyst to make a bad stock call. By keeping the math in Python, every number is reproducible and verifiable.

---

### How does the system prevent LLM hallucinations when reporting revenue or CAGR figures?

Three safeguards:

1. The LLM never computes numbers. Python regex extracts revenue, margins, and EPS from the filing text itself.
2. All growth rates (CAGR, YoY) are computed with Python math functions, not generated text.
3. Every number the LLM mentions must be grounded in a citation that links back to a specific filing, section, and page. The coverage validator checks that the retrieved chunks actually contain the data needed.

---

### The documentation mentions a "3-layer defense" for contamination prevention; can you explain how that works?

Cross-company contamination means data from one company leaking into another company's answer (e.g., using NVDA's revenue to answer an Apple question).

1. **SQL filter:** When building the search query, we extract tickers from the question (e.g., "AAPL") and add `WHERE ticker = 'AAPL'` to both the vector search and full-text search. Only chunks for that ticker are returned.
2. **Post-fusion filter:** After RRF fusion, we filter out any chunk whose ticker doesn't match the expected tickers from step 1.
3. **API filter:** In the API response, citations are filtered by ticker before sending to the frontend.

---

### What were your primary reasons for choosing Python 3.12 and FastAPI for the backend?

**Python 3.12** because the AI/ML ecosystem (HuggingFace, OpenAI SDK, PyTorch) is strongest in Python. 3.12 specifically for perf improvements and cleaner error messages.

**FastAPI** because:
- Native async support for streaming SSE responses
- Automatic OpenAPI docs (Swagger UI)
- Pydantic validation built in — no separate serializer needed
- Huge perf advantage over Flask for high-throughput API workloads

---

### Why did you select React 19 and TypeScript for the frontend instead of older, more "stable" versions?

React 19 gives us the latest concurrent features and the new compiler (React Forget) for automatic memoization. TypeScript catches bugs at compile time that would otherwise slip into production — especially important for the complex streaming state machine in the chat UI.

Newer versions also have better developer tooling (Vite 8), faster builds, and smaller bundles. "Stable" in practice means "bugfixed," and by the time we built it, 19 was stable.

---

### Explain the role of pgvector and Supabase in your database architecture.

**pgvector** is a PostgreSQL extension that adds vector data type and similarity search operators. We store chunk embeddings as `vector(768)` columns and query them with cosine similarity.

**Supabase** hosts the PostgreSQL database, manages Auth (JWT sessions), and provides the connection pooler. Using Supabase means we get a managed Postgres with pgvector built in — no separate vector database to maintain.

---

### Why did you use Groq (Llama 3.3 70B) as your primary LLM provider?

Groq offers extremely low latency (tokens arrive faster than reading speed) thanks to their custom LPU hardware. For a streaming chat experience, sub-second first-token latency is critical. Llama 3.3 70B provides GPT-4-class quality at a fraction of the cost. The combination gives us fast, cheap, high-quality answers.

---

### How does Hybrid Search (Vector + Full-Text) improve retrieval quality compared to vector-only search?

Vector search finds chunks that are semantically similar to the question. But it can miss exact matches — for example, if the user asks about "Item 1A" or "AAPL," vector search might find conceptually related chunks but skip the exact section.

Full-text search catches exact keyword matches: ticker names ("MSFT"), section headers ("Risk Factors"), fiscal years ("2024"), and financial terms ("CAGR"). Fusing both gives you semantic understanding + precision matching.

---

### What is Reciprocal Rank Fusion (RRF), and how does it help merge search results?

RRF combines two ranked lists without needing to tune weights. Each result gets a score of `1 / (k + rank)` from each search method. The scores are summed across both methods, and results are re-ranked by total score.

`k=60` is the standard value. The beauty is it doesn't care about score magnitudes — vector cosine similarity might range from 0.5-0.9 while FTS scores are completely different scales. RRF just uses rank position, so the scales don't matter.

---

### How do you implement metadata pre-filtering, and why is it more efficient than post-filtering?

We extract ticker names and fiscal years from the user's query using regex patterns (e.g., `TICKER_ALIASES` map converts "Apple" → "AAPL"). These extracted values are injected as SQL `WHERE` clauses in both the vector and full-text queries.

**Why more efficient:** If you retrieve 100 chunks first and then filter, you've wasted compute on 80 irrelevant chunks. With pre-filtering, the database only returns chunks matching the target ticker/year. For a corpus with 5+ companies, this cuts the search space by 80% before ranking even starts.

---

### Which specific HuggingFace embedding model did you use, and why was it chosen for financial queries?

`sentence-transformers/multi-qa-mpnet-base-dot-v1` — a 768-dimensional model fine-tuned for semantic search question-answering tasks. It was chosen because:
- It's designed for retrieval (multi-QA), not just generic sentence similarity
- 768d is the sweet spot between expressiveness and storage cost
- It's freely available on HuggingFace Inference API
- Consistently scores well on financial text benchmarks

---

### Explain the ingestion process: How do you transform raw SEC HTML into searchable chunks?

1. Read `manifest.json` — lists each filing (ticker, year, HTML file path)
2. Parse HTML with a custom `SECHTMLParser` that strips scripts, styles, and XBRL junk
3. Split text into SEC sections (Item 1, Item 1A, Item 7, etc.) using regex patterns
4. Further split each section into ~4000-char chunks with 200-char overlap at sentence boundaries
5. Batch-embed all chunks for one filing in a single HuggingFace API call
6. Store as `SourceDocument` (filing metadata) + `DocumentChunk` (text, embedding, ticker, year, section) in PostgreSQL

---

### How does the system handle batch embeddings during ingestion to optimize performance?

Instead of calling the embedding API once per chunk (~100-200 calls per filing), we collect all chunk texts for a filing into a list and make a single `feature_extraction` call with the full list. HuggingFace's API processes the batch server-side, returning all embeddings in one response. This reduces API calls by ~100x and cuts total ingestion time from ~30 minutes to ~12 minutes for 25 filings.

---

### What is the difference between your Python-based extraction and standard LLM extraction?

**Standard LLM extraction:** Send chunk text to the LLM and ask "what's the revenue?" The LLM guesses based on pattern recognition. It might get the number right, but the reasoning isn't verifiable and the output can change between runs.

**Python-based extraction:** Regex patterns scan the chunk text for known financial table formats (e.g., "Net sales by category" → table rows → category + dollar amount). Growth rates are computed with `(new - old) / old`. Every step is deterministic, reproducible, and testable with unit tests.

---

### How does Quorum handle multi-company comparisons (e.g., comparing AAPL vs. MSFT)?

The intent detector recognizes "compare" + multiple company names → routes to `company_comparison` workflow. It runs separate hybrid searches for each ticker (with ticker-specific query rewriting to surface the right financial tables), then builds a side-by-side comparison table in Python. The LLM gets the pre-computed comparison table and writes narrative around it.

---

### Can you explain the "Risk factor diffing" feature and how it identifies added or removed language?

For each company, we store risk factor sections (Item 1A) for multiple years. The system segments the risk text into individual risk statements, then matches them across years using heading similarity. If a risk heading appears in year N but not year N-1, it's "added." If it disappears, it's "removed." If the wording changes significantly while keeping the same heading, it's "modified." The results are displayed as a diff table showing what changed year-over-year.

---

### How is Cloud Segment Analysis routed to specific data points like AWS or Azure?

The intent detector matches keywords like "AWS," "Azure," "Google Cloud" → routes to `segment` intent. The segment workflow fetches segment-level financial data from the chunk metadata. Crucially, there's a guard that prevents fallback to total-company metrics — if the query is about AWS revenue, the system must return AWS-specific chunks or say it doesn't have enough evidence.

---

### What happens to the system if the LLM API goes down (graceful degradation)?

The pre-computed structured tables are always rendered first and returned regardless. If the LLM call fails (rate limit, timeout, API error), the user still sees the complete financial tables with all extracted metrics. A friendly message explains that the AI narrative is temporarily unavailable. This means the most valuable output (the numbers) is always delivered.

---

### How do you ensure citation integrity so that every claim is grounded in a specific filing?

Every citation carries: `ticker`, `fiscal_year`, `section_title`, `excerpt`, and `chunk_id`. When building citations, we deduplicate by `chunk_id` (no repeating the same chunk). The coverage validator checks that the retrieved chunks actually contain the data types referenced in the answer. Before sending to the frontend, citations are filtered to remove any cross-company contamination.

---

### Why did you decide to use Redis for rate limiting instead of in-memory dictionaries?

In-memory dicts reset on server restart and don't share across multiple workers. If you have 4 uvicorn workers, each has its own in-memory counter — a user could send 40 requests/minute by hitting all 4 workers. Redis provides a shared counter that persists across restarts and works across any number of workers. We also include an in-memory fallback so the app doesn't crash if Redis is unavailable.

---

### Explain the sliding-window rate limiter implementation.

Instead of simple counters that reset on the clock minute, we use Redis sorted sets. Each request adds a timestamp entry to a sorted set keyed by user+endpoint. Before processing, we remove entries older than the window (e.g., 60 seconds). If the remaining count exceeds the limit (auth: 10/min, chat: 30/min), we reject with 429. This gives a true sliding window — no burst at the minute boundary.

---

### How do you handle N+1 query problems when fetching threads, messages, and citations?

Using SQLAlchemy's `selectinload` — a single query loads the thread, eagerly loads all its messages in a second query, and eagerly loads all citations for those messages in a third query. Without `selectinload`, fetching 10 threads with 20 messages each would be 1 + 10 + 200 = 211 queries. With `selectinload`, it's 3 queries total.

---

### What is the purpose of Alembic in your database workflow?

Alembic manages database schema changes via migrations. When we modify SQLAlchemy models (e.g., add a column to `chat_messages`), we run `alembic revision --autogenerate` to generate a migration file. This file is reviewed, committed, and applied to both local and production databases with `alembic upgrade head`. This ensures schema changes are version-controlled, reversible, and tested before hitting production.

---

### How does the system handle streaming responses while maintaining thread persistence?

The streaming endpoint (`/ask/stream`) uses Server-Sent Events. Tokens are yielded as `data: {"type": "token", "content": "..."}` events. The assistant message is saved to the database in a `finally` block — this means even if the client disconnects mid-stream, the partial answer is persisted. User messages are saved immediately when the request starts. On the frontend, messages are appended to state incrementally (never replaced), and thread loading fetches complete history from the server.

---

### Can you explain the project structure and why you separated logic into domain, core, and api?

- **api/** — HTTP routers. Thin layer: validate input, call domain, return response. Zero business logic.
- **domain/** — Business logic. Extraction, retrieval, RAG, workflows. Testable without HTTP.
- **core/** — Cross-cutting concerns. Rate limiting, logging, dependency injection. Used by both api and domain.

This separation means you can test extraction logic without spinning up a server, swap the HTTP layer from FastAPI to something else, or change logging without touching business code.

---

### What specific Pydantic features did you use for configuration management?

`pydantic-settings` with `BaseSettings` class. Environment variables are validated at import time — if `SUPABASE_URL` is missing, the app fails to start immediately (fail fast). Type coercion is automatic (string `"5432"` → int 5432). The `Field(alias=...)` feature maps between Python-friendly attribute names and UPPER_CASE env var names. Nested settings are supported via `model_config`.

---

### How do you validate evidence coverage, and what triggers a "re-expansion" of a search?

The coverage validator checks whether the retrieved chunks contain the data types mentioned in the query. For example, if the query asks about "revenue" and "margins," the validator checks that the chunks include both revenue figures and margin figures. If gaps are found (e.g., we have revenue but no margin data), `expand_coverage()` increases the search depth and re-queries the database. If gaps remain after expansion, the system proceeds with available data but warns the user.

---

### What are "Intent-aware prompt selections" in your workflows.py?

The intent detector categorizes each query (revenue_mix, financial_metrics, company_comparison, etc.). Each intent has a specialized prompt template in `workflows.py`. For example, a `revenue_mix` query gets a prompt that instructs the LLM to focus on category-level breakdown and mix shifts, while a `risk_factor_diff` query gets a prompt about year-over-year language changes. The LLM never gets a generic "answer this" — it gets a structured task with specific output expectations.

---

### Why did you choose HuggingFace Inference API over a local Ollama instance for production?

Ollama requires a GPU to run embeddings locally, which adds cost and complexity to the deployment (GPU instances are expensive on Render/Railway). HuggingFace Inference API runs the same `sentence-transformers` models serverless — pay per request, no GPU to manage. For 25 filings with ~3700 chunks, the total embedding cost is less than $1. Ollama stays as the local dev fallback for offline development.

---

### How do you maintain security for database credentials and other secrets in the backend?

All secrets live in environment variables, never in code. `.env` is in `.gitignore`. Supabase credentials (anon key, service role key, database password) are passed as env vars. SQLAlchemy hides passwords from logs with `hide_password=True`. The service role key is only used server-side — never exposed to the frontend.

---

### What production hardening steps did you take regarding logging and request tracing?

`structlog` with JSON formatting in production (`QUORUM_ENV=production`) — each log line is a structured JSON object with timestamp, level, event, and request_id. Correlation IDs are generated per-request via middleware and included in all logs and 500 error responses, making it possible to trace a single user request across multiple services.

---

### How does the Docker configuration ensure the application runs securely?

The Dockerfile creates a non-root `quorum` user with `adduser --system`. The app runs as this user, not root. If an attacker exploits a vulnerability in the Python process, they don't have root access to the container. The user's home is set to `/app` and file ownership is explicitly set.

---

### Can you describe your testing strategy (unit tests vs. retrieval eval)?

- **Unit tests (138 tests, `pytest -m "not eval"`):** Mock all external services. Test extraction, retrieval fusion, RAG logic, risk diffing, auth — no network, no DB, runs in 3 seconds. These are the fast feedback loop.
- **Retrieval quality (19 tests):** Run against a live DB. Test Recall@5, MRR, Prec@5, cross-company contamination, citation metadata integrity.
- **Eval suite (61 tests, `pytest -m eval`):** Full end-to-end tests against a running backend with a real LLM. Validate answer quality, citation counts, ticker isolation, and structured output markers.

---

### What is the purpose of the 61 full eval suite tests, and what metrics do they track?

They validate real-world query quality against the actual LLM + retrieval pipeline. Each test checks:
1. Answer is non-empty
2. Correct handling of insufficient evidence (graceful degradation)
3. Structured data markers are present for structured intents
4. Minimum citation count is met
5. Citations are deduplicated
6. Every citation's ticker is in the expected set
7. No cross-company contamination for single-ticker queries
8. Every citation has a non-empty excerpt

---

### How is the frontend deployed on Vercel, and how are SPA rewrites handled?

Vercel is configured in `vercel.json` with framework=Vite, build command=`npm run build`, output directory=`dist`. The critical piece is the `rewrites` rule: `{ "source": "/(.*)", "destination": "/index.html" }`. Without this, reloading `/workspace` would 404 because Vercel looks for a file at `/workspace/index.html` that doesn't exist. The rewrite tells Vercel to serve `index.html` for all routes, letting React Router handle the client-side routing.

---

### How do you handle CORS and allowed origins in your FastAPI application?

`app/main.py` configures `CORSMiddleware` with `allow_origins` set from `ALLOWED_ORIGINS` env var (default: `http://localhost:5173` for local dev). In production, this is set to the Vercel frontend URL. Only the specified origins can make browser requests to the API — prevents unauthorized websites from calling the backend.

---

### What PostgreSQL connection pool settings did you use to ensure stability?

`pool_size=20, max_overflow=10, pool_timeout=30`. This means 20 persistent connections are maintained, with up to 10 additional connections during spikes. If all 30 connections are busy, new requests wait up to 30 seconds before timing out. This prevents the database from being overwhelmed during traffic spikes while keeping enough connections for normal operations.

---

### How does the system handle large request bodies (e.g., the 10 MB cap)?

FastAPI's built-in body size limit is set to 10 MB. Requests with larger bodies are rejected with a 413 Payload Too Large response. This prevents malicious users from sending multi-gigabyte payloads that would exhaust server memory. The ingestion pipeline handles large documents by processing them in chunks locally, not through the API.

---

### Why did you include JSON structured logging for production environments?

JSON logs are machine-parseable. Tools like Datadog, Grafana, and ELK can ingest JSON logs directly and support structured querying (e.g., "find all errors for user_id=X in the last hour"). Plain text logs require regex parsing, which is fragile and slow at scale. Each log line includes `request_id`, `timestamp`, `level`, `event`, and relevant context fields.

---

### How does the backend validate database connectivity on boot?

On startup (`main.py`), the app runs `SELECT 1` against the database. If it succeeds, it logs `database=True`. If it fails, it logs `database=False` but still starts — this allows the health check to report a degraded state instead of crashing the container. The `/health` endpoint returns the database status so load balancers can route traffic away from a degraded instance.

---

### What role does SQLAlchemy's selectinload play in your data fetching?

`selectinload` eagerly loads related objects in a separate query (instead of lazy-loading them one at a time). When fetching a thread with its messages and citations, the default lazy-loading would generate hundreds of queries. `selectinload` collapses this to 3 queries: one for the thread, one for all its messages, and one for all their citations. This eliminates the N+1 problem.

---

### How do you handle authentication between the frontend and Supabase Auth?

The frontend uses `@supabase/supabase-js` to sign in with email/password. Supabase returns a JWT access token. Every API request includes this token in the `Authorization: Bearer <token>` header. FastAPI's `get_current_profile` dependency verifies the JWT with Supabase Auth on every request. If the token is missing, expired, or invalid, the request is rejected with 401.

---

### What are the prerequisites for a developer to spin up this project locally?

Python 3.12+ (with `uv`), Node.js 20+ (with npm), a Supabase project (free tier), a Groq API key (free tier), and a HuggingFace token (free tier). Clone the repo, copy `.env.example` to `.env` with credentials, run `uv sync` + `uv run alembic upgrade head` in backend, `npm install` in frontend, and both are ready.

---

### How would you scale the ingestion pipeline if you had to process thousands of filings?

The current script is single-threaded and sequential. To scale:

1. **Parallelize by filing:** Use Python's `concurrent.futures` or a task queue (Celery/Redis Queue) to process multiple filings simultaneously.
2. **Batch embeddings:** Already implemented — one API call per filing. For thousands, the HuggingFace API rate limit would be the bottleneck. Switch to a dedicated embedding model on a GPU instance.
3. **Incremental ingestion:** Track which filings are already ingested (by accession number). Only process new/changed filings.

---

### Can you explain the use of correlation IDs in your middleware?

A UUID is generated per-request in FastAPI middleware and attached to the request state. This ID is included in all log entries for that request and returned in the response headers. If a user reports an error, support can search logs for the correlation ID and see exactly what happened for that specific request — even across multiple services.

---

### If you had to add a new financial metric, which files in the domain/ directory would you modify?

1. `extraction.py` — add the extraction function (e.g., `compute_free_cash_flow()`)
2. `coverage.py` — add the new metric keyword to coverage validation
3. `workflows.py` — optionally add a new prompt template if the metric needs special narrative handling
4. `retrieval.py` — optionally adjust search depth if the metric needs specific chunk types
5. Tests: `test_extraction.py` — add unit tests for the new metric

---

### What is the license for this project, and why was it chosen?

Proprietary — Driftwood Capital internal use. Not licensed for redistribution. Chosen because this is an internal tool for a specific investment research firm. They don't want competitors using their technology or the ingested filing corpus.
