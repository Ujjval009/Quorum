from __future__ import annotations

from app.domain.retrieval import RetrievedChunk, _fuse_results


def _make_chunk(chunk_id: str, score: float = 1.0, source: str = "vector") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        content="test content",
        page_number=1,
        chunk_index=0,
        score=score,
        source=source,
    )


def test_fuse_empty_lists():
    result = _fuse_results([], [], top_k=10)
    assert result == []


def test_fuse_only_vector():
    v = [_make_chunk("a", 0.9), _make_chunk("b", 0.8)]
    result = _fuse_results(v, [], top_k=10)
    assert len(result) == 2
    assert result[0].chunk_id == "a"


def test_fuse_only_fts():
    f = [_make_chunk("a", 0.9, "fts"), _make_chunk("b", 0.8, "fts")]
    result = _fuse_results([], f, top_k=10)
    assert len(result) == 2


def test_fuse_vector_first_then_fts_fill():
    v = [_make_chunk("a", 0.9), _make_chunk("b", 0.8)]
    f = [_make_chunk("b", 0.9, "fts"), _make_chunk("c", 0.7, "fts")]
    result = _fuse_results(v, f, top_k=10)
    # With RRF, chunk_b appears in both sets so it gets ranked highest
    assert result[0].chunk_id == "b"
    # Then chunk_a and chunk_c in RRF order
    assert result[1].chunk_id == "a"
    assert result[2].chunk_id == "c"


def test_fuse_respects_top_k():
    v = [_make_chunk(f"v{i}", 1.0) for i in range(5)]
    result = _fuse_results(v, [], top_k=3)
    assert len(result) == 3


def test_citation_label():
    c = RetrievedChunk(chunk_id="c1", document_id="d1", content="x", page_number=37, chunk_index=0, score=0.9, source="vector", ticker="AAPL", fiscal_year=2024)
    assert c.citation_label == "AAPL FY2024 · p.37"


def test_citation_label_no_page():
    c = RetrievedChunk(chunk_id="c1", document_id="d1", content="x", page_number=None, chunk_index=0, score=0.9, source="vector", ticker="MSFT", fiscal_year=2025)
    assert c.citation_label == "MSFT FY2025"


def test_citation_label_no_ticker():
    c = RetrievedChunk(chunk_id="c1", document_id="d1", content="x", page_number=12, chunk_index=0, score=0.9, source="vector")
    assert c.citation_label == "p.12"


def test_detect_intent_revenue_mix():
    from app.domain.retrieval import detect_intent
    assert detect_intent("How has revenue mix shifted?") == "revenue_mix"
    assert detect_intent("product mix analysis") == "revenue_mix"
    assert detect_intent("revenue by category") == "revenue_mix"
    assert detect_intent("net sales split") == "revenue_mix"


def test_detect_intent_general():
    from app.domain.retrieval import detect_intent
    assert detect_intent("Summary of operations") == "general"
    assert detect_intent("hello") == "general"
    assert detect_intent("what documents are available") == "general"


def test_detect_intent_risk_factor():
    from app.domain.retrieval import detect_intent
    assert detect_intent("What are the risk factors?") == "risk_factor_diff"
    assert detect_intent("item 1a changes") == "risk_factor_diff"


def test_detect_intent_company_comparison():
    from app.domain.retrieval import detect_intent
    assert detect_intent("Compare Apple and Microsoft") == "company_comparison"
    assert detect_intent("Apple vs Microsoft") == "company_comparison"


def test_apply_intent_boost_revenue_table():
    from app.domain.retrieval import _apply_intent_boost
    table_chunk = _make_chunk("table", score=0.5)
    table_chunk.content = "Products and Services Performance table showing net sales by category for 2024"
    narrative_chunk = _make_chunk("narrative", score=0.5)
    narrative_chunk.content = "iPhone and Mac and iPad had strong performance"
    chunks = [table_chunk, narrative_chunk]
    result = _apply_intent_boost(chunks, "revenue_mix")
    assert result[0].chunk_id == "table"
    assert result[0].intent_boost == 2.0
    assert result[1].chunk_id == "narrative"
    assert result[1].intent_boost == 1.0
    assert result[1].score == 0.5


