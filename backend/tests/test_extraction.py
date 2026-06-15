from __future__ import annotations

from app.domain.extraction import (
    FactSet,
    FinancialFact,
    MetricCategory,
    SEGMENT_REGISTRY,
    compute_cagr,
    compute_growth_rates,
    compute_revenue_shares,
    extract_facts,
    format_structured_context,
)
from app.domain.retrieval import RetrievedChunk


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_absolute_fact(
    ticker: str,
    year: int,
    metric: str,
    value: float,
    segment: str | None = None,
) -> FinancialFact:
    return FinancialFact(
        ticker=ticker,
        fiscal_year=year,
        metric_name=metric,
        value=value,
        metric_category=MetricCategory.ABSOLUTE,
        is_segment=bool(segment),
        segment_name=segment,
    )


def _make_share_fact(
    ticker: str,
    year: int,
    metric: str,
    value: float,
    segment: str | None = None,
) -> FinancialFact:
    return FinancialFact(
        ticker=ticker,
        fiscal_year=year,
        metric_name=metric,
        value=value,
        metric_category=MetricCategory.SHARE,
        is_segment=bool(segment),
        segment_name=segment,
    )


# ── MetricCategory sanity ────────────────────────────────────────────────────

def test_metric_category_has_all_types():
    assert MetricCategory.ABSOLUTE is not None
    assert MetricCategory.SHARE is not None
    assert MetricCategory.GROWTH is not None
    assert MetricCategory.CAGR is not None


def test_financial_fact_default_category_is_absolute():
    fact = FinancialFact(ticker="AAPL", fiscal_year=2023, metric_name="Total Revenue", value=100.0)
    assert fact.metric_category == MetricCategory.ABSOLUTE


# ── compute_revenue_shares ───────────────────────────────────────────────────

def test_compute_shares_basic():
    facts = [
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 60_000, segment="iPhone"),
        _make_absolute_fact("AAPL", 2023, "Revenue: Services", 25_000, segment="Services"),
        _make_absolute_fact("AAPL", 2023, "Revenue: Mac", 15_000, segment="Mac"),
    ]
    fs = FactSet(facts=facts)
    shares = compute_revenue_shares(fs)

    iphone = shares.get("AAPL", "Share: iPhone", 2023)
    services = shares.get("AAPL", "Share: Services", 2023)
    mac = shares.get("AAPL", "Share: Mac", 2023)

    assert iphone is not None
    assert services is not None
    assert mac is not None
    assert iphone.value == 60.0  # 60k/100k = 60%
    assert services.value == 25.0
    assert mac.value == 15.0


def test_compute_shares_sums_to_100():
    facts = [
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 200_000),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 100_000, segment="iPhone"),
        _make_absolute_fact("AAPL", 2023, "Revenue: Services", 70_000, segment="Services"),
        _make_absolute_fact("AAPL", 2023, "Revenue: Mac", 30_000, segment="Mac"),
    ]
    fs = FactSet(facts=facts)
    shares = compute_revenue_shares(fs)
    total_share = sum(f.value for f in shares.facts if f.value is not None)
    assert total_share == 100.0


def test_compute_shares_empty_when_no_total():
    facts = [
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 60_000, segment="iPhone"),
    ]
    fs = FactSet(facts=facts)
    shares = compute_revenue_shares(fs)
    assert len(shares.facts) == 0


def test_compute_shares_skips_total_revenue_itself():
    facts = [
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 60_000, segment="iPhone"),
    ]
    fs = FactSet(facts=facts)
    shares = compute_revenue_shares(fs)
    # Should not create "Share: Total Revenue" or "Share: Total net sales"
    for f in shares.facts:
        assert "Total" not in f.metric_name


def test_compute_shares_marks_category_share():
    facts = [
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 60_000, segment="iPhone"),
    ]
    fs = FactSet(facts=facts)
    shares = compute_revenue_shares(fs)
    for f in shares.facts:
        assert f.metric_category == MetricCategory.SHARE


