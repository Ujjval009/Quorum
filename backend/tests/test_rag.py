from __future__ import annotations

from app.domain.retrieval import RetrievedChunk
from app.domain.workflows import (
    GENERAL_PROMPT,
    INSUFFICIENT_EVIDENCE_RESPONSE,
    STRUCTURED_REVENUE_MIX_NARRATIVE,
    STRUCTURED_INTENTS,
    NARRATIVE_OVERLAY_INSTRUCTION,
    _format_workflow_context,
    _is_segment_query,
    build_structured_answer,
    check_sufficient_evidence,
)

REVENUE_MIX_PROMPT = STRUCTURED_REVENUE_MIX_NARRATIVE


def _make_chunk(
    chunk_id: str,
    content: str,
    page: int | None = 1,
    idx: int = 0,
    ticker: str = "",
    fiscal_year: int | None = None,
    section_title: str = "",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        content=content,
        page_number=page,
        chunk_index=idx,
        score=0.9,
        source="vector",
        ticker=ticker,
        fiscal_year=fiscal_year,
        section_title=section_title,
    )


def test_general_prompt_contains_key_rules():
    assert "equity research analyst" in GENERAL_PROMPT
    assert "Executive Summary" in GENERAL_PROMPT
    assert "Detailed Analysis" in GENERAL_PROMPT
    assert "Key Findings" in GENERAL_PROMPT
    assert "Analyst Takeaway" in GENERAL_PROMPT


def test_revenue_mix_prompt_focuses_on_mix():
    assert "mix shares" in REVENUE_MIX_PROMPT.lower()
    assert "do not" in REVENUE_MIX_PROMPT.lower()


def test_format_context_single_chunk():
    chunks = [_make_chunk("c1", "This is the first chunk.")]
    result = _format_workflow_context(chunks)
    assert "[1]" in result
    assert "This is the first chunk." in result


def test_format_context_multiple_chunks():
    chunks = [
        _make_chunk("c1", "First chunk.", page=1),
        _make_chunk("c2", "Second chunk.", page=2),
    ]
    result = _format_workflow_context(chunks)
    assert "[1]" in result
    assert "[2]" in result
    assert "First chunk." in result
    assert "Second chunk." in result


def test_format_context_includes_page_numbers():
    chunks = [_make_chunk("c1", "Some text.", page=5)]
    result = _format_workflow_context(chunks)
    assert "p.5" in result


def test_format_context_handles_no_page():
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="doc-1",
        content="No page info.",
        page_number=None,
        chunk_index=0,
        score=0.9,
        source="vector",
    )
    result = _format_workflow_context([chunk])
    assert "Page" not in result.split("\n")[0]


def test_check_sufficient_evidence_passes_good_answer():
    answer = "**Executive Summary**\n\nRevenue grew 8% YoY."
    assert check_sufficient_evidence(answer, []) == answer


def test_check_sufficient_evidence_standardizes_insufficiency():
    answer = "I do not have enough evidence to answer this question."
    assert check_sufficient_evidence(answer, []) == INSUFFICIENT_EVIDENCE_RESPONSE


def test_check_sufficient_evidence_catches_empty_sorry():
    answer = "I'm sorry, I cannot answer this."
    assert check_sufficient_evidence(answer, []) == INSUFFICIENT_EVIDENCE_RESPONSE


# --- Structured pipeline output tests ---

def _make_financial_chunk(
    ticker: str, year: int, metric: str, value: str,
) -> RetrievedChunk:
    """Create a chunk containing a recognizable financial fact."""
    return _make_chunk(
        chunk_id=f"{ticker}-{year}-{metric}",
        content=f"Total Net Sales {value}. {metric} segment revenue {value}.",
        ticker=ticker,
        fiscal_year=year,
        section_title="Item 7. Management's Discussion and Analysis",
    )


def test_build_structured_answer_returns_tuple():
    chunks = [_make_financial_chunk("AAPL", 2023, "iPhone", "$200,000")]
    result = build_structured_answer("test query", chunks, "revenue_mix")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_build_structured_answer_tables_contain_marker():
    chunks = [
        _make_financial_chunk("AAPL", 2022, "iPhone", "$180,000"),
        _make_financial_chunk("AAPL", 2023, "iPhone", "$200,000"),
    ]
    tables, messages = build_structured_answer("test query", chunks, "revenue_mix")
    assert "=== STRUCTURED FINANCIAL DATA" in tables


def test_build_structured_answer_messages_contain_narrative_overlay():
    chunks = [
        _make_financial_chunk("AAPL", 2022, "iPhone", "$180,000"),
        _make_financial_chunk("AAPL", 2023, "iPhone", "$200,000"),
    ]
    _, messages = build_structured_answer("test query", chunks, "revenue_mix")
    system_msg = messages[0]["content"]
    assert "NARRATIVE ANALYSIS ONLY" in system_msg or "NARRATIVE OVERLAY" in system_msg or "DO NOT reproduce any table" in system_msg


