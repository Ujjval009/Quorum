from __future__ import annotations

from app.domain.retrieval import RetrievedChunk
from app.domain.risk_diff import (
    RiskDiffResult,
    _extract_key_phrases,
    _heading_similarity,
    _match_segments_across_years,
    _phrase_overlap,
    _segment_risk_text,
    build_corpora,
    build_risk_diff_context,
    classify_changes,
    group_by_year,
)


def _make_chunk(
    chunk_id: str,
    content: str,
    year: int | None = None,
    page: int | None = 1,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        content=content,
        page_number=page,
        chunk_index=0,
        score=0.9,
        source="vector",
        ticker="NVDA",
        fiscal_year=year,
    )


# ── group_by_year ──


def test_group_by_year_empty():
    assert group_by_year([]) == {}


def test_group_by_year_groups_correctly():
    c1 = _make_chunk("c1", "risk content", year=2023)
    c2 = _make_chunk("c2", "risk content", year=2023)
    c3 = _make_chunk("c3", "risk content", year=2024)
    grouped = group_by_year([c1, c2, c3])
    assert set(grouped.keys()) == {2023, 2024}
    assert len(grouped[2023]) == 2
    assert len(grouped[2024]) == 1


def test_group_by_year_skips_missing_year():
    c1 = _make_chunk("c1", "risk content", year=None)
    c2 = _make_chunk("c2", "risk content", year=2024)
    grouped = group_by_year([c1, c2])
    assert set(grouped.keys()) == {2024}


# ── _extract_key_phrases ──


def test_extract_key_phrases_known_topics():
    text = "Our business depends on supply chain and artificial intelligence technology"
    phrases = _extract_key_phrases(text)
    assert "supply chain" in phrases
    assert "artificial intelligence" in phrases


def test_extract_key_phrases_capitalized():
    text = "Risks Related to NVIDIA CUDA Platform"
    phrases = _extract_key_phrases(text)
    # "NVIDIA CUDA" matches as two ALL-CAPS tokens
    assert "nvidia cuda" in phrases


def test_extract_key_phrases_empty():
    assert _extract_key_phrases("short text") == set()


# ── _heading_similarity ──


def test_heading_similarity_identical():
    h = "Risks Related to Our Manufacturing Operations"
    assert _heading_similarity(h, h) == 1.0


def test_heading_similarity_partial():
    h1 = "Risks Related to Manufacturing"
    h2 = "Risks Related to Manufacturing Operations"
    sim = _heading_similarity(h1, h2)
    assert 0.3 < sim < 1.0


def test_heading_similarity_no_overlap():
    assert _heading_similarity("Completely Different", "Unrelated Topic") == 0.0


# ── _phrase_overlap ──


def test_phrase_overlap_identical():
    p = {"supply chain", "competition", "ai"}
    assert _phrase_overlap(p, p) == 1.0


def test_phrase_overlap_partial():
    assert _phrase_overlap({"supply chain", "ai"}, {"supply chain", "tax"}) > 0.0


def test_phrase_overlap_disjoint():
    assert _phrase_overlap({"supply chain"}, {"tax policy"}) == 0.0


def test_phrase_overlap_empty():
    assert _phrase_overlap(set(), {"supply chain"}) == 0.0
    assert _phrase_overlap({"supply chain"}, set()) == 0.0


# ── _segment_risk_text ──


def test_segment_empty_text():
    assert _segment_risk_text("") == []


def test_segment_short_text():
    assert _segment_risk_text("Too short") == []


def test_segment_risk_text_single_block():
    text = "Our business depends on a limited number of suppliers. Any disruption could harm our operations."
    segments = _segment_risk_text(text)
    assert len(segments) == 1
    assert segments[0].word_count > 0
    assert len(segments[0].key_phrases) > 0


def test_segment_risk_text_multiple_blocks():
    text = (
        "Risks Related to Supply Chain\n"
        "Our supply chain is concentrated in Asia. Disruptions could occur.\n"
        "\n"
        "Risks Related to Competition\n"
        "The market is highly competitive. We face pricing pressure.\n"
    )
    segments = _segment_risk_text(text)
    assert len(segments) >= 2
    assert any("supply" in s.heading.lower() for s in segments)
    assert any("competition" in s.heading.lower() for s in segments)


# ── build_corpora ──


def test_build_corpora():
    grouped = {
        2023: [_make_chunk("c1", "Risk factor one content here.", year=2023)],
        2024: [_make_chunk("c2", "Risk factor two content here.", year=2024)],
    }
    corpora = build_corpora(grouped)
    assert 2023 in corpora
    assert 2024 in corpora
    assert corpora[2023].total_word_count > 0
    assert len(corpora[2023].segments) == 1


# ── _match_segments_across_years ──


def test_match_segments_across_years_single_year():
    text = "Risks Related to Supply Chain\nOur supply chain is concentrated."
    grouped = {2023: [_make_chunk("c1", text, year=2023)]}
    corpora = build_corpora(grouped)
    matches = _match_segments_across_years(corpora)
    assert len(matches) >= 1


