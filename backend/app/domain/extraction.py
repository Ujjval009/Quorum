from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from app.core.logging import logger
from app.domain.retrieval import RetrievedChunk


class MetricCategory(Enum):
    ABSOLUTE = auto()   # Dollar amounts ($M) — e.g., revenue, net income
    SHARE = auto()      # Percentage of total (%) — e.g., iPhone share of revenue
    GROWTH = auto()     # Year-over-year growth rate (%) — computed
    CAGR = auto()       # Compound annual growth rate (%) — computed

_FINANCIAL_VALUE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)"
    r"|(?<!\d)([\d,]{4,})(?:\.\d+)?(?!(?:\s*%|\s*\)\s*%|[.-]|\s*\)))"
)

_YEAR_LIKE = range(1900, 2100)

_YEAR_HEADER = re.compile(r"(?:for\s+)?(\d{4})\s+(?:Change|change|-\s*Change)\s+(\d{4})\s+(?:Change|change)\s+(\d{4})")

_KNOWN_LINE_ITEMS: dict[str, list[str]] = {
    "Total Revenue": [
        "total net sales", "total revenues", "total revenue",
        "net sales", "revenues", "revenue",
    ],
    "Gross Margin": [
        "total gross margin", "gross margin",
    ],
    "Operating Income": [
        "operating income", "income from operations",
    ],
    "Net Income": [
        "net income", "net earnings",
    ],
    "Diluted EPS": [
        "diluted earnings per share", "diluted net income per share",
        "diluted eps", "earnings per share — diluted",
    ],
    "Cost of Revenue": [
        "cost of revenue", "cost of sales", "cost of goods sold",
    ],
    "R&D Expense": [
        "research and development", "research & development", "r&d expense",
    ],
    "SG&A": [
        "selling, general and administrative", "selling general and administrative",
        "sga expense",
    ],
    "Total Operating Expenses": [
        "total operating expenses", "total operating expense",
    ],
    "Operating Cash Flow": [
        "net cash provided by operating activities",
        "net cash from operating activities",
    ],
}

CATEGORY_ORDER = [
    "iPhone", "Mac", "iPad", "Wearables, Home and Accessories",
    "Services", "Total net sales",
]

# Ticker-specific segment revenue names for flexible extraction.
# Each entry maps a segment display name to search keywords that
# precede dollar amounts in 10-K Item 7 revenue breakdowns.
SEGMENT_REGISTRY: dict[str, dict[str, list[str]]] = {
    "AMZN": {
        "Amazon Web Services (AWS)": [
            "aws", "amazon web services",
            "aws revenue", "amazon web services revenue",
            "aws segment", "web services segment",
        ],
    },
    "MSFT": {
        "Intelligent Cloud (Azure)": [
            "azure", "intelligent cloud",
            "intelligent cloud revenue",
            "intelligent cloud segment",
        ],
    },
    "GOOGL": {
        "Google Cloud": [
            "google cloud", "gcp",
            "google cloud revenue",
            "google cloud segment",
        ],
    },
    "NVDA": {
        "Data Center": [
            "data center", "datacenter",
            "data center revenue",
            "compute & networking",
        ],
    },
}


@dataclass
class FinancialFact:
    ticker: str
    fiscal_year: int
    metric_name: str
    value: float | None
    metric_category: MetricCategory = MetricCategory.ABSOLUTE
    source_chunk_id: str | None = None
    section_title: str | None = None
    is_segment: bool = False
    segment_name: str | None = None

    @property
    def citation_label(self) -> str:
        parts = [self.ticker, f"FY{self.fiscal_year}"]
        if self.section_title:
            parts.append(self.section_title)
        return " · ".join(parts)