def test_apply_intent_boost_noop_for_general():
    from app.domain.retrieval import _apply_intent_boost
    c = _make_chunk("a", score=0.5)
    c.content = "Products and Services Performance table showing net sales by category"
    chunks = [c]
    result = _apply_intent_boost(chunks, "general")
    assert result[0].score == 0.5
    assert result[0].intent_boost == 1.0


def test_apply_intent_boost_footnote():
    from app.domain.retrieval import _apply_intent_boost
    c = _make_chunk("fn", score=0.5)
    c.content = "disaggregated by significant products and services"
    chunks = [c]
    result = _apply_intent_boost(chunks, "revenue_mix")
    assert result[0].intent_boost == 1.5


# ── Company isolation tests ──

def _make_chunk_with_ticker(chunk_id: str, ticker: str, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        content="test",
        page_number=1,
        chunk_index=0,
        score=score,
        source="vector",
        ticker=ticker,
    )


def test_is_single_company_query_single():
    from app.domain.retrieval import is_single_company_query
    assert is_single_company_query("What is Apple's revenue?") is True
    assert is_single_company_query("MSFT cloud growth") is True
    assert is_single_company_query("NVIDIA risk factors") is True


def test_is_single_company_query_multi():
    from app.domain.retrieval import is_single_company_query
    assert is_single_company_query("Compare Apple and Microsoft") is False
    assert is_single_company_query("Apple vs Google") is False


def test_is_single_company_query_none():
    from app.domain.retrieval import is_single_company_query
    assert is_single_company_query("What is the risk factor disclosure?") is False
    assert is_single_company_query("Revenue growth") is False


def test_filter_chunks_by_ticker_keeps_match():
    from app.domain.retrieval import filter_chunks_by_ticker
    chunks = [
        _make_chunk_with_ticker("1", "AAPL"),
        _make_chunk_with_ticker("2", "AAPL"),
    ]
    result = filter_chunks_by_ticker(chunks, "AAPL")
    assert len(result) == 2


def test_filter_chunks_by_ticker_removes_other():
    from app.domain.retrieval import filter_chunks_by_ticker
    chunks = [
        _make_chunk_with_ticker("1", "AAPL"),
        _make_chunk_with_ticker("2", "MSFT"),
    ]
    result = filter_chunks_by_ticker(chunks, "AAPL")
    assert len(result) == 1
    assert result[0].chunk_id == "1"


def test_filter_chunks_by_ticker_all_wrong():
    from app.domain.retrieval import filter_chunks_by_ticker
    chunks = [
        _make_chunk_with_ticker("1", "MSFT"),
        _make_chunk_with_ticker("2", "GOOGL"),
    ]
    result = filter_chunks_by_ticker(chunks, "AAPL")
    assert result == []


def test_filter_chunks_by_ticker_none_ticker():
    from app.domain.retrieval import filter_chunks_by_ticker
    chunks = [
        _make_chunk_with_ticker("1", "AAPL"),
        _make_chunk_with_ticker("2", "MSFT"),
    ]
    result = filter_chunks_by_ticker(chunks, None)
    assert len(result) == 2


def test_filter_chunks_by_ticker_missing_ticker_field():
    from app.domain.retrieval import filter_chunks_by_ticker
    c = RetrievedChunk(
        chunk_id="1", document_id="d1", content="x",
        page_number=None, chunk_index=0, score=0.5, source="vector",
    )
    result = filter_chunks_by_ticker([c], "AAPL")
    assert result == []


def test_filter_expanded_to_single_ticker():
    from app.domain.coverage import filter_expanded_to_single_ticker
    chunks = [
        _make_chunk_with_ticker("1", "AAPL"),
        _make_chunk_with_ticker("2", "MSFT"),
    ]
    result = filter_expanded_to_single_ticker(chunks, "AAPL")
    assert len(result) == 1
    assert result[0].chunk_id == "1"


def test_filter_expanded_to_single_ticker_none():
    from app.domain.coverage import filter_expanded_to_single_ticker
    chunks = [
        _make_chunk_with_ticker("1", "AAPL"),
        _make_chunk_with_ticker("2", "MSFT"),
    ]
    result = filter_expanded_to_single_ticker(chunks, None)
    assert len(result) == 2


def test_filter_expanded_to_single_ticker_empty():
    from app.domain.coverage import filter_expanded_to_single_ticker
    assert filter_expanded_to_single_ticker([], "AAPL") == []