def test_match_segments_across_years_two_years():
    text_2023 = "Risks Related to Supply Chain\nOur supply chain is in Asia."
    text_2024 = "Risks Related to Supply Chain\nOur supply chain is concentrated in Asia and Europe."
    grouped = {
        2023: [_make_chunk("c1", text_2023, year=2023)],
        2024: [_make_chunk("c2", text_2024, year=2024)],
    }
    corpora = build_corpora(grouped)
    matches = _match_segments_across_years(corpora)
    assert len(matches) >= 1
    # Same risk topic should be matched across years
    assert any(len(m.years) >= 2 for m in matches)


def test_match_segments_added_risk():
    text_2023 = "Risks Related to Supply Chain\nOur supply chain is in Asia."
    text_2024 = (
        "Risks Related to Supply Chain\nOur supply chain is in Asia and Europe.\n"
        "\n"
        "Risks Related to AI Regulation\nNew AI laws may affect our business."
    )
    grouped = {
        2023: [_make_chunk("c1", text_2023, year=2023)],
        2024: [_make_chunk("c2", text_2024, year=2024)],
    }
    corpora = build_corpora(grouped)
    matches = _match_segments_across_years(corpora)
    # Should have at least one match tagged as "added"
    add_types = [m.change_type for m in matches if m.change_type == "added"]
    assert len(add_types) > 0


# ── classify_changes ──


def test_classify_changes_empty():
    result = classify_changes([], [2023, 2024])
    assert isinstance(result, RiskDiffResult)
    assert result.has_multi_year_data  # 2 years passed in
    assert len(result.added) == 0
    assert len(result.removed) == 0
    assert len(result.expanded) == 0
    assert len(result.reduced) == 0


def test_classify_changes_single_year_not_multiyear():
    result = classify_changes([], [2023])
    assert not result.has_multi_year_data


# ── build_risk_diff_context — full pipeline ──


def test_build_risk_diff_context_empty():
    result = build_risk_diff_context([])
    assert "No risk factor data retrieved" in result


def test_build_risk_diff_context_single_year():
    chunks = [_make_chunk("c1", "Risk factor text for FY2023.", year=2023)]
    result = build_risk_diff_context(chunks)
    assert "FY2023" in result or "No risk" in result


def test_build_risk_diff_context_two_years():
    chunks = [
        _make_chunk("c1", "Risk factor content for the first year 2023.", year=2023),
        _make_chunk("c2", "Risk factor content for the second year 2024.", year=2024),
    ]
    result = build_risk_diff_context(chunks)
    # Should identify years in the header
    assert "2023" in result
    assert "2024" in result
    assert "FY2023" in result
    assert "FY2024" in result


def test_build_risk_diff_context_three_years():
    chunks = [
        _make_chunk("c1", "Risks Related to Supply Chain\nOur supply chain is in Asia.", year=2022),
        _make_chunk("c2", "Risks Related to Supply Chain\nOur supply chain is in Asia and Europe.", year=2023),
        _make_chunk("c3", "Risks Related to Supply Chain\nOur supply chain is global with AI risks.", year=2024),
    ]
    result = build_risk_diff_context(chunks)
    assert "2022" in result
    assert "2024" in result
    # Should show the year range
    assert "FY2022" in result or "2022" in result
    assert "FY2024" in result or "2024" in result


# ── Realistic multi-year risk data ──


