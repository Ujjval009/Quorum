from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

import pytest

from app.domain.retrieval import (
    RetrievedChunk,
    detect_tickers,
    hybrid_search,
)
from app.models.base import SessionLocal

eval = pytest.mark.eval


# ── Ground-truth labeled eval set ──────────────────────────────────────────
# Each entry: (case_id, query, expected_ticker, expected_fiscal_year,
#              expected_section_keywords, expected_value_patterns)
# expected_fiscal_year=None means "any year for this company is acceptable"
# The ticker/section/value checks are cumulative: a chunk must satisfy all
# to count as "relevant" for Recall@k / MRR.

RETRIEVAL_EVAL_SET = [
    # ── Revenue / Segment queries ──
    ("rev_aapl_24", "What was Apple's iPhone revenue in FY2024?",
     "AAPL", 2024, ["Item 7", "Item 8", "Item 1"], ["iPhone"]),
    ("rev_aapl_23", "Apple services revenue FY2023",
     "AAPL", 2023, ["Item 7", "Item 8"], ["Services"]),
    ("rev_amzn_aws_23", "Amazon AWS revenue FY2023",
     "AMZN", 2023, ["Item 8", "Segment", "AWS"], ["AWS"]),
    ("rev_amzn_aws_24", "AWS operating income FY2024",
     "AMZN", 2024, ["Item 8", "Segment"], ["operating income"]),
    ("rev_msft_azure_23", "Microsoft Azure revenue growth FY2023",
     "MSFT", 2023, ["Item 7", "Intelligent Cloud"], ["Azure"]),
    ("rev_msft_cloud_24", "Microsoft Intelligent Cloud revenue FY2024",
     "MSFT", 2024, ["Item 7", "Intelligent Cloud"], ["Cloud"]),
    ("rev_nvda_dc_24", "NVIDIA data center revenue FY2024",
     "NVDA", 2024, ["Item 7", "Data Center"], ["Data Center"]),
    ("rev_googl_cloud_23", "Google Cloud revenue FY2023",
     "GOOGL", 2023, ["Item 7", "Item 8", "Cloud"], ["Cloud"]),
    ("rev_googl_search_24", "Google Search advertising revenue FY2024",
     "GOOGL", 2024, ["Item 1", "Item 7"], ["Advertising", "Search"]),
    ("rev_aapl_mix_24", "Apple revenue mix by product category FY2024",
     "AAPL", 2024, ["Item 7", "Item 8", "Net Sales"], ["iPhone", "Services", "Mac"]),

    # ── Financial metrics queries ──
    ("fin_aapl_cagr", "Apple 3-year revenue CAGR",
     "AAPL", None, ["Item 7", "Results of Operations"], ["revenue"]),
    ("fin_aapl_margin_23", "Apple gross margin FY2023",
     "AAPL", 2023, ["Item 7", "Item 8"], ["gross margin"]),
    ("fin_amzn_ni_23", "Amazon net income FY2023",
     "AMZN", 2023, ["Item 8"], ["Net income"]),
    ("fin_nvda_margin_25", "NVIDIA operating margin FY2025",
     "NVDA", 2025, ["Item 7", "Item 8"], ["operating", "margin"]),
    ("fin_googl_fcf", "Google free cash flow FY2024",
     "GOOGL", 2024, ["Item 7", "Liquidity"], ["cash flow"]),
    ("fin_msft_oi_trend", "Microsoft operating income trend",
     "MSFT", None, ["Item 7", "Results of Operations"], ["operating income"]),

    # ── Risk factor queries ──
    ("risk_aapl_22", "Apple risk factors FY2022",
     "AAPL", 2022, ["Item 1A", "Risk Factors"], ["risk"]),
    ("risk_aapl_23", "What risks does Apple face in FY2023?",
     "AAPL", 2023, ["Item 1A", "Risk Factors"], ["risk"]),
    ("risk_amzn", "Amazon risk factors",
     "AMZN", None, ["Item 1A", "Risk Factors"], ["risk"]),
    ("risk_msft_24", "Microsoft risk factors FY2024",
     "MSFT", 2024, ["Item 1A", "Risk Factors"], ["risk"]),
    ("risk_nvda_23", "NVIDIA risk factors FY2023",
     "NVDA", 2023, ["Item 1A", "Risk Factors"], ["risk"]),

    # ── AI disclosure queries ──
    ("ai_msft", "Microsoft AI disclosure risk factors",
     "MSFT", None, ["Item 1A", "Risk Factors", "Item 1"], ["AI", "artificial intelligence"]),
    ("ai_googl", "Google AI investment disclosures",
     "GOOGL", None, ["Item 1", "Item 7"], ["AI", "artificial intelligence"]),
    ("ai_nvda", "NVIDIA AI capabilities and strategy",
     "NVDA", None, ["Item 1", "Item 7"], ["AI", "accelerated computing"]),
    ("ai_amzn", "Amazon AI infrastructure investments",
     "AMZN", None, ["Item 7", "Item 1"], ["AI", "machine learning"]),

    # ── Business segment queries ──
    ("seg_aapl", "Apple main business segments",
     "AAPL", None, ["Item 1", "Business"], ["iPhone", "Services", "Mac"]),
    ("seg_amzn_aws", "Amazon AWS segment performance",
     "AMZN", None, ["Segment", "AWS"], ["AWS"]),
    ("seg_msft_cloud", "Microsoft Intelligent Cloud vs Personal Computing",
     "MSFT", None, ["Item 7", "Segment"], ["Intelligent Cloud", "Personal Computing"]),
    ("seg_googl_cloud", "Google Cloud revenue trends",
     "GOOGL", None, ["Item 7", "Cloud"], ["Cloud"]),
    ("seg_nvda_dc", "NVIDIA Data Center segment growth",
     "NVDA", None, ["Item 7", "Data Center"], ["Data Center"]),

    # ── Narrative / General queries ──
    ("gen_msft_summary", "Summarize Microsoft FY2023 financial results",
     "MSFT", 2023, ["Item 7", "Item 8"], ["revenue", "net income"]),
    ("gen_amzn_risks", "What risks does Amazon face?",
     "AMZN", None, ["Item 1A", "Risk Factors"], ["risk"]),
    ("gen_googl_money", "How does Google make money?",
     "GOOGL", None, ["Item 1", "Business"], ["advertising", "Search"]),
    ("gen_nvda_strategy", "NVIDIA business strategy",
     "NVDA", None, ["Item 1", "Business"], ["accelerated computing", "Data Center"]),
    ("gen_aapl_services", "Apple services business overview",
     "AAPL", None, ["Item 1", "Item 7"], ["Services"]),
]