def test_build_structured_answer_messages_have_precomputed_label():
    chunks = [
        _make_financial_chunk("AAPL", 2022, "iPhone", "$180,000"),
        _make_financial_chunk("AAPL", 2023, "iPhone", "$200,000"),
    ]
    _, messages = build_structured_answer("test query", chunks, "revenue_mix")
    user_msg = messages[-1]["content"]
    assert "Pre-computed Data Tables" in user_msg


def test_build_structured_answer_uses_narrative_prompt_for_financial_metrics():
    chunks = [
        _make_financial_chunk("AAPL", 2022, "iPhone", "$180,000"),
        _make_financial_chunk("AAPL", 2023, "iPhone", "$200,000"),
    ]
    _, messages = build_structured_answer("test query", chunks, "financial_metrics")
    system_msg = messages[0]["content"]
    assert "Executive Summary" in system_msg
    assert "Key Findings" in system_msg


# ── Evidence validation rejections ───────────────────────────────────────────

def test_validate_rejects_single_year_revenue_mix():
    """Revenue mix requires >= 2 years — single year must be rejected."""
    chunks = [_make_financial_chunk("AAPL", 2023, "iPhone", "$200,000")]
    tables, messages = build_structured_answer("test query", chunks, "revenue_mix")
    assert "at least two fiscal years" in tables
    assert not messages


def test_validate_rejects_no_data_structured_intent():
    """No extractable facts at all must be rejected."""
    chunks = [_make_chunk("c1", "No financial data here.")]
    tables, messages = build_structured_answer("test query", chunks, "revenue_mix")
    assert "at least two fiscal years" in tables
    assert not messages


def test_build_structured_answer_uses_narrative_prompt_for_comparison():
    chunks = [
        _make_financial_chunk("AAPL", 2023, "iPhone", "$200,000"),
        _make_financial_chunk("MSFT", 2023, "Azure", "$60,000"),
    ]
    _, messages = build_structured_answer("test query", chunks, "company_comparison")
    system_msg = messages[0]["content"]
    assert "Growth & Profitability" in system_msg


def test_structured_intents_defined():
    assert "revenue_mix" in STRUCTURED_INTENTS
    assert "financial_metrics" in STRUCTURED_INTENTS
    assert "company_comparison" in STRUCTURED_INTENTS
    assert len(STRUCTURED_INTENTS) == 4


def test_narrative_overlay_instruction_forbids_tables():
    assert "Do not reproduce any table" in NARRATIVE_OVERLAY_INSTRUCTION
    assert "definitive" in NARRATIVE_OVERLAY_INSTRUCTION


# ── Segment-query detection ──────────────────────────────────────────────────

def test_is_segment_query_detects_aws():
    assert _is_segment_query("Compare AWS and Azure cloud revenue")


def test_is_segment_query_detects_azure():
    assert _is_segment_query("What is Azure revenue growth?")


def test_is_segment_query_detects_google_cloud():
    assert _is_segment_query("Google Cloud vs AWS performance")


def test_is_segment_query_detects_gcp():
    assert _is_segment_query("GCP revenue trends")


def test_is_segment_query_detects_cloud_segment():
    assert _is_segment_query("cloud segment performance comparison")
    assert _is_segment_query("cloud revenue growth rate")
    assert _is_segment_query("cloud business vs on-premise")


def test_is_segment_query_detects_segment_keywords():
    assert _is_segment_query("segment revenue for each division")
    assert _is_segment_query("business segment performance")
    assert _is_segment_query("segment comparison between peers")


def test_is_segment_query_ignores_general_query():
    assert not _is_segment_query("How did revenue perform last year?")
    assert not _is_segment_query("Compare total revenue and net income")
    assert not _is_segment_query("What are the key risk factors?")


# ── Insufficient-evidence guard for segment queries ──────────────────────────

def _make_basic_chunk(ticker: str, content: str, year: int = 2023) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{ticker}-chunk",
        document_id=f"doc-{ticker}",
        content=content,
        page_number=1,
        chunk_index=0,
        score=0.9,
        source="vector",
        ticker=ticker,
        fiscal_year=year,
        section_title="Item 7. Management's Discussion and Analysis",
    )


def test_build_structured_answer_segment_query_no_segment_facts():
    """When user asks about cloud segments but no segment facts are
    extracted, build_structured_answer must return INSUFFICIENT_EVIDENCE_RESPONSE
    instead of falling back to total-company metrics."""
    chunks = [
        _make_basic_chunk("AMZN", "Total net sales $500,000 $450,000"),
        _make_basic_chunk("MSFT", "Total net sales $200,000 $180,000"),
    ]
    tables, messages = build_structured_answer(
        "Compare AWS and Azure cloud revenue growth",
        chunks,
        "company_comparison",
    )
    assert tables == INSUFFICIENT_EVIDENCE_RESPONSE
    assert not messages  # empty messages = caller should skip LLM call


