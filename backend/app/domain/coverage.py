from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.logging import logger
from app.domain.retrieval import (
    COMPANY_TICKER_MAP,
    RetrievedChunk,
    detect_tickers,
    hybrid_search,
)

_METRIC_KEYWORDS_BY_INTENT: dict[str, set[str]] = {
    "revenue_mix": {
        "revenue", "sales", "net sales", "product", "category",
        "iphone", "mac", "ipad", "services", "wearables",
    },
    "financial_metrics": {
        "revenue", "income", "margin", "eps", "cash flow",
        "operating", "net income", "gross margin",
    },
    "company_comparison": {
        "revenue", "growth", "income", "margin", "segment",
        "cloud", "aws", "azure",
    },
    "business_segment": {
        "segment revenue", "segment profit", "cloud",
        "aws", "azure", "data center",
    },
    "risk_factor_diff": {
        "risk factor", "item 1a", "risk disclosure",
    },
    "ai_disclosure": {
        "ai", "artificial intelligence", "machine learning",
    },
}

_INTENTS_REQUIRING_NUMERICAL = {
    "revenue_mix", "financial_metrics", "company_comparison", "business_segment",
}


@dataclass
class CoverageReport:
    required_tickers: list[str] = field(default_factory=list)
    required_years: list[int] = field(default_factory=list)
    required_metrics: list[str] = field(default_factory=list)
    retrieved_tickers: set[str] = field(default_factory=set)
    retrieved_years: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    retrieved_metrics: set[str] = field(default_factory=set)
    missing_tickers: list[str] = field(default_factory=list)
    missing_years: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    evaluated: bool = False
    has_gaps: bool = False
    gap_description: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.retrieved_years, dict):
            self.retrieved_years = defaultdict(set, self.retrieved_years)
        if isinstance(self.missing_years, dict):
            self.missing_years = defaultdict(list, self.missing_years)


def _infer_required_years(chunks: list[RetrievedChunk], query: str) -> list[int]:
    """Infer which fiscal years are likely needed from the query and available data."""
    years_present: set[int] = set()
    for c in chunks:
        if c.fiscal_year:
            years_present.add(c.fiscal_year)

    query_lower = query.lower()
    year_patterns = re.findall(r"\b(20\d{2})\b", query_lower)
    if year_patterns:
        return sorted(int(y) for y in year_patterns)

    if not years_present:
        return []

    sorted_years = sorted(years_present, reverse=True)
    if any(w in query_lower for w in ["last 3", "last three", "3 year", "three year", "multi.year"]):
        return sorted_years[:3]
    if any(w in query_lower for w in ["last 2", "last two", "2 year", "two year", "yoy", "year over year"]):
        return sorted_years[:2]
    return sorted_years


def _infer_required_metrics(intent: str) -> list[str]:
    return list(_METRIC_KEYWORDS_BY_INTENT.get(intent, set()))


def _infer_required_tickers(query: str, intent: str) -> list[str]:
    found = detect_tickers(query)
    if found:
        return found
    for name, ticker in COMPANY_TICKER_MAP.items():
        if re.search(r"\b" + re.escape(name) + r"\b", query.lower()):
            if ticker not in found:
                found.append(ticker)
    return found


def validate_coverage(
    query: str,
    chunks: list[RetrievedChunk],
    intent: str,
) -> CoverageReport:
    required_tickers = _infer_required_tickers(query, intent)
    required_years = _infer_required_years(chunks, query)
    required_metrics = _infer_required_metrics(intent)

    retrieved_tickers: set[str] = set()
    retrieved_years: dict[str, set[int]] = defaultdict(set)
    retrieved_metrics: set[str] = set()

    for c in chunks:
        if c.ticker:
            retrieved_tickers.add(c.ticker.upper())
            if c.fiscal_year:
                retrieved_years[c.ticker.upper()].add(c.fiscal_year)
        if c.section_title:
            retrieved_metrics.add(c.section_title.lower())

    missing_tickers: list[str] = []
    missing_years: dict[str, list[int]] = defaultdict(list)

    for ticker in required_tickers:
        if ticker not in retrieved_tickers:
            missing_tickers.append(ticker)
        else:
            for y in required_years:
                if y not in retrieved_years.get(ticker, set()):
                    missing_years[ticker].append(y)

    gap_parts: list[str] = []
    if missing_tickers:
        gap_parts.append(f"Missing companies: {', '.join(missing_tickers)}")
    if missing_years:
        for ticker, years in missing_years.items():
            gap_parts.append(f"{ticker} missing years: {', '.join(str(y) for y in years)}")

    has_gaps = bool(missing_tickers) or bool(missing_years)
    requires_numerical = intent in _INTENTS_REQUIRING_NUMERICAL

    if requires_numerical and not chunks:
        has_gaps = True
        gap_parts.append("No chunks retrieved")

    report = CoverageReport(
        required_tickers=required_tickers,
        required_years=required_years,
        required_metrics=required_metrics,
        retrieved_tickers=retrieved_tickers,
        retrieved_years=dict(retrieved_years),
        retrieved_metrics=retrieved_metrics,
        missing_tickers=missing_tickers,
        missing_years=dict(missing_years),
        evaluated=True,
        has_gaps=has_gaps,
        gap_description="; ".join(gap_parts),
    )

    logger.info(
        "Coverage validated",
        query=query[:80],
        intent=intent,
        has_gaps=has_gaps,
        gap_description=report.gap_description,
    )
    return report


def expand_coverage(
    query: str,
    chunks: list[RetrievedChunk],
    coverage: CoverageReport,
    intent: str,
    db: Session,
) -> list[RetrievedChunk]:
    """Expand retrieval to fill coverage gaps and return augmented chunk list."""
    if not coverage.has_gaps:
        return chunks

    existing_ids = {c.chunk_id for c in chunks}
    new_chunks: list[RetrievedChunk] = []

    for ticker in coverage.missing_tickers:
        logger.info("Expanding coverage for missing ticker", ticker=ticker)
        expanded = hybrid_search(
            query=f"{ticker} {query}",
            db=db,
            top_k=25,
            ticker=ticker,
            search_depth=50,
        )
        for c in expanded:
            if c.chunk_id not in existing_ids:
                existing_ids.add(c.chunk_id)
                new_chunks.append(c)

    for ticker, years in coverage.missing_years.items():
        logger.info("Expanding coverage for missing years", ticker=ticker, years=years)
        for year in years:
            expanded = hybrid_search(
                query=f"{ticker} {year} 10-K annual report financial results",
                db=db,
                top_k=15,
                ticker=ticker,
                search_depth=30,
            )
            for c in expanded:
                if c.chunk_id not in existing_ids:
                    existing_ids.add(c.chunk_id)
                    new_chunks.append(c)

    if not chunks and not new_chunks:
        logger.warning("Coverage expansion produced no additional chunks")
        return chunks

    result = chunks + new_chunks
    logger.info(
        "Coverage expanded",
        original=len(chunks),
        added=len(new_chunks),
        total=len(result),
    )
    return result


def filter_expanded_to_single_ticker(
    chunks: list[RetrievedChunk],
    ticker: str,
) -> list[RetrievedChunk]:
    """Ensure all expanded chunks belong to the requested ticker.

    Safety guard: if expansion inadvertently pulled chunks from other
    companies, filter them out. Preserves comparison workflow by only
    applying when a single target ticker is given.
    """
    if not ticker:
        return chunks
    ticker_upper = ticker.upper()
    return [c for c in chunks if c.ticker and c.ticker.upper() == ticker_upper]
