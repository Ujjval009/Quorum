from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import logger
from app.domain.retrieval import RetrievedChunk

_RISK_HEADING_PATTERNS = re.compile(
    r"^(?:risks?\s+related\s+to|our\s+\w+\s+(?:may|could|is|are)|"
    r"we\s+(?:may|could|face|are\s+subject|depend|rely)|"
    r"if\s+(?:we|our)|the\s+(?:loss|failure|disruption)|"
    r"changes?\s+in|adverse\s+|any\s+|unfavorable|"
    r"increased?\s+|decreased?\s+)",
    re.IGNORECASE,
)

_KNOWN_RISK_TOPICS = frozenset({
    "economic", "market", "competition", "competitive", "regulatory", "regulation",
    "legal", "litigation", "tax", "taxation", "intellectual property", "patent",
    "cybersecurity", "security", "data breach", "privacy",
    "supply chain", "supplier", "manufacturing", "production",
    "customer", "concentration", "demand", "sales",
    "international", "foreign", "global", "geopolitical",
    "currency", "exchange rate", "interest rate", "inflation",
    "acquisition", "integration", "restructuring",
    "technology", "innovation", "research and development", "r&d",
    "personnel", "key personnel", "employee", "workforce",
    "pandemic", "health", "epidemic", "disaster",
    "climate", "environmental", "esg", "sustainability",
    "indebtedness", "debt", "liquidity", "capital", "financing",
    "accounting", "internal control", "financial reporting",
    "outsourcing", "third party", "partner",
    "export", "import", "tariff", "trade", "sanction",
    "ai", "artificial intelligence", "machine learning",
    "cloud", "infrastructure", "data center", "capacity",
    "reputation", "brand",
    "warranty", "product liability", "defect",
    "insurance", "coverage",
    "conflict of interest", "related party",
    "government", "political",
    "seasonal", "quarterly", "fluctuation",
    "common stock", "ownership", "shareholder",
    "forward-looking", "projection",
})


@dataclass
class RiskSegment:
    heading: str
    text: str
    word_count: int
    key_phrases: set[str] = field(default_factory=set)


@dataclass
class YearRiskCorpus:
    year: int
    full_text: str
    segments: list[RiskSegment]
    total_word_count: int = 0


@dataclass
class RiskMatch:
    label: str
    years: dict[int, RiskSegment]
    change_type: str = "stable"


@dataclass
class RiskDiffResult:
    added: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    expanded: list[dict[str, Any]]
    reduced: list[dict[str, Any]]
    stable: list[dict[str, Any]]
    new_themes: list[str]
    corpora: dict[int, YearRiskCorpus]
    has_multi_year_data: bool = False


# ── Step 1: Group chunks by year ──────────────────────────────────────────