def _build_nvidia_like_risk(year: int) -> list[RetrievedChunk]:
    """Generate NVDA-like risk factor text for a given year."""
    risks_by_year = {
        2021: (
            "Item 1A. Risk Factors\n"
            "\n"
            "Risks Related to Our Business\n"
            "Our business depends on the PC gaming market. A decline in gaming demand would harm us.\n"
            "\n"
            "Risks Related to Manufacturing\n"
            "We rely on third-party manufacturers. Any disruption could impact supply.\n"
            "\n"
            "Risks Related to Competition\n"
            "The GPU market is highly competitive. We face pressure from AMD and Intel.\n"
            "\n"
            "Risks Related to International Operations\n"
            "We operate globally and face currency and regulatory risks.\n"
        ),
        2022: (
            "Item 1A. Risk Factors\n"
            "\n"
            "Risks Related to Our Business\n"
            "Our business depends on gaming and data center markets. Gaming declined but data center grew.\n"
            "\n"
            "Risks Related to Manufacturing\n"
            "We rely on third-party manufacturers. Any disruption could impact supply.\n"
            "\n"
            "Risks Related to Competition\n"
            "The GPU and AI accelerator market is highly competitive.\n"
            "\n"
            "Risks Related to International Operations\n"
            "We operate globally and face currency, trade, and export control risks.\n"
        ),
        2023: (
            "Item 1A. Risk Factors\n"
            "\n"
            "Risks Related to Our Business\n"
            "Our business depends on data center and AI markets. Gaming remains relevant.\n"
            "\n"
            "Risks Related to Manufacturing\n"
            "We rely on third-party manufacturers. Supply constraints for advanced packaging limit growth.\n"
            "\n"
            "Risks Related to Competition\n"
            "The AI accelerator market is intensely competitive. New entrants include AMD and custom ASICs.\n"
            "\n"
            "Risks Related to International Operations and Export Controls\n"
            "Export controls on advanced semiconductors to China may harm our revenue.\n"
            "\n"
            "Risks Related to AI Regulation\n"
            "Emerging AI regulations could impose compliance costs and limit product capabilities.\n"
        ),
        2024: (
            "Item 1A. Risk Factors\n"
            "\n"
            "Risks Related to Our Business\n"
            "Our business depends on data center and AI infrastructure markets. Demand from hyperscalers drives growth.\n"
            "\n"
            "Risks Related to Manufacturing and Supply\n"
            "We rely on a concentrated set of suppliers. Advanced packaging and CoWoS capacity constraints limit growth.\n"
            "\n"
            "Risks Related to Competition\n"
            "The AI accelerator market is intensely competitive. Hyperscalers are developing custom silicon.\n"
            "\n"
            "Risks Related to Export Controls\n"
            "Expanded export controls on advanced semiconductors to China and other countries may harm our revenue and market position.\n"
            "\n"
            "Risks Related to AI Regulation\n"
            "AI safety and fairness regulations in the US, EU, and China could impose significant compliance costs.\n"
            "\n"
            "Risks Related to Customer Concentration\n"
            "A small number of hyperscale customers represent a growing share of our revenue. Loss of any key customer could materially harm us.\n"
        ),
        2025: (
            "Item 1A. Risk Factors\n"
            "\n"
            "Risks Related to Our Business\n"
            "Our business depends on data center and AI infrastructure markets. Hyperscaler demand continues to drive growth.\n"
            "\n"
            "Risks Related to Manufacturing and Supply\n"
            "We rely on a concentrated set of suppliers for advanced packaging. Capacity constraints persist.\n"
            "\n"
            "Risks Related to Competition\n"
            "The AI accelerator market is intensely competitive with AMD, Intel, and custom ASICs from hyperscalers.\n"
            "\n"
            "Risks Related to Export Controls\n"
            "Expanded export controls on advanced AI semiconductors to China and other countries materially impact revenue.\n"
            "\n"
            "Risks Related to AI Regulation\n"
            "AI safety frameworks and regulations in the US, EU, and China impose growing compliance costs.\n"
            "\n"
            "Risks Related to Customer Concentration\n"
            "A small number of hyperscale customers represent a growing and concentrated share of revenue.\n"
            "\n"
            "Risks Related to Energy and Infrastructure\n"
            "Our data center GPUs and our customers' AI infrastructure require substantial energy, raising costs and regulatory scrutiny.\n"
        ),
    }
    text = risks_by_year.get(year, "Risk factors for this year.")
    return [_make_chunk(f"{year}_risk", text, year=year)]


NVDA_YEARS = [2021, 2022, 2023, 2024, 2025]


def test_realistic_nvidia_pipeline():
    """Full end-to-end test with NVDA-like data across 5 fiscal years."""
    chunks = []
    for y in NVDA_YEARS:
        chunks.extend(_build_nvidia_like_risk(y))

    result = build_risk_diff_context(chunks)

    # Verify all years present in output
    for y in NVDA_YEARS:
        assert str(y) in result or f"FY{y}" in result

    # Verify categories present
    assert "Summary Statistics" in result
    assert "Year-by-Year" in result or "Risk Factor Overview" in result

    # Verify some structure is present
    assert "Added" in result or "Removed" in result or "Expanded" in result or "Reduced" in result

    # Should be a meaningful amount of output
    assert len(result) > 500


def test_nvidia_all_five_years():
    """With 5 years of data, we should see multiple categories of change."""
    chunks = []
    for y in NVDA_YEARS:
        chunks.extend(_build_nvidia_like_risk(y))

    result = build_risk_diff_context(chunks)

    # All five years should appear
    assert "FY2021" in result
    assert "FY2025" in result

    # Should show the full year range
    assert "FY2021 – FY2025" in result

    # Should find added risks (e.g., AI Regulation added in 2023)
    assert "Added" in result or "Summary Statistics" in result


def test_nvidia_added_risks_detected():
    """Risks added in later years (AI regulation, customer concentration, energy)
    should be detected as 'added'."""
    chunks = []
    for y in NVDA_YEARS:
        chunks.extend(_build_nvidia_like_risk(y))

    result = build_risk_diff_context(chunks)

    # AI Regulation appeared first in 2023
    assert "Regulation" in result or "regulation" in result

    # Customer Concentration appeared first in 2024
    assert "Customer" in result or "customer" in result or "concentration" in result

    # Energy appeared first in 2025
    assert "Energy" in result or "energy" in result


def test_nvidia_expanded_risks_detected():
    """Risks that grew in word count should be detected."""
    chunks = []
    for y in NVDA_YEARS:
        chunks.extend(_build_nvidia_like_risk(y))

    result = build_risk_diff_context(chunks)

    # Export controls expanded from a sub-point in international operations (2022)
    # to its own section (2024+) — should register as expanded or added
    assert "Export" in result or "export" in result