ASSERT_RETRIEVAL_COUNT = 35
assert len(RETRIEVAL_EVAL_SET) == ASSERT_RETRIEVAL_COUNT, (
    f"Expected {ASSERT_RETRIEVAL_COUNT} eval cases, got {len(RETRIEVAL_EVAL_SET)}"
)


# ── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Metrics helpers ──────────────────────────────────────────────────────────

def _is_relevant_chunk(
    chunk: RetrievedChunk,
    expected_ticker: str,
    expected_fiscal_year: int | None,
    expected_section_keywords: list[str],
    expected_value_patterns: list[str],
) -> bool:
    """Check if a chunk matches the ground-truth expectations."""
    if chunk.ticker and chunk.ticker.upper() != expected_ticker.upper():
        return False
    if expected_fiscal_year is not None:
        if chunk.fiscal_year != expected_fiscal_year:
            return False
    section = (chunk.section_title or "").lower()
    if not any(kw.lower() in section for kw in expected_section_keywords):
        return False
    content = (chunk.content or "").lower()
    if not any(p.lower() in content for p in expected_value_patterns):
        return False
    return True


def _recall_at_k(
    chunks: list[RetrievedChunk],
    k: int,
    expected_ticker: str,
    expected_fiscal_year: int | None,
    expected_section_keywords: list[str],
    expected_value_patterns: list[str],
) -> float:
    """Recall@k: does any chunk in top-k match all criteria?"""
    for c in chunks[:k]:
        if _is_relevant_chunk(c, expected_ticker, expected_fiscal_year,
                               expected_section_keywords, expected_value_patterns):
            return 1.0
    return 0.0


def _ticker_precision(
    chunks: list[RetrievedChunk],
    k: int,
    expected_ticker: str,
) -> float:
    """Precision@k (ticker): fraction of top-k chunks with the correct ticker."""
    if not chunks or k == 0:
        return 0.0
    top_k = chunks[:k]
    matches = sum(1 for c in top_k if c.ticker and c.ticker.upper() == expected_ticker.upper())
    return matches / k


def _mrr(
    chunks: list[RetrievedChunk],
    expected_ticker: str,
    expected_fiscal_year: int | None,
    expected_section_keywords: list[str],
    expected_value_patterns: list[str],
) -> float:
    """Mean Reciprocal Rank: 1/rank of first relevant chunk, 0 if none."""
    for rank, c in enumerate(chunks):
        if _is_relevant_chunk(c, expected_ticker, expected_fiscal_year,
                               expected_section_keywords, expected_value_patterns):
            return 1.0 / (rank + 1)
    return 0.0


def _cross_company_chunks(
    chunks: list[RetrievedChunk],
    expected_ticker: str,
) -> list[RetrievedChunk]:
    """Return chunks from companies OTHER than the expected ticker."""
    expected = expected_ticker.upper()
    return [c for c in chunks if c.ticker and c.ticker.upper() != expected]