@dataclass
class FactSet:
    facts: list[FinancialFact] = field(default_factory=list)

    def by_ticker(self) -> dict[str, list[FinancialFact]]:
        d: dict[str, list[FinancialFact]] = defaultdict(list)
        for f in self.facts:
            d[f.ticker].append(f)
        return dict(d)

    def by_metric(self) -> dict[str, list[FinancialFact]]:
        d: dict[str, list[FinancialFact]] = defaultdict(list)
        for f in self.facts:
            d[f.metric_name].append(f)
        return dict(d)

    def by_year(self) -> dict[int, list[FinancialFact]]:
        d: dict[int, list[FinancialFact]] = defaultdict(list)
        for f in self.facts:
            d[f.fiscal_year].append(f)
        return dict(d)

    def get(self, ticker: str, metric: str, year: int) -> FinancialFact | None:
        for f in self.facts:
            if f.ticker == ticker and f.metric_name == metric and f.fiscal_year == year:
                return f
        return None

    def facts_by_category(self, category: MetricCategory) -> list[FinancialFact]:
        return [f for f in self.facts if f.metric_category == category]

    def tickers(self) -> list[str]:
        return sorted({f.ticker for f in self.facts})

    def years(self) -> list[int]:
        return sorted({f.fiscal_year for f in self.facts})

    def metrics(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for f in self.facts:
            if f.metric_name not in seen:
                seen.add(f.metric_name)
                result.append(f.metric_name)
        return result

    def metrics_by_category(self, category: MetricCategory) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for f in self.facts:
            if f.metric_category == category and f.metric_name not in seen:
                seen.add(f.metric_name)
                result.append(f.metric_name)
        return result


def _extract_values(text: str) -> list[float]:
    values: list[float] = []
    for m in _FINANCIAL_VALUE.finditer(text):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        val = float(raw)
        if val >= 1_000:
            # Filter out year numbers (e.g., "2022", "2021") that the bare-number
            # alternative of _FINANCIAL_VALUE falsely matches. Dollar-prefixed
            # values ($26,914) are always genuine financial figures.
            if m.group(1) is None and 1900 <= val <= 2100:
                continue
            values.append(val)
    return values


def _deduplicate_facts(facts: list[FinancialFact]) -> list[FinancialFact]:
    """Deduplicate conflicting facts by preferring the most frequent value.

    For each (ticker, metric_name, fiscal_year), counts occurrences of each
    distinct value and keeps only the value with the highest frequency.  This
    naturally favors correct facts that recur across many financial-table
    chunks over spurious matches from narrative or pro-forma chunks.
    """
    groups: dict[tuple[str, str, int], dict[float | None, int]] = {}
    for f in facts:
        key = (f.ticker, f.metric_name, f.fiscal_year)
        if key not in groups:
            groups[key] = {}
        groups[key][f.value] = groups[key].get(f.value, 0) + 1

    seen: set[tuple[str, str, int]] = set()
    result: list[FinancialFact] = []
    for f in facts:
        key = (f.ticker, f.metric_name, f.fiscal_year)
        if key in seen:
            continue
        counts = groups[key]
        best_value = max(counts, key=lambda v: (counts[v], 0 if v is not None else 1))
        if f.value == best_value:
            seen.add(key)
            result.append(f)
    return result


def _extract_years(text: str) -> list[int] | None:
    # Pattern 1: Standard "2022 Change 2021 Change 2020" (AAPL, MSFT)
    m = _YEAR_HEADER.search(text)
    if m:
        return [int(m.group(1)), int(m.group(2)), int(m.group(3))]

    # Pattern 2: Two-year "2022 Change 2021"
    m2 = re.search(r"(\d{4})\s+Change\s+(\d{4})", text)
    if m2:
        return [int(m2.group(1)), int(m2.group(2))]

    # Pattern 3: "Year Ended <date> <date> $ Change % Change" (NVDA, AMZN)
    m3 = re.search(
        r"Year Ended\s+\w+\s+\d+,\s*(\d{4})\s+\w+\s+\d+,\s*(\d{4})(?:\s+\w+)?\s*\$?\s*Change",
        text, re.IGNORECASE,
    )
    if m3:
        return [int(m3.group(1)), int(m3.group(2))]

    # Pattern 4: "Year Ended <date> $ Change" (single-year summary)
    m4 = re.search(
        r"Year Ended\s+\w+\s+\d+,\s*(\d{4})\s*\$?\s*Change",
        text, re.IGNORECASE,
    )
    if m4:
        return [int(m4.group(1))]

    # Pattern 5: "Fiscal Year 2022 Summary" header with "Year Ended" later
    m5 = re.search(r"Fiscal\s+Year\s+(\d{4})\s+Summary", text, re.IGNORECASE)
    if m5:
        m5b = re.search(
            r"Year Ended\s+\w+\s+\d+,\s*(\d{4})",
            text, re.IGNORECASE,
        )
        if m5b:
            years = {int(m5.group(1)), int(m5b.group(1))}
            return sorted(years, reverse=True)
        return [int(m5.group(1))]

    # Pattern 6: "Year Ended <date> <date> <date>" (cash flow: 3+ years, no Change)
    m6 = re.search(
        r"Year Ended\s+\w+\s+\d+,\s*(\d{4})\s+\w+\s+\d+,\s*(\d{4})(?:\s+\w+\s+\d+,\s*(\d{4}))?",
        text, re.IGNORECASE,
    )
    if m6:
        years = [int(m6.group(1)), int(m6.group(2))]
        if m6.group(3):
            years.append(int(m6.group(3)))
        return years

    # Pattern 7: "(In millions) Year Ended <date> <date>" (Variation without commas)
    m7 = re.search(
        r"\(In millions\)[^)]*Year Ended\s+\w+\s+\d+,\s*(\d{4})\s+\w+\s+\d+,\s*(\d{4})",
        text, re.IGNORECASE,
    )
    if m7:
        return [int(m7.group(1)), int(m7.group(2))]

    # Pattern 8: "Year Ended <date>, <year> <year> <year>" (MSFT format)
    # e.g., "Year ended June 30, 2023 2022 2021"
    m8 = re.search(
        r"Year Ended\s+\w+\s+\d+,\s*((?:\d{4}\s+){1,}\d{4})(?!\s+\w+\s+\d+,)",
        text, re.IGNORECASE,
    )
    if m8:
        years_str = m8.group(1).strip()
        return [int(y) for y in years_str.split()]

    # Pattern 9: Plain year pair with "Percentage Change" (MSFT segment table header)
    m9 = re.search(
        r"(\d{4})\s+(\d{4})\s+Percentage\s+Change",
        text,
    )
    if m9:
        return [int(m9.group(1)), int(m9.group(2))]

    # Pattern 10: Common "Year Ended <date>" + embedded years in the text.
    # Pick up to 3 most-recent-looking 4-digit years near a table header.
    m10 = re.findall(r"\b(20[2-9]\d)\b", text)
    if len(m10) >= 2:
        uniq = sorted(set(int(y) for y in m10), reverse=True)
        return uniq[:3]

    return None


def _parse_revenue_table(
    content: str,
    doc_year: int,
    ticker: str,
    chunk_id: str,
    section_title: str | None,
) -> list[FinancialFact]:
    years = _extract_years(content)
    if not years:
        return []

    # Find the start of the revenue table. Search for the marker phrases
    # that introduce the table (e.g., "Net sales by category:").
    # This prevents content.find() from matching narrative mentions of
    # category names that appear before the actual financial table.
    table_start = 0
    for marker in ("net sales by category", "products and services performance"):
        idx = content.lower().find(marker)
        if idx != -1:
            table_start = idx
            break

    facts: list[FinancialFact] = []
    for cat in CATEGORY_ORDER:
        idx = content.find(cat, table_start)
        if idx == -1:
            continue
        snippet = content[idx:idx + 200]
        values = _extract_values(snippet)
        if len(values) >= len(years):
            for i, y in enumerate(years):
                facts.append(FinancialFact(
                    ticker=ticker,
                    fiscal_year=y,
                    metric_name=f"Revenue: {cat}",
                    value=values[i],
                    metric_category=MetricCategory.ABSOLUTE,
                    source_chunk_id=chunk_id,
                    section_title=section_title,
                    is_segment=True,
                    segment_name=cat,
                ))
    return facts


def _in_table_row(text: str, pos: int) -> bool:
    """Check if the position is within a table-like row.

    A table row contains either pipe characters (markdown table),
    dollar amounts in a row, or a label followed by aligned numbers.
    """
    line_start = text.rfind("\n", 0, pos)
    if line_start == -1:
        line_start = 0
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]

    # Pipe-delimited table row
    if "|" in line:
        return True
    # Multiple dollar signs (tabular dollar amounts)
    if line.count("$") >= 2:
        return True
    # Single $ with 2+ 4-digit numbers in same line
    if "$" in line and len(re.findall(r"\b[\d,]{4,}\b", line)) >= 2:
        return True
    # Bare-number table row: label followed by 2+ comma-separated 4-digit values
    # e.g., "Intelligent Cloud 87,907 74,965 59,728"
    if len(re.findall(r"\b[\d,]{4,}\b", line)) >= 2:
        return True
    return False


