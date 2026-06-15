from __future__ import annotations

import re

from app.config import settings
from app.core.logging import logger
from app.domain.retrieval import RetrievedChunk, detect_tickers
from app.domain.revenue_mix import build_mix_context
from app.domain.risk_diff import build_risk_diff_context
from app.domain.comparison import build_comparison_context
from app.domain.extraction import (
    FactSet,
    compute_cagr,
    compute_growth_rates,
    compute_revenue_shares,
    extract_facts,
    format_structured_context,
)

SAFETY_INSTRUCTION = """
SAFETY REQUIREMENTS (these are mandatory):
- Never infer beyond the SEC filings provided in the context.
- Never make forecasts unless explicitly stated in the filings.
- Never fabricate numbers, percentages, or trends.
- If the evidence is insufficient to answer any part of the question, state:
  "The available filings do not provide enough evidence to answer this question."
- Do not fill gaps with assumptions. Acknowledge what the data covers and where it is silent.
"""

GENERAL_PROMPT = f"""You are a senior equity research analyst at a top investment firm. Answer the user's question using the SEC filing excerpts below.

STRUCTURE YOUR ANSWER:
1. **Executive Summary** — 2-3 sentence-level conclusion.
2. **Detailed Analysis** — Tables, multi-year trends, calculations.
3. **Key Findings** — Bullet points of the most important insights.
4. **Evidence Used** — Briefly note which filings/years provided the data.
5. **Analyst Takeaway** — 1-2 sentence verdict.

RULES:
- Base your answer on the provided context. When data is sufficient, answer with conviction. When data is truly absent, simply address what the available data shows.
- Extract numbers from financial tables and present them in clear markdown tables with multi-year columns.
- Calculate and highlight year-over-year changes, compound growth rates, and margin trends.
- Leverage the full temporal range of available data. If chunks span 5 fiscal years, analyze all 5.
- Synthesize across chunks from different years and sections to build a complete picture.
- Always inline-cite sources in the format seen in context headers (e.g. [1] AAPL FY2024 · p.37).
{SAFETY_INSTRUCTION}"""

NARRATIVE_OVERLAY_INSTRUCTION = """
THE DATA TABLES ABOVE ARE THE COMPLETE STRUCTURED OUTPUT.
YOUR JOB IS TO ADD NARRATIVE ANALYSIS ONLY.
DO NOT:
- Do not reproduce any table. The tables above are definitive.
- Do not reformat, reorder, or restate the numbers.
- Do not calculate or recalculate any metric.
- Do NOT say "not enough evidence" or "insufficient data" — the tables are the evidence.

INSTEAD:
1. Read the pre-computed tables carefully.
2. Write ONLY the sections listed below — no tables, no data dumps.
3. Reference specific figures from the tables in your narrative (e.g., "iPhone share contracted from 52.1% to 50.4%").
4. Provide context and interpretation that the numbers alone don't convey.
5. Keep the narrative concise — the tables already show the detail.
"""

STRUCTURED_REVENUE_MIX_NARRATIVE = f"""You are a senior equity research analyst specializing in revenue mix analysis.

The complete revenue mix tables (revenue by category, mix shares, growth rates) have already been computed and provided above.

{NARRATIVE_OVERLAY_INSTRUCTION}

Write these narrative sections:
1. **Executive Summary** — 2-3 sentences summarizing the key mix trends.
2. **Key Findings** — The most important mix shifts, referencing specific figures from the tables.
3. **Detailed Analysis** — Discuss what drove each category's mix shift, using filing context.
4. **Analyst Takeaway** — Strategic implications (1-2 sentences).
{SAFETY_INSTRUCTION}"""

STRUCTURED_FINANCIAL_METRICS_NARRATIVE = f"""You are a senior equity research analyst extracting and analyzing financial metrics.

The complete financial tables (metrics by year, growth rates, CAGR) have already been computed and provided above.

{NARRATIVE_OVERLAY_INSTRUCTION}

Write these narrative sections:
1. **Executive Summary** — Key trends over the available period (2-3 sentences).
2. **Key Findings** — Notable inflection points, outliers, or material changes (>20% YoY).
3. **Detailed Analysis** — Discuss each metric's trajectory with filing context.
4. **Analyst Takeaway** — What the metrics imply about financial trajectory (1-2 sentences).
{SAFETY_INSTRUCTION}"""