def test_compute_shares_multiple_years():
    facts = [
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 90_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2022, "Revenue: iPhone", 50_000, segment="iPhone"),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 60_000, segment="iPhone"),
    ]
    fs = FactSet(facts=facts)
    shares = compute_revenue_shares(fs)
    s2022 = shares.get("AAPL", "Share: iPhone", 2022)
    s2023 = shares.get("AAPL", "Share: iPhone", 2023)
    assert s2022 is not None and s2022.value == 55.6  # 50k/90k = 55.555... → 55.6
    assert s2023 is not None and s2023.value == 60.0


# ── compute_growth_rates guards ──────────────────────────────────────────────

def test_growth_excludes_share_metrics():
    """Growth rates on share percentages produce nonsense — must be excluded."""
    facts = [
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 120_000),
        _make_share_fact("AAPL", 2022, "Share: iPhone", 60.0, segment="iPhone"),
        _make_share_fact("AAPL", 2023, "Share: iPhone", 55.0, segment="iPhone"),
    ]
    result = compute_growth_rates(facts)
    metrics = [r["metric"] for r in result]
    assert "Total Revenue" in metrics
    assert "Share: iPhone" not in metrics


def test_growth_only_on_absolute_metrics():
    facts = [
        _make_absolute_fact("AAPL", 2022, "Net Income", 50_000),
        _make_absolute_fact("AAPL", 2023, "Net Income", 55_000),
        _make_share_fact("AAPL", 2022, "Share: iPhone", 60.0),
        _make_share_fact("AAPL", 2023, "Share: iPhone", 55.0),
    ]
    result = compute_growth_rates(facts)
    assert len(result) == 1
    assert result[0]["metric"] == "Net Income"


def test_growth_correct_value():
    facts = [
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 120_000),
    ]
    result = compute_growth_rates(facts)
    assert len(result) == 1
    gr = result[0]["growth_rates"]
    assert len(gr) == 1
    assert gr[0]["growth_pct"] == 20.0  # (120k - 100k) / 100k


# ── compute_cagr guards ──────────────────────────────────────────────────────

def test_cagr_excludes_share_metrics():
    facts = [
        _make_absolute_fact("AAPL", 2021, "Total Revenue", 80_000),
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 120_000),
        _make_share_fact("AAPL", 2021, "Share: iPhone", 60.0),
        _make_share_fact("AAPL", 2022, "Share: iPhone", 58.0),
        _make_share_fact("AAPL", 2023, "Share: iPhone", 55.0),
    ]
    result = compute_cagr(facts)
    metrics = [r["metric"] for r in result]
    assert "Total Revenue" in metrics
    assert "Share: iPhone" not in metrics


def test_cagr_only_on_absolute_metrics():
    facts = [
        _make_absolute_fact("AAPL", 2021, "Net Income", 40_000),
        _make_absolute_fact("AAPL", 2022, "Net Income", 50_000),
        _make_absolute_fact("AAPL", 2023, "Net Income", 60_000),
        _make_share_fact("AAPL", 2021, "Share: iPhone", 60.0),
        _make_share_fact("AAPL", 2022, "Share: iPhone", 58.0),
        _make_share_fact("AAPL", 2023, "Share: iPhone", 55.0),
    ]
    result = compute_cagr(facts)
    assert len(result) == 1
    assert result[0]["metric"] == "Net Income"


# ── format_structured_context separation ─────────────────────────────────────

def test_format_includes_revenue_mix_section():
    """Revenue Mix (%) section must exist when share facts are present."""
    facts = [
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 60_000, segment="iPhone"),
    ]
    fs = FactSet(facts=facts + compute_revenue_shares(FactSet(facts=facts)).facts)
    output = format_structured_context(fs, "revenue_mix")
    assert "Revenue Mix" in output
    assert "Revenue by Category" in output


def test_format_revenue_mix_uses_percent_sign():
    """Revenue Mix values should use % formatting, not $."""
    facts = [
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 60_000, segment="iPhone"),
    ]
    fs = FactSet(facts=facts + compute_revenue_shares(FactSet(facts=facts)).facts)
    output = format_structured_context(fs, "revenue_mix")
    assert "60.0%" in output