def _extract_segment_facts(
    content: str,
    doc_year: int,
    ticker: str,
    chunk_id: str,
    section_title: str | None,
) -> list[FinancialFact]:
    """Extract segment revenue for any ticker using the segment registry.

    Only extracts when the segment keyword appears in a table-like row
    (pipe-delimited, dollar signs, or tabular number layout). This prevents
    false matches from narrative mentions of segment names.
    """
    facts: list[FinancialFact] = []
    segments = SEGMENT_REGISTRY.get(ticker)
    if not segments:
        return facts

    years = _extract_years(content)

    for segment_name, keywords in segments.items():
        for keyword in keywords:
            search_from = 0
            while True:
                idx = content.lower().find(keyword, search_from)
                if idx == -1:
                    break

                # Skip narrative mentions — only extract from table rows
                if not _in_table_row(content, idx):
                    search_from = idx + 1
                    continue

                # Additional guard: the keyword must be followed by a value
                # within 15 chars. Table rows look like "Intelligent Cloud 60,080"
                # (number right after), while narrative says "Intelligent Cloud
                # Revenue increased" (word after). This prevents false matches
                # on long single-line chunks where table data appears later.
                after = content[idx + len(keyword):idx + len(keyword) + 15]
                if not re.match(r"\s*[$]?\s*[\d,(]", after):
                    search_from = idx + 1
                    continue

                # Build a row-limited snippet: from this match to the next
                # segment keyword or next newline.
                next_seg_start = len(content)
                for other_name, other_kws in segments.items():
                    for okw in other_kws:
                        oidx = content.lower().find(okw, idx + 1)
                        if oidx >= 0 and oidx < next_seg_start:
                            next_seg_start = oidx

                end = min(next_seg_start, idx + 300)
                snippet = content[idx:end]

                values = _extract_values(snippet)
                if not values:
                    search_from = idx + 1
                    continue

                if years and len(values) >= len(years):
                    for i, y in enumerate(years[:len(values)]):
                        facts.append(FinancialFact(
                            ticker=ticker,
                            fiscal_year=y,
                            metric_name=f"Revenue: {segment_name}",
                            value=values[i],
                            metric_category=MetricCategory.ABSOLUTE,
                            source_chunk_id=chunk_id,
                            section_title=section_title,
                            is_segment=True,
                            segment_name=segment_name,
                        ))
                elif years:
                    facts.append(FinancialFact(
                        ticker=ticker,
                        fiscal_year=years[0],
                        metric_name=f"Revenue: {segment_name}",
                        value=values[0],
                        metric_category=MetricCategory.ABSOLUTE,
                        source_chunk_id=chunk_id,
                        section_title=section_title,
                        is_segment=True,
                        segment_name=segment_name,
                    ))
                else:
                    facts.append(FinancialFact(
                        ticker=ticker,
                        fiscal_year=doc_year,
                        metric_name=f"Revenue: {segment_name}",
                        value=values[0],
                        metric_category=MetricCategory.ABSOLUTE,
                        source_chunk_id=chunk_id,
                        section_title=section_title,
                        is_segment=True,
                        segment_name=segment_name,
                    ))
                break

    return facts


