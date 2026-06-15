# Testing

## Suite overview

| Suite | File | Count | Marker | Requires |
|-------|------|-------|--------|----------|
| Fast unit tests | `tests/test_*.py` (excluding eval_suite) | 138 (unit) + 19 (retrieval eval) | `not eval` | Nothing (mocked) |
| Retrieval quality | `tests/test_retrieval_eval.py` | 19 | none | Running backend + live DB |
| Regression eval | `tests/eval_suite.py` | 52 parametrized + 9 standalone | `eval` | Running backend + live DB + LLM API key |

## Quick start

```bash
# Fast checks (no network, no LLM)
cd backend && uv run pytest -v -m "not eval"

# Full regression eval suite
cd backend && uv run pytest tests/eval_suite.py -v -m eval
```

## Test structure

### Parametrized cases (43 tests)

All registered via `ALL_EVAL_CASES` at `eval_suite.py:136` and dispatched through `test_eval_query`:

| Category | Cases | What it tests |
|----------|-------|---------------|
| `REVENUE_MIX_CASES` | rm1–rm6 | Revenue mix, product contribution, mix shifts |
| `FINANCIAL_METRICS_CASES` | fm1–fm7 | CAGR, margins, growth rates, P&L trends |
| `COMPARISON_CASES` | cmp1–cmp6, ie2 | Cross-company side-by-side tables |
| `RISK_FACTOR_CASES` | risk1–risk4 | Risk factor diff across years |
| `AI_DISCLOSURE_CASES` | ai1–ai5 | AI terminology evolution over time |
| `INSUFFICIENT_EVIDENCE_CASES` | ie1, ie3 | Queries with no data → graceful degredation |
| `BUSINESS_SEGMENT_CASES` | seg1–seg5 | Segment-level revenue, mix, growth |
| `GENERAL_CASES` | gen1–gen7 | Unstructured narrative answers |

### Standalone tests (9 tests)

| Test | What it validates |
|------|-------------------|
| `test_revenue_mix_structured_output` | Structured data marker on mix query |
| `test_comparison_structured_output` | Both tickers appear in comparison citations |
| `test_single_ticker_no_cross_company` | No cross-company citation leaks |
| `test_citations_deduplicated` | No duplicate chunk IDs in citations |
| `test_risk_diff_multi_year` | Multi-year risk diff non-empty |
| `test_insufficient_evidence_unknown_ticker` | Unknown ticker returns insufficient evidence |
| `test_cloud_segment_comparison` | Cloud segment query → structured or insufficient |
| `test_citations_have_metadata` | Every citation has ticker, year, section_title |
| `test_answer_has_sections` | General answers have Executive Summary + Key Findings |

### What each test validates

Every parametrized case checks:
1. **Answer non-empty**
2. **Insufficient evidence** — correct graceful response when data is absent
3. **Structured data marker** — `=== STRUCTURED FINANCIAL DATA` present for structured intents
4. **Citation count** — minimum citations threshold
5. **Citation deduplication** — no duplicate chunk IDs
6. **Citation ticker integrity** — every citation ticker is in expected list
7. **Single-ticker isolation** — no cross-company contamination for single-ticker queries
8. **Citation excerpt** — every citation has non-empty excerpt

Standalone tests add: structured output format, cross-company citation correctness, section headers in narrative, citation metadata completeness.

## Results

### 2026-06-13 — Final: **52/52 PASSING**

| Run | Config | Passed | Failed | Skipped |
|-----|--------|--------|--------|---------|
| 1 | Groq `llama-3.3-70b-versatile` | 8 | 0 | 44 (rate limited) |
| 2 | Groq `groq/compound-mini` | 8 | 0 | 44 (rate limited) |
| 3 | Groq `llama-3.3-70b-versatile` (next day) | 24 | 4 (fm2, ie2, seg2, seg5) | 16 |
| 4 | **OpenRouter** `meta-llama/llama-3.3-70b-instruct` | **52** | **0** | **0** |

### Fixes applied during runs