def test_build_structured_answer_segment_query_with_segment_facts():
    """When segment facts ARE extracted, the function should return
    normal tables + messages (not insufficient-evidence)."""
    chunks = [
        _make_basic_chunk(
            "AMZN", "AWS  $80,000  $75,000\nTotal net sales $500,000 $450,000",
        ),
        _make_basic_chunk(
            "MSFT", "Intelligent Cloud  $60,000  $55,000\nTotal net sales $200,000 $180,000",
        ),
    ]
    tables, messages = build_structured_answer(
        "Compare AWS and Azure cloud revenue growth",
        chunks,
        "company_comparison",
    )
    assert tables != INSUFFICIENT_EVIDENCE_RESPONSE
    assert messages  # non-empty = proceed with LLM call


def test_build_structured_answer_general_query_still_works():
    """Non-segment queries should not trigger the insufficient-evidence guard."""
    chunks = [
        _make_basic_chunk("AMZN", "Total net sales $500,000"),
        _make_basic_chunk("MSFT", "Total net sales $200,000"),
    ]
    tables, messages = build_structured_answer(
        "Compare total revenue of Amazon and Microsoft",
        chunks,
        "company_comparison",
    )
    assert tables != INSUFFICIENT_EVIDENCE_RESPONSE
    assert messages


# ── validate_evidence unit tests ────────────────────────────────────────────

def test_validate_empty_chunks():
    """Empty chunk list should be rejected."""
    from app.domain.workflows import validate_evidence
    msg = validate_evidence("test query", [], "general")
    assert msg is not None
    assert "No documents were retrieved" in msg


def test_validate_single_ticker_mismatch():
    """Query mentions AAPL but chunks have no AAPL data."""
    from app.domain.workflows import validate_evidence
    chunks = [_make_basic_chunk("MSFT", "Some data")]
    msg = validate_evidence("What is AAPL revenue?", chunks, "general")
    assert msg is not None
    assert "AAPL" in msg


def test_validate_multi_ticker_one_missing():
    """Query mentions AMZN and MSFT but only MSFT chunks exist."""
    from app.domain.workflows import validate_evidence
    chunks = [_make_basic_chunk("MSFT", "Some data")]
    msg = validate_evidence("Compare AMZN and MSFT cloud revenue", chunks, "company_comparison")
    assert msg is not None
    assert "AMZN" in msg


def test_validate_risk_diff_single_year():
    """Risk factor diff requires >= 2 years of risk data."""
    from app.domain.workflows import validate_evidence
    chunks = [
        RetrievedChunk(
            chunk_id="risk-2023", document_id="doc",
            content="Risk factors...", page_number=1, chunk_index=0,
            score=0.9, source="vector",
            ticker="AAPL", fiscal_year=2023,
            section_title="Item 1A. Risk Factors",
        ),
    ]
    msg = validate_evidence("risk factor changes", chunks, "risk_factor_diff")
    assert msg is not None
    assert "at least two fiscal years" in msg


def test_validate_risk_diff_two_years_passes():
    """Risk factor diff with >= 2 years should pass chunk-level validation."""
    from app.domain.workflows import validate_evidence
    chunks = [
        RetrievedChunk(
            chunk_id="risk-2022", document_id="doc",
            content="Risk factors...", page_number=1, chunk_index=0,
            score=0.9, source="vector",
            ticker="AAPL", fiscal_year=2022,
            section_title="Item 1A. Risk Factors",
        ),
        RetrievedChunk(
            chunk_id="risk-2023", document_id="doc",
            content="Risk factors...", page_number=1, chunk_index=0,
            score=0.9, source="vector",
            ticker="AAPL", fiscal_year=2023,
            section_title="Item 1A. Risk Factors",
        ),
    ]
    msg = validate_evidence("risk factor changes", chunks, "risk_factor_diff")
    assert msg is None


def test_validate_multi_year_intent_single_year_chunks():
    """Revenue mix with single year of chunks should be rejected."""
    from app.domain.workflows import validate_evidence
    chunks = [_make_basic_chunk("AAPL", "Revenue data", year=2023)]
    msg = validate_evidence("revenue mix analysis", chunks, "revenue_mix")
    assert msg is not None
    assert "at least two fiscal years" in msg


def test_validate_multi_year_intent_two_years_passes():
    """Revenue mix with 2+ years of chunks should pass chunk-level check."""
    from app.domain.workflows import validate_evidence
    chunks = [
        _make_basic_chunk("AAPL", "Revenue data", year=2022),
        _make_basic_chunk("AAPL", "Revenue data", year=2023),
    ]
    msg = validate_evidence("revenue mix analysis", chunks, "revenue_mix")
    assert msg is None