# Phrases that should NOT trigger a financial line-item extraction when
# they precede a label match (e.g., "cost of revenue" should not extract
# "Total Revenue" facts).
_SKIP_PREFIXES: list[str] = [
    "cost of", "costs of",
    "cost of sales", "costs of sales",
    "cost of goods sold",
    "total cost of",
]

# Label-specific context filters: if any of these phrases appear within
# 30 chars BEFORE the matched label, skip it.
_LABEL_CONTEXT_FILTERS: dict[str, list[str]] = {
    "revenue": ["cost of", "costs of", "cost of sales"],
    "revenues": ["cost of", "costs of", "cost of sales"],
}


_EPS_VALUE = re.compile(
    r"\$\s*\(\s*([\d,]+(?:\.\d+)?)\s*\)"   # $ ( 0.27 ) — negative
    r"|\$\s*([\d,]+(?:\.\d+)?)",            # $ 2.09 — positive
)


def _extract_eps_values(text: str) -> list[float]:
    """Extract EPS values from a line like 'Diluted earnings per share $ 2.09 $ 3.24'.

    EPS values are dollar-prefixed and can be small (< $1000, unlike most
    financial values in $M).  Only captures $-prefixed values, never bare
    numbers, to avoid grabbing weighted-average share counts.
    """
    values: list[float] = []
    for m in _EPS_VALUE.finditer(text):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        val = float(raw)
        if m.group(1) is not None:
            val = -val  # parenthetical = negative
        # EPS is never a year number (1900-2100); those are table headers
        if 1900 <= val <= 2100:
            continue
        values.append(val)
    return values