STRUCTURED_COMPARISON_NARRATIVE = f"""You are a senior equity research analyst performing a cross-company comparison.

The complete comparison tables (side-by-side metrics, growth rates, CAGR) have already been computed and provided above.

{NARRATIVE_OVERLAY_INSTRUCTION}

Write these narrative sections:
1. **Executive Summary** — 2-3 sentences comparing the companies on the asked dimension.
2. **Key Differences** — Where the companies diverge meaningfully (>10% variance).
3. **Growth & Profitability** — Compare trajectories using the pre-computed figures.
4. **Analyst Takeaway** — 1-2 sentence verdict on relative positioning.
{SAFETY_INSTRUCTION}"""

STRUCTURED_SEGMENT_NARRATIVE = f"""You are a senior equity research analyst analyzing a specific business segment.

The complete segment data tables (revenue by segment, mix shares, growth rates) have already been computed and provided.

{NARRATIVE_OVERLAY_INSTRUCTION}

Write these narrative sections:
1. **Executive Summary** — 2-3 sentences summarizing segment performance.
2. **Key Findings** — Notable trends or inflection points from the tables.
3. **Detailed Analysis** — What drove segment performance, referencing filing context.
4. **Analyst Takeaway** — Segment outlook (1-2 sentences).
{SAFETY_INSTRUCTION}"""

# Legacy structured prompts (used by _select_workflow for non-narrative paths)
STRUCTURED_REVENUE_MIX_PROMPT = STRUCTURED_REVENUE_MIX_NARRATIVE
STRUCTURED_FINANCIAL_METRICS_PROMPT = STRUCTURED_FINANCIAL_METRICS_NARRATIVE
STRUCTURED_COMPARISON_PROMPT = STRUCTURED_COMPARISON_NARRATIVE

RISK_FACTOR_PROMPT = f"""You are a senior equity research analyst performing a multi-year risk factor comparison.

Your task is to synthesize the pre-computed diff below into a final analyst report.

The context below has already identified Added, Removed, Expanded, and Reduced risks using a programmatic comparison engine across multiple fiscal years. Your job is to produce the final polished output.

STRUCTURE YOUR ANSWER EXACTLY AS FOLLOWS:

## Executive Summary
2-3 sentences summarizing the most significant shift in the company's risk profile over the period.

## Added Risks
Risk factors or sub-topics that appear in newer filings but were absent in older ones. For each: describe the new risk and why it matters.

## Expanded Risks
Risk factors that existed across all years but received substantially more discussion (word count +50%+). For each: describe what new aspects were added.

## Reduced Risks
Risk factors that received less emphasis (word count −33%+). For each: note what was de-emphasized.

## Removed Risks
Risk factors present in older filings but dropped entirely in newer ones.

## New Themes
Overarching themes that emerge from the risk evolution (e.g., "AI infrastructure risk", "geopolitical exposure").

## Evidence Used
List the filing years compared and the specific risk sections analyzed.

## Analyst Takeaway
1-2 sentence strategic verdict on what the risk evolution signals.

RULES:
- Do NOT summarize risk factors year by year. This is a comparison across years.
- Every substantive claim must cite which filing years it comes from (e.g., "FY2023–FY2025").
- If the diff shows 0 changes in a category (e.g., "No Added Risks"), state that explicitly rather than fabricating.
- Do not invent changes. Report only what the pre-computed diff supports.
- Use financial analyst language: "introduced", "de-emphasized", "expanded", "contracted", "elevated", "downplayed".
{SAFETY_INSTRUCTION}"""