# ── Test: Aggregate metrics (primary quality gate) ──────────────────────────

@eval
def test_retrieval_aggregate_metrics(db: Session) -> None:
    """Compute aggregate retrieval metrics across the full eval set.

    This is the primary regression gate. When retrieval quality improves,
    bump the thresholds. Never let them drop.
    """
    total = len(RETRIEVAL_EVAL_SET)
    recall5_sum = 0.0
    recall10_sum = 0.0
    prec5_sum = 0.0
    mrr_sum = 0.0
    failures: list[str] = []

    for case_id, query, expected_ticker, expected_fiscal_year, sections, values in RETRIEVAL_EVAL_SET:
        chunks = hybrid_search(query, db, top_k=10)
        if not chunks:
            failures.append(f"{case_id}: no results")
            continue

        r5 = _recall_at_k(chunks, 5, expected_ticker, expected_fiscal_year, sections, values)
        r10 = _recall_at_k(chunks, 10, expected_ticker, expected_fiscal_year, sections, values)
        p5 = _ticker_precision(chunks, 5, expected_ticker)
        m = _mrr(chunks, expected_ticker, expected_fiscal_year, sections, values)

        recall5_sum += r5
        recall10_sum += r10
        prec5_sum += p5
        mrr_sum += m

        if r5 == 0:
            top_info = "; ".join(
                f"{c.ticker} FY{c.fiscal_year} [{c.section_title}]"
                for c in chunks[:5]
            )
            failures.append(f"{case_id}: no match in top-5 ({top_info})")

    mean_recall5 = recall5_sum / total
    mean_recall10 = recall10_sum / total
    mean_prec5 = prec5_sum / total
    mean_mrr = mrr_sum / total

    print(f"\n{'='*60}")
    print(f"  RETRIEVAL EVAL SUMMARY ({total} queries)")
    print(f"{'='*60}")
    print(f"  Mean Recall@5:    {mean_recall5:.3f}")
    print(f"  Mean Recall@10:   {mean_recall10:.3f}")
    print(f"  Mean Prec@5 (tkr):{mean_prec5:.3f}")
    print(f"  Mean MRR:         {mean_mrr:.3f}")
    if failures:
        print(f"  Failures ({len(failures)}):")
        for f in failures[:10]:
            print(f"    - {f}")
        if len(failures) > 10:
            print(f"    ... and {len(failures) - 10} more")
    print(f"{'='*60}\n")

    # ── Baselines (metadata filtering enabled) ──
    assert mean_recall5 >= 0.80, f"Mean Recall@5: {mean_recall5:.3f} (threshold: 0.80)"
    assert mean_recall10 >= 0.80, f"Mean Recall@10: {mean_recall10:.3f} (threshold: 0.80)"
    assert mean_prec5 >= 0.90, f"Mean Precision@5: {mean_prec5:.3f} (threshold: 0.90)"
    assert mean_mrr >= 0.70, f"Mean MRR: {mean_mrr:.3f} (threshold: 0.70)"


# ── Test: Cross-company contamination ───────────────────────────────────────

CROSS_COMPANY_CASES = [
    ("cc_msft_risk", "Microsoft risk factors FY2024", "MSFT", "AAPL"),
    ("cc_googl_risk", "Google risk factors", "GOOGL", "AMZN"),
    ("cc_nvda_risk", "NVIDIA risk factors FY2023", "NVDA", "MSFT"),
    ("cc_aapl_risk", "Apple risk factors FY2022", "AAPL", "AMZN"),
    ("cc_amzn_risk", "Amazon risk factors", "AMZN", "GOOGL"),
]


@eval
@pytest.mark.parametrize(
    "case_id,query,intended_ticker,wrong_ticker",
    CROSS_COMPANY_CASES,
    ids=[c[0] for c in CROSS_COMPANY_CASES],
)
def test_cross_company_no_contamination(
    db: Session,
    case_id: str,
    query: str,
    intended_ticker: str,
    wrong_ticker: str,
) -> None:
    """Searching with a specific ticker filter must NOT return wrong company chunks."""
    chunks = hybrid_search(query, db, top_k=10, ticker=intended_ticker)
    assert len(chunks) >= 1, (
        f"{case_id}: no results for ticker={intended_ticker}. "
        f"query='{query}'"
    )
    wrong = _cross_company_chunks(chunks, intended_ticker)
    assert len(wrong) == 0, (
        f"{case_id}: {len(wrong)} chunks from '{wrong_ticker}' found "
        f"despite ticker filter. query='{query}'"
    )





# ── Test: Multi-ticker detection ─────────────────────────────────────────────