def _extract_known_metrics(
    content: str,
    doc_year: int,
    ticker: str,
    chunk_id: str,
    section_title: str | None,
) -> list[FinancialFact]:
    """Extract known financial line items from the chunk content.

    Labels are matched only when followed by a dollar sign or numeric value
    within 50 characters, to avoid false positives from incidental matches
    like "revenue" inside "Cost of revenue" or "Net income" in narratives.
    """
    facts: list[FinancialFact] = []
    years_found = _extract_years(content)

    for metric_name, labels in _KNOWN_LINE_ITEMS.items():
        for label in labels:
            # Match label followed by a dollar amount OR a bare number >= 1000.
            # Many financial tables put $ only on the first line item and use
            # bare numbers for continuation rows (e.g., "Total revenue 281,724").
            # Use [$] character class for literal $ to avoid Python 3.14's
            # deprecation of invalid escape sequences like \$.
            m = re.search(
                r"\b" + re.escape(label) + r"(?!\s+by)\s*[:]?\s*[$]?\s*(?:[\d(])",
                content.lower(),
            )
            if not m:
                continue
            # Check context before the label: skip if preceded by a
            # disallowed phrase (e.g., "revenue" inside "cost of revenue").
            pre_context = content.lower()[:m.start()]
            skip = False
            for context_filter in _LABEL_CONTEXT_FILTERS.get(label, []):
                if re.search(rf"{re.escape(context_filter)}\s*$", pre_context):
                    skip = True
                    break
            if skip:
                continue

            idx = m.start()
            is_eps = metric_name == "Diluted EPS"
            is_total = label.startswith("total")
            if is_eps:
                # EPS values are always dollar-prefixed and close to the label.
                # Skip narrative text by requiring a $ within 30 chars.
                after_label = content[idx + len(label):idx + len(label) + 30]
                if "$" not in after_label:
                    continue
                line_end = content.find("\n", idx)
                if line_end == -1:
                    line_end = len(content)
                snippet = content[idx:line_end + 1]
                values = _extract_eps_values(snippet)
            elif is_total:
                snippet = content[idx:idx + 250]
                values = _extract_values(snippet)
            else:
                # For non-total labels (e.g., "revenue", "net sales"),
                # restrict to values on the same line only to avoid
                # picking up sub-category numbers from following table rows.
                line_end = content.find("\n", idx)
                if line_end == -1:
                    line_end = len(content)
                snippet = content[idx:line_end + 1]
                values = _extract_values(snippet)
            if not values:
                continue
            if years_found and len(values) >= len(years_found):
                for i, y in enumerate(years_found):
                    facts.append(FinancialFact(
                        ticker=ticker, fiscal_year=y, metric_name=metric_name,
                        value=values[i], metric_category=MetricCategory.ABSOLUTE,
                        source_chunk_id=chunk_id,
                        section_title=section_title,
                    ))
            else:
                clean_label = label.split("(")[0].strip()
                if clean_label in content.lower()[:idx + len(label)]:
                    for i, val in enumerate(values[:3]):
                        facts.append(FinancialFact(
                            ticker=ticker,
                            fiscal_year=doc_year - i,
                            metric_name=metric_name,
                            value=val,
                            metric_category=MetricCategory.ABSOLUTE,
                            source_chunk_id=chunk_id,
                            section_title=section_title,
                        ))
            break
    return facts