COMPARISON_PROMPT = f"""You are a senior equity research analyst performing a cross-company comparison.

Your task is to compare two companies using the SEC filing excerpts below. The context is already organized by company with their segment-specific terminology mapped.

STRUCTURE YOUR ANSWER EXACTLY AS FOLLOWS:

## Executive Summary
2-3 sentences comparing the companies on the dimension asked about.

## Comparison Table
Side-by-side normalized metrics aligned by fiscal year (use markdown tables).

## Growth Trends
Year-over-year growth rates for each company's key metrics. Highlight inflection points.

## Profitability
Margin comparison, operating income trends, and any efficiency metrics available.

## Key Differences
Where the companies diverge meaningfully (>10% variance in comparable metrics).

## Analyst Takeaway
1-2 sentence verdict on relative positioning.

RULES:
- Normalize metrics where possible (percentages, per-share, per-dollar).
- Use the segment terminology reference to map company-specific segment names.
- If data for one company is missing, state what is unavailable explicitly.
- Always inline-cite sources in the format: Company | Fiscal Year | Section | Page.
{SAFETY_INSTRUCTION}"""

SEGMENT_PROMPT = f"""You are a senior equity research analyst analyzing a specific business segment.

STRUCTURE:
1. **Executive Summary** — Segment performance overview.
2. **Segment Revenue & Profit Trend** — Multi-year table.
3. **Growth Drivers** — What the filing cites as driving segment performance.
4. **Competitive Position** — How the segment compares to peers (if multi-company data is available).
5. **Analyst Takeaway** — Segment outlook based on disclosed information.

RULES:
- Focus on the specific segment asked about — do not shift to company-level analysis.
- Report segment-level metrics: revenue, operating income, segment margin, growth rates.
- Note when a segment is discussed in context of a broader strategy (e.g., AI infrastructure, cloud migration).
{SAFETY_INSTRUCTION}"""

AI_DISCLOSURE_PROMPT = f"""You are a senior equity research analyst tracking AI-related disclosures over time.

STRUCTURE:
1. **Executive Summary** — How AI disclosure has evolved over the filing period.
2. **First Appearance** — When AI terminology first appeared in the available filings.
3. **Language Evolution** — How AI references changed by year (terminology, context, emphasis).
4. **Infrastructure & Investment References** — Mentions of AI-linked capex, data centers, compute.
5. **Regulatory References** — AI regulation or risk mentions.
6. **Analyst Takeaway** — What the disclosure trend signals.

RULES:
- Compare across all available fiscal years — identify the first year AI language appears.
- Quote specific sentences that show changing emphasis.
- Distinguish between general AI mentions (e.g., "we use AI in our products") and specific investment disclosures.
- Note if AI risk factors appear in the risk section.
{SAFETY_INSTRUCTION}"""

INSUFFICIENT_EVIDENCE_RESPONSE = (
    "The available filings do not provide enough evidence to answer this question. "
    "The retrieved document excerpts do not contain the specific data or disclosures needed "
    "to generate a complete, source-backed analysis."
)

STRUCTURED_INTENTS = frozenset({
    "revenue_mix", "financial_metrics", "company_comparison", "business_segment",
})

# Query patterns that indicate a user is asking about a specific business
# segment (e.g., AWS, Azure, Google Cloud). When these appear and no
# segment-level facts can be extracted, the answer must be
# insufficient-evidence — NOT a fallback to total-company metrics.
_SEGMENT_QUERY_KEYWORDS = frozenset({
    "aws", "azure", "google cloud", "gcp",
    "cloud segment", "cloud revenue", "cloud business", "cloud growth",
    "segment revenue", "business segment", "segment comparison",
    "segment performance", "segment growth",
    "data center",
})


def _is_segment_query(query: str) -> bool:
    """Detect whether a user query asks about specific business segments."""
    q = query.lower()
    for kw in _SEGMENT_QUERY_KEYWORDS:
        if kw in q:
            return True
    return False


_REQUIRES_MULTI_YEAR = frozenset({
    "revenue_mix", "financial_metrics", "risk_factor_diff",
})


