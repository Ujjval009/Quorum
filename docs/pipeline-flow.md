# Pipeline Flow

Two pipelines power Quorum: **Ingestion** (SEC HTML → database) and **Query** (user question → grounded answer).

---

## 1. Ingestion Pipeline

Transforms raw SEC 10-K HTML filings into searchable chunks with embeddings.

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  SEC EDGAR   │   │  HTML Parser │   │  Section     │   │  Chunking    │   │  Embedding   │
│  10-K Filings │──→│  strip tags  │──→│  Extractor   │──→│  + Overlap   │──→│  + Storage   │
│  (HTML)      │   │  skip XBRL   │   │  Item 1–16   │   │  4000 chars  │   │  pgvector    │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
                                                                                    │
                                                                                    ▼
                                                                           ┌──────────────────┐
                                                                           │  source_documents│
                                                                           │  document_chunks │
                                                                           │  (PostgreSQL)    │
                                                                           └──────────────────┘
```

### Step-by-step

| Step | File | What happens |
|------|------|--------------|
| **1. Read manifest** | `scripts/ingest_html.py` | Reads `data/downloads/manifest.json` — lists ticker, year, local HTML path for each filing |
| **2. Parse HTML** | `scripts/ingest_html.py` | `SECHTMLParser` strips script/style tags via Python `HTMLParser`, removes XBRL `ix:` namespace junk |
| **3. Extract sections** | `scripts/ingest_html.py` | Regex `_ITEM_PATTERN` splits text on `Item 1.`, `Item 1A.`, `Item 7.`, etc. Maps raw labels to canonical titles via `_COMMON_SECTION_TITLES` dictionary |
| **4. Chunk** | `scripts/ingest_html.py` | Splits each section into ~4000-char chunks with 200-char overlap on sentence/paragraph boundaries. Falls back to 800-word chunks for dense text |
| **5. Embed** | `scripts/ingest_html.py` | Batch-embeds all chunks via configured provider → 768-dim vector. Default: HuggingFace `sentence-transformers/multi-qa-mpnet-base-dot-v1`. Fallback: Ollama `nomic-embed-text` |
| **6. Store** | `scripts/ingest_html.py` | `SourceDocument` (filing metadata) → 1 row. `DocumentChunk` (text + embedding + metadata) → N rows per filing. Committed in batch per document |

### Schema (PostgreSQL + pgvector)

```
source_documents              document_chunks
┌─────────────────────┐      ┌──────────────────────────┐
│ id (UUID)           │←─────│ document_id (FK)         │
│ ticker (VARCHAR)    │      │ id (UUID)                │
│ fiscal_year (INT)   │      │ chunk_index (INT)        │
│ filing_type (TEXT)  │      │ content (TEXT)           │
│ source_type (TEXT)  │      │ section_title (TEXT)     │
│ title (TEXT)        │      │ page_number (INT)        │
│ filename (TEXT)     │      │ token_count (INT)        │
│ content (TEXT)      │      │ embedding (vector(768))  │
│ page_count (INT)    │      │ search_vector (tsvector) │
│ created_at (TZ)     │      │ created_at (TZ)          │
└─────────────────────┘      └──────────────────────────┘
```

Indexes: HNSW on `embedding` (cosine), GIN on `search_vector`, B-tree on `(ticker, fiscal_year)`.

---

## 2. Query Pipeline

Converts a natural language question into a sourced analyst answer.

```
User: "What was Apple's revenue in 2024?"

      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    1. METADATA FILTERING                         │