def extract_facts(chunks: list[RetrievedChunk]) -> FactSet:
    fact_set = FactSet()

    # Process chunks in priority order so that facts from authoritative
    # chunks (summary tables, year-aligned chunks) are registered FIRST
    # and won't be shadowed by later narrative-only or cross-year chunks.
    def _chunk_priority(c: RetrievedChunk) -> int:
        if not c.content or not c.fiscal_year:
            return 99
        years = _extract_years(c.content)
        # Priority 0: chunk FY matches an extracted year (best alignment)
        if years and c.fiscal_year in years:
            return 0
        # Priority 1: summary / financial table section
        if any(tag in c.content.lower() for tag in ("summary", "fiscal year")):
            return 1
        # Priority 2: has extractable years but no alignment
        if years:
            return 2
        # Priority 3: narrative-only, no years
        return 3

    for chunk in sorted(chunks, key=_chunk_priority):
        if not chunk.content or not chunk.ticker or not chunk.fiscal_year:
            continue
        content = chunk.content
        ticker = chunk.ticker.upper()
        doc_year = chunk.fiscal_year
        chunk_id = chunk.chunk_id
        section_title = chunk.section_title

        if "net sales by category" in content.lower() or "products and services performance" in content.lower():
            table_facts = _parse_revenue_table(content, doc_year, ticker, chunk_id, section_title)
            fact_set.facts.extend(table_facts)

        segment_facts = _extract_segment_facts(content, doc_year, ticker, chunk_id, section_title)
        fact_set.facts.extend(segment_facts)

        metric_facts = _extract_known_metrics(content, doc_year, ticker, chunk_id, section_title)
        fact_set.facts.extend(metric_facts)

    # Deduplicate conflicting facts by preferring values that appear in
    # MORE chunks (frequency-based).  This naturally favors correct facts
    # that recur across multiple financial-table chunks over spurious
    # matches from narrative or pro-forma chunks.
    fact_set.facts = _deduplicate_facts(fact_set.facts)

    logger.info(
        "Extraction complete",
        total_facts=len(fact_set.facts),
        unique_tickers=len(fact_set.tickers()),
        unique_metrics=len(fact_set.metrics()),
    )
    return fact_set


def compute_revenue_shares(fact_set: FactSet) -> FactSet:
    """Derive revenue-share percentages from absolute revenue facts.

    For each (ticker, year), computes category_revenue / total_revenue * 100.
    Produces SHARE-category facts. Does NOT modify the input FactSet.
    """
    share_set = FactSet()
    for ticker in fact_set.tickers():
        for year in fact_set.years():
            total = fact_set.get(ticker, "Total Revenue", year)
            if not total or total.value is None or total.value <= 0:
                continue

            for metric in fact_set.metrics():
                if not metric.startswith("Revenue:"):
                    continue
                fact = fact_set.get(ticker, metric, year)
                if fact is None or fact.value is None:
                    continue

                share_pct = round(fact.value / total.value * 100, 1)
                segment = fact.segment_name or metric.replace("Revenue: ", "")
                share_fact = FinancialFact(
                    ticker=ticker,
                    fiscal_year=year,
                    metric_name=f"Share: {segment}",
                    value=share_pct,
                    metric_category=MetricCategory.SHARE,
                    source_chunk_id=fact.source_chunk_id,
                    section_title=fact.section_title,
                    is_segment=fact.is_segment,
                    segment_name=segment,
                )
                share_set.facts.append(share_fact)

    return share_set


def compute_growth_rates(
    facts: list[FinancialFact],
) -> list[dict[str, Any]]:
    """Compute YoY growth rates for ABSOLUTE (dollar) metrics only.

    Share/percentage metrics produce meaningless growth rates (e.g.,
    "iPhone share went from 52.1% to 50.4%" is a -1.7pp change, not -3.3% growth)
    and must be excluded from this computation.
    """
    by_key: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for f in facts:
        if f.value is not None and f.metric_category == MetricCategory.ABSOLUTE:
            by_key[(f.ticker, f.metric_name)][f.fiscal_year] = f.value

    results: list[dict[str, Any]] = []
    for (ticker, metric), year_values in by_key.items():
        years = sorted(year_values.keys())
        if len(years) < 2:
            continue
        growth_rates: list[dict[str, Any]] = []
        for i in range(1, len(years)):
            prev_val = year_values[years[i - 1]]
            curr_val = year_values[years[i]]
            if prev_val and prev_val > 0:
                pct = round((curr_val - prev_val) / prev_val * 100, 1)
            else:
                pct = None
            growth_rates.append({
                "from_year": years[i - 1],
                "to_year": years[i],
                "growth_pct": pct,
            })
        if growth_rates:
            results.append({
                "ticker": ticker,
                "metric": metric,
                "growth_rates": growth_rates,
            })

    return results