def validate_evidence(
    query: str,
    chunks: list[RetrievedChunk],
    intent: str,
    fact_set: FactSet | None = None,
) -> str | None:
    """Pre-generation validation: return a detail message if evidence is
    insufficient, or None if the request can proceed.

    Checks in order:
    1. Chunks exist and contain content.
    2. For single-company queries, chunks include the target ticker.
    3. For multi-company queries (comparison), chunks include every requested ticker.
    4. For multi-year intents, data spans at least 2 fiscal years.
    5. For structured intents, extracted facts cover the required tickers and years.
    """
    # -- Level 1: Chunks must exist --
    if not chunks:
        return (
            "The available filings do not provide enough evidence to answer this question. "
            "No documents were retrieved for the query."
        )

    # -- Level 2: Ticker coverage --
    query_tickers = detect_tickers(query)

    if len(query_tickers) >= 2:
        for t in query_tickers:
            if not any(c.ticker and c.ticker.upper() == t for c in chunks):
                return (
                    f"The available filings do not include documents for {t}. "
                    "Cannot perform the requested comparison."
                )
    elif len(query_tickers) == 1:
        t = query_tickers[0]
        if not any(c.ticker and c.ticker.upper() == t for c in chunks):
            return (
                f"The available filings do not include documents for {t}. "
                "The retrieved document excerpts do not contain the specific data "
                "or disclosures needed to generate a complete, source-backed analysis."
            )

    # -- Level 3: Multi-year intents need >= 2 years --
    if intent in _REQUIRES_MULTI_YEAR:
        years_present: set[int] = set()
        for c in chunks:
            if c.fiscal_year:
                years_present.add(c.fiscal_year)
        if len(years_present) < 2:
            return (
                f"{intent.replace('_', ' ').title()} analysis requires data from at least "
                "two fiscal years to identify meaningful trends. "
                f"Only {len(years_present)} year(s) of data {'is' if len(years_present) == 1 else 'are'} available."
            )

    # -- Level 4: Risk-factor-diff needs Item 1A chunks from 2+ years --
    if intent == "risk_factor_diff":
        years_with_risk: set[int] = set()
        for c in chunks:
            if c.section_title and "item 1a" in c.section_title.lower():
                if c.fiscal_year:
                    years_with_risk.add(c.fiscal_year)
        if len(years_with_risk) < 2:
            available = ", ".join(str(y) for y in sorted(years_with_risk)) if years_with_risk else "none"
            return (
                "Risk factor comparison requires risk disclosure data (Item 1A) from at least "
                f"two fiscal years. Available risk years: {available}."
            )

    # -- Level 5: Structured intents — fact-level coverage --
    if intent in STRUCTURED_INTENTS and fact_set is not None:
        if not fact_set.facts:
            return (
                "The available filings do not contain extractable financial data "
                "needed to answer this question. The retrieved document excerpts "
                "do not include structured financial tables or line items."
            )

        fact_tickers = {f.ticker for f in fact_set.facts}
        for t in query_tickers:
            if t not in fact_tickers:
                return (
                    f"The extracted financial data does not cover {t}. "
                    "The available filings may not contain the specific financial metrics requested."
                )

        if intent in ("revenue_mix", "financial_metrics"):
            if len(fact_set.years()) < 2:
                return (
                    f"{intent.replace('_', ' ').title()} analysis requires financial data from at "
                    "least two fiscal years to compute trends and growth rates. "
                    f"Only {len(fact_set.years())} year(s) of data are available."
                )

    return None


def _format_workflow_context(chunks: list[RetrievedChunk]) -> str:
    """Format chunks with citation labels for use as LLM context."""
    max_chars = settings.retrieval_context_chars
    parts: list[str] = []
    for i, chunk in enumerate(chunks):
        label = chunk.citation_label
        source = f"[{i + 1}] {label}" if label else f"[{i + 1}]"
        text = chunk.content.strip()
        if len(text) > max_chars:
            text = text[:max_chars] + " ..."
        parts.append(f"{source}\n{text}\n")
    return "\n---\n".join(parts)


