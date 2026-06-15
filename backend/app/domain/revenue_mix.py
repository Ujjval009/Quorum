from __future__ import annotations

import re

from app.core.logging import logger

_YEAR_PATTERN = re.compile(r"for (\d{4}), (\d{4}) and (\d{4})")
_CATEGORY_ORDER = [
    "iPhone",
    "Mac",
    "iPad",
    "Wearables, Home and Accessories",
    "Services",
    "Total Net Sales",
]

# Matches a revenue value in the table: a number >= 1000 with optional $ and commas.
# These appear as either "$ 205,489" or bare "29,984" or "26,694".
# We explicitly exclude change values like "(2)%", "7 %", "— %", or numbers < 1000.
_REVENUE_VALUE = re.compile(
    r"\$\s*([\d,]+)|(?<!\d)([\d,]{4,})(?!(?:\s*%|\s*\)\s*%))"
)


def _parse_years(text: str) -> list[int] | None:
    m = _YEAR_PATTERN.search(text)
    if not m:
        return None
    return [int(m.group(1)), int(m.group(2)), int(m.group(3))]


_COLUMN_HEADER = re.compile(r"\d{4} Change \d{4} Change \d{4}")


def _extract_revenue_values(text: str) -> list[float]:
    """Extract all revenue-like numbers from a table section.

    Skips column headers, change percentages, and footnotes.
    Starts extraction after the "YYYY Change YYYY Change YYYY" header row.
    """
    # Find the column header row and start data extraction after it
    data_start = 0
    m = _COLUMN_HEADER.search(text)
    if m:
        data_start = m.end()
    else:
        # Fallback: find first occurrence of a category name with word boundary
        for cat in [" iPhone ", "\niPhone", " iPhone$"]:
            idx = text.find(cat)
            if idx != -1:
                data_start = idx
                break

    data_text = text[data_start:] if data_start < len(text) else text

    seen: set[tuple[int, int]] = set()
    values: list[float] = []

    for m in _REVENUE_VALUE.finditer(data_text):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        val = float(raw)
        start = m.start()
        end = m.end()

        key = (start, end)
        if key in seen:
            continue
        seen.add(key)

        if val < 1_000:
            continue

        values.append(val)

    return values


def _extract_table_section(content: str) -> str | None:
    start = content.find("Products and Services Performance")
    if start == -1:
        start = content.find("net sales by category")
    if start == -1:
        return None

    section = content[start:]

    # Find the end of the table — typically at "iPhone iPhone" (next section)
    # or after "Total net sales" when the next narrative starts.
    for term in ["iPhone iPhone", "iPhone net sales", "iPad net sales", "Mac net sales"]:
        idx = section.find(term)
        if idx != -1:
            return section[:idx]

    # Fallback: take a generous slice
    return section[:800]


def parse_revenue_table(content: str) -> dict[int, dict[str, float]] | None:
    years = _parse_years(content)
    if not years:
        return None

    section = _extract_table_section(content)
    if not section:
        return None

    values = _extract_revenue_values(section)
    num_years = len(years)

    # We expect 6 or 7 categories (with Total). 3 values per category.
    # Minimum is 5 product categories × 3 years = 15 values.
    # With Total: 6 × 3 = 18 values.
    if len(values) < 5 * num_years:
        logger.debug("Not enough revenue values", found=len(values), needed=5 * num_years)
        return None

    # Determine category count: if we have enough for 6 categories including Total
    num_cats = 6 if len(values) >= 6 * num_years else 5
    cats = _CATEGORY_ORDER[:num_cats]

    result: dict[int, dict[str, float]] = {}
    for y in years:
        result[y] = {}

    for ci, cat in enumerate(cats):
        for yi, year in enumerate(years):
            idx = ci * num_years + yi
            if idx < len(values):
                result[year][cat] = values[idx]

    return result


def merge_tables(tables: list[dict[int, dict[str, float]]]) -> dict[int, dict[str, float]]:
    merged: dict[int, dict[str, float]] = {}
    for table in tables:
        for year, categories in table.items():
            if year not in merged:
                merged[year] = {}
            for cat, val in categories.items():
                if cat not in merged[year]:
                    merged[year][cat] = val
    return merged