def compute_cagr(facts: list[FinancialFact]) -> list[dict[str, Any]]:
    """Compute CAGR for ABSOLUTE (dollar) metrics only.

    CAGR on share percentages is mathematically nonsensical — it conflates
    composition changes with absolute growth. Only dollar-value metrics
    (revenue, net income, etc.) qualify for CAGR computation.
    """
    by_key: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for f in facts:
        if f.value is not None and f.metric_category == MetricCategory.ABSOLUTE:
            by_key[(f.ticker, f.metric_name)][f.fiscal_year] = f.value

    results: list[dict[str, Any]] = []
    for (ticker, metric), year_values in by_key.items():
        years = sorted(year_values.keys())
        if len(years) < 3:
            continue
        first_val = year_values[years[0]]
        last_val = year_values[years[-1]]
        n = len(years) - 1
        if first_val and last_val and first_val > 0 and n > 0:
            cagr_val = round(((last_val / first_val) ** (1 / n) - 1) * 100, 1)
        else:
            cagr_val = None
        results.append({
            "ticker": ticker,
            "metric": metric,
            "first_year": years[0],
            "last_year": years[-1],
            "first_value": first_val,
            "last_value": last_val,
            "cagr_pct": cagr_val,
        })

    return results


def _format_dollar_table(
    title: str,
    headers: list[str],
    rows: list[tuple[str, list[float | None]]],
    unit: str = "$ millions",
    fmt: str = "${:,.0f}",
) -> list[str]:
    """Build a pipe-delimited markdown table for rendering in the frontend."""
    has_any_data = any(any(v is not None for v in vals) for _, vals in rows)
    if not has_any_data:
        return []
    parts: list[str] = [f"## {title} ({unit})", ""]
    header = "| " + headers[0] + " |"
    for h in headers[1:]:
        header += " " + h + " |"
    parts.append(header)
    sep = "|" + "---|" * len(headers)
    parts.append(sep)
    for label, values in rows:
        has_data = any(v is not None for v in values)
        if not has_data:
            continue
        cells = [f" **{label}** "]
        for v in values:
            if v is not None:
                cells.append(" " + fmt.format(v) + " ")
            else:
                cells.append(" — ")
        parts.append("|" + "|".join(cells) + "|")
    parts.append("")
    return parts


def _growth_header(
    growth_rates: list[dict[str, Any]],
) -> list[str]:
    """Build column headers for the growth-rate table."""
    seen: set[str] = set()
    parts_list: list[str] = []
    for g in growth_rates:
        for gr in g.get("growth_rates", []):
            fr = gr.get("from_year", "")
            to = gr.get("to_year", "")
            label = f"FY{fr}→FY{to}"
            if label not in seen:
                seen.add(label)
                parts_list.append(label)
    return parts_list


def _build_multi_ticker_rows(
    fact_set: FactSet,
    metrics: list[str],
    years: list[int],
    tickers: list[str],
) -> list[tuple[str, list[float | None]]]:
    """Build table rows that include all tickers.

    For each metric, creates one row per ticker that has data for it.
    Row labels are formatted as ``{ticker}: {metric}``.
    """
    rows: list[tuple[str, list[float | None]]] = []
    seen: set[tuple[str, str]] = set()
    for metric in metrics:
        for t in tickers:
            key = (t, metric)
            if key in seen:
                continue
            vals: list[float | None] = []
            has_any = False
            for y in years:
                f = fact_set.get(t, metric, y)
                vals.append(f.value if f else None)
                if f is not None:
                    has_any = True
            if has_any:
                seen.add(key)
                rows.append((f"{t} {metric}", vals))
    return rows