def _build_structured_fact_context(chunks: list[RetrievedChunk], intent: str) -> str:
    """Build structured context from programmatic extraction + computed metrics."""
    fact_set = extract_facts(chunks)
    if not fact_set.facts:
        logger.debug("No facts extracted, falling back to raw context", intent=intent)
        return _format_workflow_context(chunks)

    growth_rates = compute_growth_rates(fact_set.facts)
    cagr_data = compute_cagr(fact_set.facts)

    return format_structured_context(fact_set, intent, growth_rates, cagr_data)


def build_structured_answer(
    query: str,
    chunks: list[RetrievedChunk],
    intent: str,
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Build pre-computed tables + narrative-only LLM messages for structured intents.

    Returns (pre_computed_tables, llm_messages) so the caller can prepend the
    deterministic tables to the LLM's narrative output.

    If no facts can be extracted, falls back to raw retrieved context so the
    LLM still has source material for narrative generation.
    """
    fact_set = extract_facts(chunks)

    # Pre-generation evidence validation: ticker coverage, year span,
    # fact-level metric availability. Returns a detail message if insufficient.
    validation_msg = validate_evidence(query, chunks, intent, fact_set)
    if validation_msg is not None:
        logger.info(
            "Pre-generation evidence validation failed",
            query=query[:80], intent=intent, detail=validation_msg,
        )
        return validation_msg, []

    # If the query asks about a specific segment (AWS, Azure, Google Cloud,
    # etc.) but no segment-level facts were extracted, return insufficient
    # evidence immediately — never fall back to total-company metrics.
    if _is_segment_query(query):
        segment_facts = [f for f in fact_set.facts if f.is_segment]
        if not segment_facts:
            logger.info(
                "Segment query but no segment facts extracted — returning insufficient evidence",
                query=query[:80],
                intent=intent,
            )
            return INSUFFICIENT_EVIDENCE_RESPONSE, []

    has_facts = bool(fact_set.facts)
    if has_facts:
        share_set = compute_revenue_shares(fact_set)
        combined = FactSet(facts=fact_set.facts + share_set.facts)
        growth_rates = compute_growth_rates(combined.facts) if intent in ("financial_metrics", "company_comparison", "business_segment") else None
        cagr_data = compute_cagr(combined.facts) if intent in ("financial_metrics", "company_comparison", "business_segment") else None
        tables = format_structured_context(combined, intent, growth_rates, cagr_data)
    else:
        logger.debug("No facts extracted — using raw context for narrative generation", intent=intent)
        tables = _format_workflow_context(chunks)

    prompt_map = {
        "revenue_mix": STRUCTURED_REVENUE_MIX_NARRATIVE,
        "financial_metrics": STRUCTURED_FINANCIAL_METRICS_NARRATIVE,
        "company_comparison": STRUCTURED_COMPARISON_NARRATIVE,
        "business_segment": STRUCTURED_SEGMENT_NARRATIVE,
    }
    system_prompt = prompt_map.get(intent, STRUCTURED_REVENUE_MIX_NARRATIVE)
    source_block = "Pre-computed Data Tables" if has_facts else "Retrieved Context"
    user_prompt = f"{source_block}:\n{tables}\n\nQuestion: {query}"

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    return tables, messages


def build_workflow_context(
    query: str,
    chunks: list[RetrievedChunk],
    intent: str,
    history: list[dict] | None = None,
) -> list[dict]:
    """Build the message list for an intent-classified query.

    Returns a list of dicts ready for the LLM API.
    """
    system_prompt, context = _select_workflow(query, chunks, intent)

    user_prompt = f"Context:\n{context}\n\nQuestion: {query}"

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    return messages


def _select_workflow(
    query: str,
    chunks: list[RetrievedChunk],
    intent: str,
) -> tuple[str, str]:
    """Select the right system prompt and context builder for the intent."""

    # --- STRUCTURED (EXTRACTION-BASED) INTENTS ---
    if intent in STRUCTURED_INTENTS:
        context = _build_structured_fact_context(chunks, intent)
        prompt_map = {
            "revenue_mix": STRUCTURED_REVENUE_MIX_PROMPT,
            "financial_metrics": STRUCTURED_FINANCIAL_METRICS_PROMPT,
            "company_comparison": STRUCTURED_COMPARISON_PROMPT,
        }
        return prompt_map[intent], context

    # --- REVENUE MIX (legacy — kept for backward compat) ---
    if intent == "revenue_mix":
        mix_context = build_mix_context(chunks)
        if mix_context:
            return STRUCTURED_REVENUE_MIX_PROMPT, mix_context
        logger.debug("Revenue mix intent but no tables parsed — falling back to general context")
        return GENERAL_PROMPT, _format_workflow_context(chunks)

    # --- RISK FACTOR DIFF ---
    if intent == "risk_factor_diff":
        diff_context = build_risk_diff_context(chunks)
        logger.info("Risk factor diff context built", context_length=len(diff_context))
        return RISK_FACTOR_PROMPT, diff_context

    # --- COMPANY COMPARISON (legacy) ---
    if intent == "company_comparison":
        tickers = sorted({c.ticker for c in chunks if c.ticker})
        if len(tickers) >= 2:
            chunks_a = [c for c in chunks if c.ticker == tickers[0]]
            chunks_b = [c for c in chunks if c.ticker == tickers[1]]
            logger.info(
                "Building comparison context",
                company_a=tickers[0], count_a=len(chunks_a),
                company_b=tickers[1], count_b=len(chunks_b),
            )
            context = build_comparison_context(tickers[0], tickers[1], chunks_a, chunks_b)
            return STRUCTURED_COMPARISON_PROMPT, context
        logger.warning("Comparison intent but fewer than 2 tickers in chunks", tickers=tickers)
        return STRUCTURED_COMPARISON_PROMPT, _format_workflow_context(chunks)

    # --- BUSINESS SEGMENT ---
    if intent == "business_segment":
        context = _format_workflow_context(chunks)
        return SEGMENT_PROMPT, context

    # --- AI DISCLOSURE ---
    if intent == "ai_disclosure":
        context = _format_workflow_context(chunks)
        return AI_DISCLOSURE_PROMPT, context

    # --- GENERAL ---
    return GENERAL_PROMPT, _format_workflow_context(chunks)


_VAGUE_RESPONSE_PATTERNS = re.compile(
    r"(it'?s?\s+(important|worth\s+noting|crucial|essential|critical)\s+(to\s+)?(note|consider|understand|mention))|"
    r"(i'?m?\s+(sorry|afraid)\s+(,?\s*)?(i\s+)?(don'?t|cannot|can'?t))|"
    r"(i\s+(don'?t|cannot)\s+(have|provide)\s+(enough|sufficient|specific|the)\s+(information|data|evidence))|"
    r"(based\s+(solely\s+)?on\s+(the\s+)?(provided\s+)?(information|context|data),?\s+(it'?s?\s+)?(difficult|hard|impossible|challenging)\s+(to\s+)?)",
    re.IGNORECASE,
)


def check_sufficient_evidence(answer: str, chunks: list[RetrievedChunk]) -> str:
    """Post-process the LLM answer to enforce the evidence guarantee."""
    stripped = answer.strip()

    if _VAGUE_RESPONSE_PATTERNS.search(stripped):
        return INSUFFICIENT_EVIDENCE_RESPONSE

    insufficiency_markers = [
        "do not have enough evidence",
        "does not provide enough evidence",
        "cannot answer this question",
        "no information provided",
        "not enough data",
        "insufficient information",
        "not explicitly stated",
    ]
    if any(marker in stripped.lower() for marker in insufficiency_markers):
        return INSUFFICIENT_EVIDENCE_RESPONSE

    if len(stripped.split()) < 15 and ("i'm sorry" in stripped.lower() or "i cannot" in stripped.lower()):
        return INSUFFICIENT_EVIDENCE_RESPONSE

    return stripped