def compute_shares(data: dict[int, dict[str, float]]) -> dict[int, dict[str, float]]:
    shares: dict[int, dict[str, float]] = {}
    for year, categories in data.items():
        total = categories.get("Total Net Sales", 0)
        if total == 0:
            total = sum(v for k, v in categories.items() if k != "Total Net Sales")
        shares[year] = {}
        for cat in _CATEGORY_ORDER:
            if cat == "Total Net Sales":
                continue
            rev = categories.get(cat, 0)
            shares[year][cat] = round((rev / total * 100) if total > 0 else 0, 2)
    return shares


def compute_mix_shifts(shares: dict[int, dict[str, float]]) -> list[dict]:
    sorted_years = sorted(shares.keys())
    if len(sorted_years) < 2:
        return []

    first = sorted_years[0]
    last = sorted_years[-1]

    shifts = []
    for cat in _CATEGORY_ORDER:
        if cat == "Total Net Sales":
            continue
        start_share = shares[first].get(cat, 0)
        end_share = shares[last].get(cat, 0)
        shift = round(end_share - start_share, 2)
        shifts.append({
            "category": cat,
            f"fy{first}_share": start_share,
            f"fy{last}_share": end_share,
            "shift_pp": shift,
        })

    shifts.sort(key=lambda x: abs(x["shift_pp"]), reverse=True)
    return shifts


def format_mix_analysis(data: dict[int, dict[str, float]]) -> str:
    shares = compute_shares(data)
    shifts = compute_mix_shifts(shares)
    sorted_years = sorted(shares.keys())

    lines: list[str] = []
    lines.append("=== REVENUE MIX ANALYSIS (Pre-calculated) ===\n")

    # Share table
    header_years = " ".join(f"FY{y:<8}" for y in sorted_years)
    lines.append(f"{'Category':<35} {header_years}")
    lines.append("-" * 80)

    for cat in _CATEGORY_ORDER:
        if cat == "Total Net Sales":
            continue
        vals = " ".join(f"{shares[y].get(cat, 0):>7.1f}%   " for y in sorted_years)
        lines.append(f"{cat:<35} {vals}")

    lines.append("")

    # Revenue table
    lines.append("Underlying Revenue ($M):")
    rev_header = " ".join(f"FY{y:<12}" for y in sorted_years)
    lines.append(f"{'Category':<35} {rev_header}")
    lines.append("-" * 80)

    for cat in _CATEGORY_ORDER:
        vals = " ".join(
            f"${data[y].get(cat, 0):>10,.0f}" if data[y].get(cat, 0) else f"{'N/A':>12}"
            for y in sorted_years
        )
        lines.append(f"{cat:<35} {vals}")

    lines.append("")

    # Mix shifts
    lines.append("Mix Shift (percentage points, first → last year):")
    for s in shifts:
        direction = "+" if s["shift_pp"] >= 0 else ""
        lines.append(f"  {s['category']:<30} {direction}{s['shift_pp']:.2f} pp")

    lines.append("")

    # Observations
    lines.append("Key Observations (calculated):")
    if shifts:
        biggest = shifts[0]
        lines.append(f"  - Largest mix shift: {biggest['category']} ({biggest['shift_pp']:+.2f} pp)")
    for s in shifts:
        if s["shift_pp"] > 0.5:
            lines.append(f"  - {s['category']} share expanded by {s['shift_pp']:+.2f} pp — gaining revenue mix weight")
        elif s["shift_pp"] < -0.5:
            lines.append(f"  - {s['category']} share contracted by {s['shift_pp']:+.2f} pp — losing revenue mix weight")

    return "\n".join(lines)


def build_mix_context(chunks: list) -> str | None:
    tables: list[dict[int, dict[str, float]]] = []
    table_sources: list[str] = []

    for chunk in chunks:
        content = chunk.content if hasattr(chunk, "content") else str(chunk)
        if "products and services performance" not in content.lower() and "net sales by category" not in content.lower():
            continue
        table = parse_revenue_table(content)
        if table:
            tables.append(table)
            label = chunk.citation_label if hasattr(chunk, "citation_label") else ""
            table_sources.append(label)
            logger.info("Parsed revenue table", source=label, years=sorted(table.keys()))

    if not tables:
        logger.debug("No revenue tables parsed from chunks")
        return None

    merged = merge_tables(tables)
    analysis = format_mix_analysis(merged)

    source_line = f"\nData sources: {', '.join(table_sources)}" if table_sources else ""
    analysis += source_line

    logger.info("Revenue mix analysis built", years=sorted(merged.keys()), tables=len(tables))
    return analysis