def format_structured_context(
    fact_set: FactSet,
    intent: str,
    growth_rates: list[dict] | None = None,
    cagr_data: list[dict] | None = None,
) -> str:
    parts: list[str] = [
        "=== STRUCTURED FINANCIAL DATA (Pre-computed — Deterministic) ===",
        "The data below has been extracted programmatically from SEC filings.",
        "All calculations (growth rates, CAGR, revenue share) are computed in Python — not by the LLM.",
        "",
    ]

    tickers = fact_set.tickers()
    years = fact_set.years()
    revenue_metrics = fact_set.metrics_by_category(MetricCategory.ABSOLUTE)
    share_metrics = fact_set.metrics_by_category(MetricCategory.SHARE)

    # -- Section 1: Revenue by Category ($M) — absolute dollars --
    rev_row_metrics = [m for m in revenue_metrics if m.startswith("Revenue:")]

    if rev_row_metrics and intent in ("revenue_mix", "financial_metrics", "company_comparison"):
        col_headers = ["Category"] + [f"FY{y}" for y in years]
        rows = _build_multi_ticker_rows(fact_set, rev_row_metrics, years, tickers)
        parts.extend(_format_dollar_table("Revenue by Category", col_headers, rows, "$ millions"))

    # -- Section 2: Revenue Mix (%) — share of total --
    share_row_metrics = [m for m in share_metrics]

    if share_row_metrics and intent in ("revenue_mix", "company_comparison"):
        col_headers = ["Segment"] + [f"FY{y}" for y in years]
        rows = _build_multi_ticker_rows(fact_set, share_row_metrics, years, tickers)
        parts.extend(_format_dollar_table("Revenue Mix", col_headers, rows, "%", "{:.1f}%"))

    # -- Section 3: Key Financial Metrics ($M) — company-level absolute metrics --
    financial_metrics = [m for m in revenue_metrics if not m.startswith("Revenue:")]

    if financial_metrics and intent in ("financial_metrics", "company_comparison"):
        col_headers = ["Metric"] + [f"FY{y}" for y in years]
        rows = _build_multi_ticker_rows(fact_set, financial_metrics, years, tickers)
        parts.extend(_format_dollar_table("Key Financial Metrics", col_headers, rows, "$ millions"))

    # -- Section 4: YoY Growth (%) — only for ABSOLUTE metrics, only in financial or comparison intents --
    if growth_rates and intent in ("financial_metrics", "company_comparison"):
        parts.append("## Year-over-Year Growth Rates (%)")
        parts.append("")
        growth_headers = _growth_header(growth_rates)
        parts.append("| Metric | " + " | ".join(growth_headers) + " |")
        parts.append("|" + "---|" * (len(growth_headers) + 1))
        for entry in growth_rates:
            cells = [f" **{entry['ticker']} {entry['metric']}** "]
            for gr in entry.get("growth_rates", []):
                pct = gr.get("growth_pct")
                cells.append(f" {pct:.1f}% " if pct is not None else " — ")
            parts.append("|" + "|".join(cells) + "|")
        parts.append("")

    # -- Section 5: CAGR (%) — only for ABSOLUTE metrics, only in financial or comparison intents --
    if cagr_data and intent in ("financial_metrics", "company_comparison"):
        parts.append("## Compound Annual Growth Rate (CAGR)")
        parts.append("")
        parts.append("| Metric | Period | CAGR |")
        parts.append("|---|----|----|")
        for entry in cagr_data:
            cagr_val = entry.get("cagr_pct")
            period = (
                f"FY{entry['first_year']}→FY{entry['last_year']}"
                if entry.get("first_year") and entry.get("last_year") else ""
            )
            pct_str = f"{cagr_val}%" if cagr_val is not None else "—"
            parts.append(f"| **{entry['ticker']} {entry['metric']}** | {period} | {pct_str} |")
        parts.append("")

    # -- Citations --
    parts.append("## Data Sources (Citations)")
    seen_citations: set[str] = set()
    for f in fact_set.facts:
        label = f.citation_label
        if label and label not in seen_citations:
            seen_citations.add(label)
            parts.append(f"- {label}")

    return "\n".join(parts)