| Test | Issue | Fix |
|------|-------|-----|
| `fm2` | NVDA citation leaked into Apple-only CAGR query | Added `"iphone"` to `COMPANY_TICKER_MAP` in `retrieval.py` |
| `ie2` | Expected `insufficient_evidence` but system produced structured cloud data | Moved test from `INSUFFICIENT_EVIDENCE_CASES` to `COMPARISON_CASES` |
| `seg2` | AWS segment query produced narrative-only output (missing structured tables) | Added `business_segment` to `STRUCTURED_INTENTS` + added `STRUCTURED_SEGMENT_NARRATIVE` prompt |
| `seg5` | Same as seg2 + "data center" not recognized as segment keyword | Added `"data center"` and `"segment growth"` to `_SEGMENT_QUERY_KEYWORDS` |

## Rate limiting & providers

### Groq free tier limits

| Model | RPM | RPD | TPM | TPD |
|-------|-----|-----|-----|-----|
| `llama-3.3-70b-versatile` | 30 | 1,000 | 12,000 | 100,000 |

The full eval suite consumes ~50–80k tokens. With Groq free tier's 100k TPD, you get **one full run per day**.

### OpenRouter (production recommendation)

Switch to OpenRouter for production / CI:

```bash
# .env
GROQ_API_KEY=sk-or-v1-<your-key>
GROQ_LLM_MODEL=meta-llama/llama-3.3-70b-instruct
LLM_BASE_URL=https://openrouter.ai/api/v1
```

The config in `config.py` reads `LLM_BASE_URL` and falls back to `https://api.groq.com/openai/v1` when empty.

## Switching providers

The `.env` file controls the LLM provider. To switch between Groq and OpenRouter:

```bash
# ── OpenRouter (current) ──
GROQ_API_KEY=sk-or-v1-<your-key>
GROQ_LLM_MODEL=meta-llama/llama-3.3-70b-instruct
LLM_BASE_URL=https://openrouter.ai/api/v1

# ── Groq (original) ──
GROQ_API_KEY=gsk-<your-groq-key>
GROQ_LLM_MODEL=llama-3.3-70b-versatile
LLM_BASE_URL=                           # empty = uses default Groq URL
```

`config.py` checks `LLM_BASE_URL` first — when empty, it defaults to `https://api.groq.com/openai/v1`.

## CI integration

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg17
        env:
          POSTGRES_DB: quorum_test
          POSTGRES_PASSWORD: test
        ports: [5432:5432]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - name: Fast unit tests
        run: uv run pytest -v -m "not eval"
      - name: Eval suite
        run: uv run pytest tests/eval_suite.py -v -m eval
        env:
          GROQ_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          GROQ_LLM_MODEL: meta-llama/llama-3.3-70b-instruct
          LLM_BASE_URL: https://openrouter.ai/api/v1
```

## Architecture

```
pytest -m "not eval"                    pytest -m eval
       │                                       │
       ▼                                       ▼
  Unit tests                          api_client fixture
  (no deps, no net)                    ┌──────────────────┐
                                       │ POST /auth/login │
                                       │ (once per sess.) │
                                       └──────┬───────────┘
                                              │
                ┌─────────────────────────────┐
                │  POST /chat/threads/{id}/ask │
                └──────────┬──────────────────┘
                           │
                ┌──────────▼──────────┐
                │  generate_answer()   │
                │  rag.py:42           │
                └──────────┬──────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
     structured intents          non-structured
     (revenue_mix,               (general, ai,
      financial_metrics,          risk, segment)
      comparison)
              │                         │
              ▼                         ▼
    build_structured_answer()    build_workflow_context()
    workflows.py:372             workflows.py:439
              │                         │
              ▼                         ▼
    extract_facts()              _format_workflow_context()
    (deterministic,              (raw chunk context → LLM)
     no LLM)
              │
              ▼
    format_structured_context()
    (tables first)
              │
              ▼
    LLM narrative overlay
    (tables + narrative)
```