def test_format_no_growth_in_revenue_mix_intent():
    """Revenue mix intent should not show growth-rate or CAGR sections
    (those belong in financial_metrics intent)."""
    facts = [
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 120_000),
        _make_absolute_fact("AAPL", 2022, "Revenue: iPhone", 60_000, segment="iPhone"),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 65_000, segment="iPhone"),
    ]
    fs = FactSet(facts=facts)
    growth = compute_growth_rates(fs.facts)
    cagr = compute_cagr(fs.facts)
    output = format_structured_context(fs, "revenue_mix", growth, cagr)
    assert "Year-over-Year Growth" not in output
    assert "Compound Annual Growth Rate" not in output


def test_format_growth_in_financial_metrics_intent():
    """Financial metrics intent MUST include growth and CAGR."""
    facts = [
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 120_000),
    ]
    fs = FactSet(facts=facts)
    growth = compute_growth_rates(fs.facts)
    cagr = compute_cagr(fs.facts)
    output = format_structured_context(fs, "financial_metrics", growth, cagr)
    assert "Year-over-Year Growth" in output
    assert "CAGR" in output


def test_format_growth_in_company_comparison_intent():
    """Company comparison intent includes revenue mix AND growth."""
    facts = [
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 120_000),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 65_000, segment="iPhone"),
    ]
    fs = FactSet(facts=facts + compute_revenue_shares(FactSet(facts=facts)).facts)
    growth = compute_growth_rates(fs.facts)
    cagr = compute_cagr(fs.facts)
    output = format_structured_context(fs, "company_comparison", growth, cagr)
    assert "Revenue Mix" in output
    assert "Revenue by Category" in output
    assert "Year-over-Year Growth" in output


def test_format_growth_section_has_no_share_metrics():
    """The growth-rate output must never contain share metrics."""
    facts = [
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 120_000),
        _make_share_fact("AAPL", 2022, "Share: iPhone", 60.0),
        _make_share_fact("AAPL", 2023, "Share: iPhone", 55.0),
    ]
    growth = compute_growth_rates(facts)
    assert all("Share:" not in r["metric"] for r in growth)


def test_format_cagr_section_has_no_share_metrics():
    """The CAGR output must never contain share metrics."""
    facts = [
        _make_absolute_fact("AAPL", 2021, "Total Revenue", 80_000),
        _make_absolute_fact("AAPL", 2022, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 120_000),
        _make_share_fact("AAPL", 2021, "Share: iPhone", 60.0),
        _make_share_fact("AAPL", 2022, "Share: iPhone", 58.0),
        _make_share_fact("AAPL", 2023, "Share: iPhone", 55.0),
    ]
    cagr = compute_cagr(facts)
    assert all("Share:" not in r["metric"] for r in cagr)


# ── FactSet category helpers ─────────────────────────────────────────────────

def test_facts_by_category_filters_correctly():
    abs_fact = _make_absolute_fact("AAPL", 2023, "Total Revenue", 100_000)
    share_fact = _make_share_fact("AAPL", 2023, "Share: iPhone", 60.0)
    fs = FactSet(facts=[abs_fact, share_fact])
    assert len(fs.facts_by_category(MetricCategory.ABSOLUTE)) == 1
    assert len(fs.facts_by_category(MetricCategory.SHARE)) == 1
    assert len(fs.facts_by_category(MetricCategory.GROWTH)) == 0


def test_metrics_by_category():
    facts = [
        _make_absolute_fact("AAPL", 2023, "Total Revenue", 100_000),
        _make_absolute_fact("AAPL", 2023, "Revenue: iPhone", 60_000),
        _make_share_fact("AAPL", 2023, "Share: iPhone", 60.0),
    ]
    fs = FactSet(facts=facts)
    absolute_metrics = fs.metrics_by_category(MetricCategory.ABSOLUTE)
    share_metrics = fs.metrics_by_category(MetricCategory.SHARE)
    assert "Total Revenue" in absolute_metrics
    assert "Revenue: iPhone" in absolute_metrics
    assert "Share: iPhone" in share_metrics
    assert "Share: iPhone" not in absolute_metrics


# ── Segment registry ─────────────────────────────────────────────────────────

def test_segment_registry_has_cloud_providers():
    assert "AMZN" in SEGMENT_REGISTRY
    assert "MSFT" in SEGMENT_REGISTRY
    assert "GOOGL" in SEGMENT_REGISTRY
    assert "NVDA" in SEGMENT_REGISTRY