MULTI_TICKER_CASES = [
    ("mt1", "Compare Apple and Microsoft revenue", ["AAPL", "MSFT"]),
    ("mt2", "Amazon vs Google cloud growth", ["AMZN", "GOOGL"]),
    ("mt3", "NVIDIA and Apple AI investment comparison", ["NVDA", "AAPL"]),
    ("mt4", "Microsoft Azure vs AWS vs Google Cloud", ["MSFT", "AMZN", "GOOGL"]),
    ("mt5", "Compare capital expenditures at Microsoft, Amazon, and NVIDIA",
     ["MSFT", "AMZN", "NVDA"]),
]


@eval
@pytest.mark.parametrize(
    "case_id,query,expected_tickers",
    MULTI_TICKER_CASES,
    ids=[c[0] for c in MULTI_TICKER_CASES],
)
def test_multi_ticker_detection(
    case_id: str,
    query: str,
    expected_tickers: list[str],
) -> None:
    """Multi-ticker queries must detect all expected tickers."""
    tickers = detect_tickers(query)
    for t in expected_tickers:
        assert t in tickers, (
            f"{case_id}: expected ticker '{t}' not detected in '{query}'. "
            f"Got: {tickers}"
        )


# ── Test: Metadata integrity ─────────────────────────────────────────────────

SAMPLE_QUERIES_FOR_METADATA = [
    ("meta1", "Apple revenue FY2024", "AAPL"),
    ("meta2", "Microsoft cloud FY2023", "MSFT"),
    ("meta3", "Amazon AWS FY2024", "AMZN"),
    ("meta4", "Google risk factors", "GOOGL"),
    ("meta5", "NVIDIA data center", "NVDA"),
]


@eval
@pytest.mark.parametrize(
    "case_id,query,expected_ticker",
    SAMPLE_QUERIES_FOR_METADATA,
    ids=[c[0] for c in SAMPLE_QUERIES_FOR_METADATA],
)
def test_chunk_metadata_integrity(
    db: Session,
    case_id: str,
    query: str,
    expected_ticker: str,
) -> None:
    """Every chunk must have ticker, fiscal_year, section_title, non-empty content."""
    chunks = hybrid_search(query, db, top_k=10)
    for c in chunks:
        assert c.ticker is not None, f"{case_id}: chunk {c.chunk_id} missing ticker"
        assert c.fiscal_year is not None, f"{case_id}: chunk {c.chunk_id} missing fiscal_year"
        assert c.section_title is not None and c.section_title.strip(), (
            f"{case_id}: chunk {c.chunk_id} missing section_title"
        )
        assert c.content is not None, f"{case_id}: chunk {c.chunk_id} has None content"


# ── Test: Chunk size sanity ──────────────────────────────────────────────────

@eval
def test_chunk_size_distribution(db: Session) -> None:
    """Verify chunk sizes are within expected bounds (no truncated/malformed chunks)."""
    result = db.execute(text("""
        SELECT
            MIN(LENGTH(content)) AS min_len,
            AVG(LENGTH(content)) AS avg_len,
            MAX(LENGTH(content)) AS max_len,
            COUNT(*) AS total
        FROM document_chunks
    """)).fetchone()

    total = result.total
    min_len = result.min_len
    avg_len = result.avg_len
    max_len = result.max_len

    assert total >= 3500, f"Expected >= 3500 chunks, got {total}"
    assert min_len == 0 or min_len >= 20, f"Unexpected very small chunks: min={min_len}"
    assert avg_len >= 500, f"Average chunk too small: avg={avg_len}"
    assert max_len <= 7000, f"Chunks exceed reasonable max: max={max_len}"
    assert max_len >= 1000, f"Max chunk too small (possible truncation): max={max_len}"


@eval
def test_chunk_count_per_document(db: Session) -> None:
    """Every document should have a reasonable number of chunks."""
    result = db.execute(text("""
        SELECT sd.ticker, sd.fiscal_year, COUNT(dc.id) AS chunk_count
        FROM source_documents sd
        JOIN document_chunks dc ON dc.document_id = sd.id
        GROUP BY sd.ticker, sd.fiscal_year
        ORDER BY sd.ticker, sd.fiscal_year
    """)).fetchall()

    assert len(result) >= 25, f"Expected 25 documents with chunks, got {len(result)}"
    for r in result:
        assert 50 <= r.chunk_count <= 500, (
            f"{r.ticker} FY{r.fiscal_year}: {r.chunk_count} chunks (expected 50-500)"
        )


# ── Test: Section diversity ──────────────────────────────────────────────────

@eval
def test_section_title_diversity(db: Session) -> None:
    """The corpus should have a healthy number of distinct section titles."""
    result = db.execute(text("""
        SELECT COUNT(DISTINCT section_title)
        FROM document_chunks
        WHERE section_title IS NOT NULL AND section_title != ''
    """)).fetchone()
    distinct = result[0]
    assert distinct >= 20, f"Only {distinct} distinct section titles (expected >= 20)"