def test_validate_general_intent_no_restrictions():
    """General intents with valid chunks should pass."""
    from app.domain.workflows import validate_evidence
    chunks = [_make_basic_chunk("AAPL", "Some content")]
    msg = validate_evidence("How did AAPL perform?", chunks, "general")
    assert msg is None


def test_validate_company_comparison_both_tickers_present():
    """Company comparison with both tickers present should pass."""
    from app.domain.workflows import validate_evidence
    chunks = [
        _make_basic_chunk("AMZN", "Amazon data"),
        _make_basic_chunk("MSFT", "Microsoft data"),
    ]
    msg = validate_evidence("Compare AMZN and MSFT", chunks, "company_comparison")
    assert msg is None


# ── Citation integrity tests ────────────────────────────────────────────────

from app.domain.rag import _build_citations


def test_build_citations_deduplicates_by_chunk_id():
    """Duplicate chunk_ids should produce exactly one citation."""
    chunk = _make_chunk("dup-id", "Some content")
    chunks = [chunk, chunk]  # same object twice
    citations = _build_citations(chunks)
    assert len(citations) == 1


def test_build_citations_deduplicates_by_id_string():
    """Same chunk_id string from different objects should deduplicate."""
    c1 = _make_chunk("same-id", "Content A", idx=0)
    c2 = _make_chunk("same-id", "Content B", idx=1)
    chunks = [c1, c2]
    citations = _build_citations(chunks)
    assert len(citations) == 1
    # First occurrence wins
    assert "Content A" in citations[0]["excerpt"]


def test_build_citations_preserves_unique_chunks():
    """Different chunk_ids should all appear as citations."""
    chunks = [
        _make_chunk("id-1", "First", idx=0),
        _make_chunk("id-2", "Second", idx=1),
        _make_chunk("id-3", "Third", idx=2),
    ]
    citations = _build_citations(chunks)
    assert len(citations) == 3


def test_build_citations_includes_ticker():
    """Every citation should carry the chunk's ticker."""
    chunk = _make_chunk("c1", "Data", ticker="AAPL")
    citations = _build_citations([chunk])
    assert citations[0]["ticker"] == "AAPL"


def test_build_citations_includes_fiscal_year():
    """Every citation should carry the chunk's fiscal year."""
    chunk = _make_chunk("c1", "Data", idx=0)
    chunk.fiscal_year = 2023
    citations = _build_citations([chunk])
    assert citations[0]["fiscal_year"] == 2023


def test_build_citations_includes_section_title():
    """Every citation should carry the chunk's section title."""
    chunk = _make_chunk("c1", "Data", idx=0)
    chunk.section_title = "Item 7. Management Discussion"
    citations = _build_citations([chunk])
    assert citations[0]["section_title"] == "Item 7. Management Discussion"


def test_build_citations_excerpt_truncated_to_500():
    """Excerpt should be at most 500 characters."""
    chunk = _make_chunk("c1", "X" * 1000, idx=0)
    citations = _build_citations([chunk])
    assert len(citations[0]["excerpt"]) == 500


def test_build_citations_preserves_chunk_id_type():
    """chunk_id should be preserved as-is (str or UUID)."""
    chunk = _make_chunk("my-uuid", "Data", idx=0)
    citations = _build_citations([chunk])
    assert citations[0]["chunk_id"] == "my-uuid"


def test_filter_expanded_to_single_ticker_removes_wrong_ticker():
    """filter_expanded_to_single_ticker must strip cross-company chunks."""
    from app.domain.coverage import filter_expanded_to_single_ticker
    chunks = [
        _make_basic_chunk("AMZN", "Amazon data"),
        _make_basic_chunk("MSFT", "Microsoft data"),
    ]
    filtered = filter_expanded_to_single_ticker(chunks, "AMZN")
    assert len(filtered) == 1
    assert filtered[0].ticker == "AMZN"


def test_filter_expanded_to_single_ticker_preserves_correct():
    """All chunks matching the target ticker survive filtering."""
    from app.domain.coverage import filter_expanded_to_single_ticker
    chunks = [
        _make_basic_chunk("AAPL", "Apple data A", year=2022),
        _make_basic_chunk("AAPL", "Apple data B", year=2023),
    ]
    filtered = filter_expanded_to_single_ticker(chunks, "AAPL")
    assert len(filtered) == 2


def test_filter_expanded_to_single_ticker_empty_on_full_miss():
    """No matching chunks produces an empty list."""
    from app.domain.coverage import filter_expanded_to_single_ticker
    chunks = [_make_basic_chunk("AMZN", "Amazon data")]
    filtered = filter_expanded_to_single_ticker(chunks, "AAPL")
    assert len(filtered) == 0