def group_by_year(chunks: list[RetrievedChunk]) -> dict[int, list[RetrievedChunk]]:
    grouped: dict[int, list[RetrievedChunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.fiscal_year:
            grouped[chunk.fiscal_year].append(chunk)
    logger.info("Risk diff — chunks grouped by year", years=sorted(grouped.keys()), total=len(chunks))
    return dict(sorted(grouped.items()))


# ── Step 2: Segment risk text into individual risk topics ─────────────────


def _extract_key_phrases(text: str) -> set[str]:
    """Extract meaningful key phrases from risk factor text."""
    phrases: set[str] = set()
    for match in re.finditer(
        r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}|[A-Z]{2,}(?:\s+[A-Z]{2,}){0,2}",
        text,
    ):
        phrase = match.group(0).lower()
        words = phrase.split()
        if 2 <= len(words) <= 5 and len(phrase) > 8:
            phrases.add(phrase)

    lowered = text.lower()
    for topic in _KNOWN_RISK_TOPICS:
        if topic in lowered:
            phrases.add(topic)

    # Remove generic boilerplate that appears in every risk heading
    phrases -= {"risks related", "related to", "our business", "we may", "we could"}
    return phrases


def _segment_risk_text(text: str) -> list[RiskSegment]:
    """Split risk factor text into individual risk topic segments.

    Handles two common formats:
      - Paragraphs separated by blank lines.
      - Segments starting with a risk-heading pattern.
    """
    # Split by double newlines or section boundaries
    blocks = re.split(r"\n\s*\n", text)
    segments: list[RiskSegment] = []

    for block in blocks:
        block = block.strip()
        if not block or len(block.split()) < 5:
            continue

        lines = block.split("\n")
        heading = lines[0].strip().rstrip(":")
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        if not body:
            body = heading
            first_sentence = re.split(r"[.!?]", heading)[0]
            heading = first_sentence[:80] if len(first_sentence) > 5 else heading[:80]

        word_count = len(block.split())
        key_phrases = _extract_key_phrases(block)

        segments.append(RiskSegment(
            heading=heading.strip(),
            text=block,
            word_count=word_count,
            key_phrases=key_phrases,
        ))

    return segments


# ── Step 3: Build year corpora ────────────────────────────────────────────


def build_corpora(grouped: dict[int, list[RetrievedChunk]]) -> dict[int, YearRiskCorpus]:
    corpora: dict[int, YearRiskCorpus] = {}
    for year, year_chunks in grouped.items():
        full_text = "\n\n".join(c.content for c in year_chunks)
        segments = _segment_risk_text(full_text)
        corpora[year] = YearRiskCorpus(
            year=year,
            full_text=full_text,
            segments=segments,
            total_word_count=len(full_text.split()),
        )
        logger.debug(
            "Risk diff — year corpus",
            year=year,
            segments=len(segments),
            total_words=corpora[year].total_word_count,
        )
    return corpora


# ── Step 4: Match segments across years ───────────────────────────────────


def _heading_similarity(h1: str, h2: str) -> float:
    tokens1 = set(re.findall(r"\w+", h1.lower()))
    tokens2 = set(re.findall(r"\w+", h2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union) if union else 0.0


def _phrase_overlap(p1: set[str], p2: set[str]) -> float:
    if not p1 or not p2:
        return 0.0
    return len(p1 & p2) / len(p1 | p2)


def _match_segments_across_years(
    corpora: dict[int, YearRiskCorpus],
) -> list[RiskMatch]:
    years = sorted(corpora.keys())
    if not years:
        return []

    all_matches: dict[str, RiskMatch] = {}

    # Use earliest year as reference for matching forward
    ref_year = years[0]
    ref_segments = corpora[ref_year].segments

    for ref_idx, ref_seg in enumerate(ref_segments):
        match_key = re.sub(r"\W+", "_", ref_seg.heading.lower())[:40]
        rm = RiskMatch(
            label=ref_seg.heading[:80],
            years={ref_year: ref_seg},
        )

        for year in years[1:]:
            best_score = 0.0
            best_seg: RiskSegment | None = None
            for seg in corpora[year].segments:
                hs = _heading_similarity(ref_seg.heading, seg.heading)
                po = _phrase_overlap(ref_seg.key_phrases, seg.key_phrases)
                combined = hs * 0.6 + po * 0.4
                if combined > best_score:
                    best_score = combined
                    best_seg = seg
            if best_score > 0.3 and best_seg is not None:
                rm.years[year] = best_seg

        all_matches[match_key] = rm

    # Find segments in later years that weren't matched → potential "added" risks
    for year in years[1:]:
        for seg in corpora[year].segments:
            already_matched = False
            for rm in all_matches.values():
                if year in rm.years and rm.years[year] is seg:
                    already_matched = True
                    break

            if already_matched:
                continue

            matched_to = False
            for other_year in years:
                if other_year == year:
                    continue
                for other_seg in corpora[other_year].segments:
                    hs = _heading_similarity(seg.heading, other_seg.heading)
                    po = _phrase_overlap(seg.key_phrases, other_seg.key_phrases)
                    if hs * 0.6 + po * 0.4 > 0.5:
                        match_key = re.sub(r"\W+", "_", other_seg.heading.lower())[:40]
                        if match_key not in all_matches:
                            all_matches[match_key] = RiskMatch(
                                label=other_seg.heading[:80],
                                years={other_year: other_seg},
                            )
                        all_matches[match_key].years[year] = seg
                        matched_to = True
                        break
                if matched_to:
                    break

            if not matched_to:
                # Create a new match for this segment that appeared only in this year
                match_key = f"unique_{year}_{seg.heading.lower()[:30]}"
                match_key = re.sub(r"\W+", "_", match_key)
                logger.debug(
                    "Risk diff — unmatched segment",
                    year=year,
                    heading=seg.heading[:60],
                    match_key=match_key,
                    is_latest_year=(year == years[-1]),
                )
                all_matches[match_key] = RiskMatch(
                    label=seg.heading[:80],
                    years={year: seg},
                    change_type="added" if year == years[-1] else "removed",
                )

    # Classify change types for multi-year matches
    for rm in all_matches.values():
        matched_years = set(rm.years.keys())
        if len(matched_years) < 2:
            continue

        early = min(matched_years)
        late = max(matched_years)
        early_wc = rm.years[early].word_count
        late_wc = rm.years[late].word_count

        if early_wc > 0 and late_wc > 0:
            ratio = late_wc / early_wc
            if ratio > 1.5:
                rm.change_type = "expanded"
            elif ratio < 0.67:
                rm.change_type = "reduced"
            else:
                rm.change_type = "stable"

    return list(all_matches.values())


# ── Step 5: Classify and format diff ──────────────────────────────────────


def classify_changes(matches: list[RiskMatch], years: list[int]) -> RiskDiffResult:
    added: list[dict] = []
    removed: list[dict] = []
    expanded: list[dict] = []
    reduced: list[dict] = []
    stable: list[dict] = []
    new_themes: set[str] = set()

    # ── Identify emerging themes from added and expanded risks ──
    _THEME_KEYWORDS: dict[str, list[str]] = {
        "AI & Machine Learning": ["artificial intelligence", "ai", "machine learning", "generative ai", "llm", "neural"],
        "Cloud Infrastructure": ["cloud", "azure", "aws", "data center", "infrastructure", "compute"],
        "Geopolitical Risk": ["geopolitical", "sanctions", "trade", "tariff", "china", "export control", "foreign"],
        "Supply Chain": ["supply chain", "supplier", "manufacturing", "logistics", "disruption"],
        "Cybersecurity": ["cybersecurity", "cyber", "data breach", "security", "hacking", "malware"],
        "Regulatory": ["regulation", "regulatory", "compliance", "antitrust", "litigation", "legal"],
        "ESG & Sustainability": ["esg", "sustainability", "climate", "environmental", "carbon", "renewable"],
        "Talent & Workforce": ["talent", "employee", "workforce", "labor", "unionization", "compensation"],
        "Data Privacy": ["privacy", "gdpr", "data protection", "pii", "personal data"],
        "Pandemic & Health": ["pandemic", "covid", "health", "epidemic", "biological"],
    }
    
    theme_presence: dict[str, int] = {theme: 0 for theme in _THEME_KEYWORDS}
    
    # Count theme mentions in added and expanded risks
    for item in added + expanded:
        label_lower = item.get("label", "").lower()
        for theme, keywords in _THEME_KEYWORDS.items():
            if any(kw in label_lower for kw in keywords):
                theme_presence[theme] += 1
    
    # Identify themes that appear in multiple added/expanded risks
    for theme, count in theme_presence.items():
        if count >= 2:  # Theme appears in at least 2 added/expanded risks
            new_themes.add(theme)

    for rm in matches:
        matched_years = sorted(rm.years.keys())
        entry: dict[str, Any] = {
            "label": rm.label,
            "heading": rm.label,
            "years": {str(y): rm.years[y].text[:300] for y in matched_years},
            "word_counts": {str(y): rm.years[y].word_count for y in matched_years},
            "match_count": len(matched_years),
        }

        if rm.change_type == "added":
            entry["first_year"] = min(matched_years)
            added.append(entry)
        elif rm.change_type == "removed":
            entry["last_year"] = max(matched_years)
            removed.append(entry)
        elif rm.change_type == "expanded":
            early = min(matched_years)
            late = max(matched_years)
            entry.update({
                "from_year": early,
                "to_year": late,
                "from_words": rm.years[early].word_count,
                "to_words": rm.years[late].word_count,
                "change_pct": round(
                    (rm.years[late].word_count / rm.years[early].word_count - 1) * 100, 1
                ),
            })
            expanded.append(entry)
        elif rm.change_type == "reduced":
            early = min(matched_years)
            late = max(matched_years)
            entry.update({
                "from_year": early,
                "to_year": late,
                "from_words": rm.years[early].word_count,
                "to_words": rm.years[late].word_count,
                "change_pct": round(
                    (rm.years[late].word_count / rm.years[early].word_count - 1) * 100, 1
                ),
            })
            reduced.append(entry)
        else:
            stable.append(entry)

    added.sort(key=lambda x: x["match_count"], reverse=True)
    removed.sort(key=lambda x: x["match_count"], reverse=True)
    expanded.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)
    reduced.sort(key=lambda x: abs(x.get("change_pct", 0)), reverse=True)

    result = RiskDiffResult(
        added=added,
        removed=removed,
        expanded=expanded,
        reduced=reduced,
        stable=stable,
        new_themes=list(new_themes),
        corpora={},
        has_multi_year_data=len(years) >= 2,
    )

    logger.info(
        "Risk diff — classification complete",
        total_matches=len(matches),
        added=len(added),
        removed=len(removed),
        expanded=len(expanded),
        reduced=len(reduced),
        stable=len(stable),
    )

    return result


# ── Step 6: Build structured context string ────────────────────────────────


def build_risk_diff_context(chunks: list[RetrievedChunk]) -> str:
    grouped = group_by_year(chunks)
    years = sorted(grouped.keys())

    if not years:
        return "# Risk Factor Diff\n\nNo risk factor data retrieved.\n"

    corpora = build_corpora(grouped)
    matches = _match_segments_across_years(corpora)
    diff = classify_changes(matches, years)
    diff.corpora = corpora

    return _format_diff_context(diff, years)


def _format_diff_context(diff: RiskDiffResult, years: list[int]) -> str:
    parts: list[str] = []

    # ── Header ──
    parts.append(f"# Risk Factor Diff Analysis: FY{years[0]} – FY{years[-1]}")
    parts.append(f"Years compared: {', '.join(f'FY{y}' for y in years)}")
    parts.append(f"Distinct risk topics tracked: {len(diff.added) + len(diff.removed) + len(diff.expanded) + len(diff.reduced) + len(diff.stable)}")

    if len(years) < 2:
        parts.append("\n⚠ Only one fiscal year of data retrieved. A multi-year comparison is not possible.")
        return "\n".join(parts)

    # ── New Themes (from Phase 1) ──
    if diff.new_themes:
        parts.append("\n## New Emerging Themes")
        for i, theme in enumerate(sorted(diff.new_themes), 1):
            parts.append(f"{i}. **{theme}** — appears prominently in recent added/expanded risk factors")
        parts.append("")

    # ── Summary Statistics ──
    parts.append("""
## Summary Statistics
| Category | Count |
|----------|-------|
| Added risks | {added} |
| Removed risks | {removed} |
| Expanded risks (word count +50%) | {expanded} |
| Reduced risks (word count −33%) | {reduced} |
| Stable risks | {stable} |
""".format(
        added=len(diff.added),
        removed=len(diff.removed),
        expanded=len(diff.expanded),
        reduced=len(diff.reduced),
        stable=len(diff.stable),
    ))

    # ── Added Risks ──
    if diff.added:
        parts.append("## Added Risks (present in later years, absent in earliest)")
        for i, item in enumerate(diff.added[:15], 1):
            years_found = sorted(int(y) for y in item["years"])
            first_year = min(years_found)
            wc = item["word_counts"].get(str(first_year), 0)
            parts.append(f"""
### {i}. {item['label']}
- **First appeared**: FY{first_year}
- **Present in**: {', '.join(f'FY{y}' for y in years_found)}
- **Words**: ~{wc}
- **Excerpt (FY{first_year})**:
> {item['years'][str(first_year)][:500]}
""")

    # ── Removed Risks ──
    if diff.removed:
        parts.append("\n## Removed Risks (absent in latest year)")
        for i, item in enumerate(diff.removed[:15], 1):
            years_found = sorted(int(y) for y in item["years"])
            last_year = max(years_found)
            wc = item["word_counts"].get(str(last_year), 0)
            parts.append(f"""
### {i}. {item['label']}
- **Last appeared**: FY{last_year}
- **Present in**: {', '.join(f'FY{y}' for y in years_found)}
- **Words**: ~{wc}
- **Excerpt (FY{last_year})**:
> {item['years'][str(last_year)][:500]}
""")

    # ── Expanded Risks ──
    if diff.expanded:
        parts.append("\n## Expanded Risks (word count increased ≥50%)")
        for i, item in enumerate(diff.expanded[:10], 1):
            parts.append(f"""
### {i}. {item['label']}
- **Scale**: {item['from_words']} words (FY{item['from_year']}) → {item['to_words']} words (FY{item['to_year']})
- **Change**: +{item['change_pct']}%
- **Earlier text**:
> {item['years'][str(item['from_year'])][:300]}
- **Later text**:
> {item['years'][str(item['to_year'])][:300]}
""")

    # ── Reduced Risks ──
    if diff.reduced:
        parts.append("\n## Reduced Risks (word count decreased ≥33%)")
        for i, item in enumerate(diff.reduced[:10], 1):
            parts.append(f"""
### {i}. {item['label']}
- **Scale**: {item['from_words']} words (FY{item['from_year']}) → {item['to_words']} words (FY{item['to_year']})
- **Change**: {item['change_pct']}%
- **Earlier text**:
> {item['years'][str(item['from_year'])][:300]}
- **Later text**:
> {item['years'][str(item['to_year'])][:300]}
""")

    # ── Stable Risks (summary only) ──
    if diff.stable:
        parts.append(f"""
## Stable Risks ({len(diff.stable)} items held steady across all years)
""")
        for i, item in enumerate(diff.stable[:20], 1):
            parts.append(f"{i}. {item['label']} — present in {item['match_count']} years")

    # ── Year-by-year corpus reference ──
    if diff.corpora:
        parts.append("\n## Year-by-Year Risk Factor Overview")
        for year, corpus in sorted(diff.corpora.items()):
            parts.append(f"\n### FY{year} — {len(corpus.segments)} risk topics, ~{corpus.total_word_count} words")
            for i, seg in enumerate(corpus.segments[:20], 1):
                parts.append(f"  {i:2d}. [{seg.word_count:4d}w] {seg.heading[:120]}")
            if len(corpus.segments) > 20:
                parts.append(f"       ... and {len(corpus.segments) - 20} more topics")

    return "\n".join(parts)