│   extract_filters("Apple revenue 2024") → tickers=[AAPL]        │
│                                              years=[2024]       │
│   Uses TICKER_ALIASES map + FY_PATTERN regex                    │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    2. INTENT DETECTION                           │
│   detect_intent("revenue 2024") → "financial_metrics"            │
│   Categories: revenue_mix, financial_metrics, company_comparison │
│   risk_factor_diff, ai_disclosure, segment, general              │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    3. HYBRID SEARCH (2 parallel queries)         │
│                                                                  │
│   ┌──────────────────────┐    ┌──────────────────────┐           │
│   │  Vector Search       │    │  Full-Text Search    │           │
│   │  pgvector cosine sim │    │  ts_rank(to_tsquery) │           │
│   │  WHERE ticker=ANY    │    │  WHERE ticker=ANY    │           │
│   │  AND year=ANY        │    │  AND year=ANY        │           │
│   └──────────┬───────────┘    └──────────┬───────────┘           │
│              │                           │                       │
│              └──────────┬────────────────┘                       │
│                         │                                        │
│                ┌────────▼────────┐                               │
│                │  RRF Fusion     │                               │
│                │  Reciprocal     │                               │
│                │  Rank Fusion    │                               │
│                │  (k=60)         │                               │
│                └────────┬────────┘                               │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    4. EXTRACTION (deterministic, no LLM)         │
│                                                                  │
│   extract_facts(chunks) → FactSet                                │
│   ├── Revenue by category & year tables                          │
│   ├── Growth rates (YoY, CAGR) via compute_growth_rates()        │
│   ├── Revenue shares / mix via compute_revenue_shares()          │
│   ├── Margins (gross, operating, net)                            │
│   ├── EPS values                                                 │
│   └── All computed via Python regex — never by the LLM           │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    5. COVERAGE VALIDATION                        │
│                                                                  │
│   validate_coverage(query, chunks, intent)                       │
│   ├── Checks which metric keywords are covered by chunks         │
│   ├── If gaps found → expand_coverage() → re-search              │
│   └── If still gaps → warn but proceed with available data       │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    6. GENERATION (tables first, then LLM)        │
│                                                                  │
│   ┌──────────────────────────────────────────┐                   │
│   │  STRUCTURED INTENT?                      │                   │
│   │  (revenue_mix, financial_metrics, etc.)  │                   │
│   └────────────┬─────────────────────────────┘                   │
│                │                                                 │
│       YES      │          NO                                     │
│         │      │          │                                      │
│         ▼      │          ▼                                      │
│  ┌──────────┐  │   ┌──────────────┐                             │
│  │ Build    │  │   │ Build raw    │                             │
│  │ structured│  │   │ chunk context│                             │
│  │ tables   │  │   │ → LLM        │                             │
│  │ (Python)  │  │   └──────────────┘                             │
│  └────┬─────┘  │                                                │
│       │        │                                                │
│       ▼        │                                                │
│  ┌──────────┐  │                                                │
│  │ LLM      │  │                                                │
│  │ narrative│  │                                                │
│  │ overlay  │  │                                                │
│  └──────────┘  │                                                │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    7. CITATION BUILDING                          │
│                                                                  │
│   _build_citations(chunks, answer) → list of Citation            │
│   ├── Each citation has: chunk_id, ticker, fiscal_year           │
│   │   section_title, excerpt                                     │
│   ├── Deduplicated (no repeat chunk_ids)                         │
│   └── Filtered by ticker (no cross-company contamination)        │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    8. PERSIST + RESPOND                          │
│                                                                  │
│   ┌─────────────────────┐  ┌────────────────────┐                │
│   │  Save assistant msg │  │  Stream to browser │                │
│   │  Save citations     │  │  (or return JSON)  │                │
│   │  DB commit          │  │  + citation data   │                │
│   └─────────────────────┘  └────────────────────┘                │
└──────────────────────────────────────────────────────────────────┘

      │
      ▼
User sees: structured tables + narrative + clickable citations
```

---

## 3. Intent Workflow Routing

The intent detection determines which generation path is taken:

| Intent | Extraction | Structure | Prompt |
|--------|-----------|-----------|--------|
| `revenue_mix` | `extract_facts` → revenue by category + mix shares | `build_mix_context()` → markdown table | `STRUCTURED_REVENUE_MIX_NARRATIVE` |
| `financial_metrics` | `extract_facts` → CAGR, margins, growth rates | `format_structured_context()` → markdown section | `STRUCTURED_FINANCIAL_METRICS_NARRATIVE` |
| `company_comparison` | Per-ticker extraction → side-by-side | `build_comparison_context()` → comparison table | `STRUCTURED_COMPARISON_NARRATIVE` |
| `risk_factor_diff` | Cross-year section comparison | `build_risk_diff_context()` → diff output | `STRUCTURED_RISK_DIFF_NARRATIVE` |
| `segment` | Segment-level extraction | `build_mix_context()` filtered to segment | `STRUCTURED_SEGMENT_NARRATIVE` |
| `ai_disclosure` | Keyword-based chunk filtering | Raw context → LLM | `GENERAL_PROMPT` |
| `general` | None | Raw context → LLM | `GENERAL_PROMPT` |

---

## 4. Key files reference

| File | Role |
|------|------|
| `scripts/ingest_html.py` | SEC HTML → `source_documents` + `document_chunks` |
| `app/domain/embeddings.py` | `generate_embedding()` — HuggingFace or Ollama provider |
| `app/domain/retrieval.py` | `extract_filters()`, `_vector_search()`, `_fts_search()`, `hybrid_search()`, `detect_intent()` |
| `app/domain/extraction.py` | `extract_facts()`, `compute_cagr()`, `compute_growth_rates()`, `compute_revenue_shares()` |
| `app/domain/coverage.py` | `validate_coverage()`, `expand_coverage()` |
| `app/domain/workflows.py` | Intent-specific prompts + structured answer builders |
| `app/domain/revenue_mix.py` | `build_mix_context()` — revenue mix tables |
| `app/domain/risk_diff.py` | `build_risk_diff_context()` — risk factor diffs |
| `app/domain/comparison.py` | `build_comparison_context()` — multi-ticker tables |
| `app/domain/rag.py` | `generate_answer()`, `generate_answer_stream()`, `_build_citations()` |
| `app/api/chat.py` | HTTP endpoints: ask, stream, thread CRUD |