def test_segment_registry_entries_have_keywords():
    for ticker, segments in SEGMENT_REGISTRY.items():
        assert len(segments) >= 1
        for name, keywords in segments.items():
            assert len(name) > 0
            assert len(keywords) >= 1
            assert all(len(k) > 0 for k in keywords)


# ── Segment extraction through extract_facts ─────────────────────────────────

def _make_segment_chunk(
    ticker: str, year: int, content: str,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{ticker}-{year}-seg",
        document_id=f"doc-{ticker}",
        content=content,
        page_number=10,
        chunk_index=0,
        score=0.9,
        source="vector",
        ticker=ticker,
        fiscal_year=year,
        section_title="Item 7. Management's Discussion and Analysis",
    )


def test_extract_aws_segment_facts():
    """AWS revenue in table format should be extracted as Revenue: Amazon Web Services (AWS)."""
    chunk = _make_segment_chunk(
        "AMZN", 2023,
        "Revenue by Segment\nAWS  $80,000  $75,000  $70,000\n"
        "eCommerce  $200,000  $190,000  $180,000",
    )
    fs = extract_facts([chunk])
    aws_facts = [f for f in fs.facts if "AWS" in f.metric_name or "Web Services" in f.metric_name]
    assert len(aws_facts) > 0
    assert any(f.value == 80_000 for f in aws_facts)
    assert all(f.is_segment for f in aws_facts)


def test_extract_azure_segment_facts():
    """Azure/Intelligent Cloud revenue should be extracted."""
    chunk = _make_segment_chunk(
        "MSFT", 2024,
        "Intelligent Cloud revenue $60,000 $55,000 $50,000\n"
        "Azure services $40,000 $35,000 $30,000",
    )
    fs = extract_facts([chunk])
    cloud_facts = [f for f in fs.facts if "Azure" in f.metric_name or "Intelligent Cloud" in f.metric_name]
    assert len(cloud_facts) > 0
    assert all(f.is_segment for f in cloud_facts)


def test_extract_google_cloud_segment_facts():
    """Google Cloud revenue should be extracted."""
    chunk = _make_segment_chunk(
        "GOOGL", 2023,
        "Google Cloud  $30,000  $25,000  $20,000\n"
        "Google Advertising  $200,000  $180,000  $160,000",
    )
    fs = extract_facts([chunk])
    cloud_facts = [f for f in fs.facts if "Google Cloud" in f.metric_name or "gcp" in f.metric_name.lower()]
    assert len(cloud_facts) > 0
    assert all(f.is_segment for f in cloud_facts)


def test_extract_segment_facts_rejects_narrative():
    """Segment keywords in narrative text (not table rows) should NOT be extracted."""
    chunk = _make_segment_chunk(
        "AMZN", 2023,
        "AWS revenue was $80,000 for the fiscal year, compared to $75,000 last year.",
    )
    fs = extract_facts([chunk])
    aws_facts = [f for f in fs.facts if "AWS" in f.metric_name or "Web Services" in f.metric_name]
    assert len(aws_facts) == 0


def test_extract_segment_facts_unknown_ticker():
    """Tickers not in SEGMENT_REGISTRY should not produce segment facts."""
    chunk = _make_segment_chunk(
        "UNKNOWN", 2023,
        "Cloud revenue $80,000",
    )
    fs = extract_facts([chunk])
    segment_facts = [f for f in fs.facts if f.is_segment]
    assert len(segment_facts) == 0


def test_extract_segment_facts_does_not_duplicate_apple_categories():
    """AAPL segments are handled by CATEGORY_ORDER, not SEGMENT_REGISTRY."""
    chunk = _make_segment_chunk(
        "AAPL", 2023,
        "iPhone $200,000 Mac $50,000",
    )
    fs = extract_facts([chunk])
    # AAPL is NOT in SEGMENT_REGISTRY, so no duplicate segment extraction
    # (only the CATEGORY_ORDER-based parsing would work, but that requires
    # the 'net sales by category' trigger phrase)
    segment_from_registry = [f for f in fs.facts if f.is_segment and "Web Services" in f.metric_name]
    assert len(segment_from_registry) == 0
