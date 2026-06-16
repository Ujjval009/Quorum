from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import logger
from app.domain.embeddings import generate_embedding

TICKER_ALIASES: dict[str, str] = {
    "apple": "AAPL",
    "aapl": "AAPL",
    "amazon": "AMZN",
    "amzn": "AMZN",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "googl": "GOOGL",
}

_FY_PATTERN = re.compile(r"(?:fy\s*)?(20(?:2[1-5]))", re.IGNORECASE)


def extract_filters(query: str) -> tuple[list[str], list[int]]:
    """Extract ticker(s) and fiscal year(s) from a query string.

    Returns:
        (tickers, fiscal_years) — each is a list of unique values found.
    """
    q = query.lower()
    tickers: list[str] = []
    seen_tickers: set[str] = set()
    for alias, ticker in TICKER_ALIASES.items():
        if alias in q and ticker not in seen_tickers:
            seen_tickers.add(ticker)
            tickers.append(ticker)

    fiscal_years = sorted({
        int(m) for m in _FY_PATTERN.findall(query)
    })

    return tickers, fiscal_years


COMPANY_TICKER_MAP: dict[str, str] = {
    "apple": "AAPL",
    "aapl": "AAPL",
    "iphone": "AAPL",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "azure": "MSFT",
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "amazon": "AMZN",
    "amzn": "AMZN",
    "aws": "AMZN",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "googl": "GOOGL",
    "goog": "GOOGL",
    "gcp": "GOOGL",
}


def detect_ticker(query: str) -> str | None:
    """Extract a company ticker from a query string, or None if no match."""
    lowered = query.lower()
    for name, ticker in COMPANY_TICKER_MAP.items():
        if re.search(r"\b" + re.escape(name) + r"\b", lowered):
            return ticker
    return None


def detect_tickers(query: str) -> list[str]:
    """Extract ALL company tickers from a query string.

    Returns a list of unique tickers found, preserving detection order.
    Used by the comparison engine to identify both companies in a comparison query.
    """
    lowered = query.lower()
    found: dict[str, str] = {}
    for name, ticker in COMPANY_TICKER_MAP.items():
        if re.search(r"\b" + re.escape(name) + r"\b", lowered):
            found[name] = ticker
    # Deduplicate by ticker, preserving first name matched per ticker
    seen: set[str] = set()
    result: list[str] = []
    for name, ticker in found.items():
        if ticker not in seen:
            seen.add(ticker)
            result.append(ticker)
    return result


class RetrievedChunk:
    def __init__(
        self,
        chunk_id: str,
        document_id: str,
        content: str,
        page_number: int | None,
        chunk_index: int,
        score: float,
        source: str,
        intent_boost: float = 1.0,
        ticker: str | None = None,
        fiscal_year: int | None = None,
        company_name: str | None = None,
        section_title: str | None = None,
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.content = content
        self.page_number = page_number
        self.chunk_index = chunk_index
        self.score = score
        self.source = source
        self.intent_boost = intent_boost
        self.ticker = ticker
        self.fiscal_year = fiscal_year
        self.company_name = company_name
        self.section_title = section_title
        self.segment: str | None = None  # Business segment (populated by comparison engine)

    @property
    def citation_label(self) -> str:
        parts = []
        if self.ticker and self.fiscal_year:
            parts.append(f"{self.ticker} FY{self.fiscal_year}")
        elif self.ticker:
            parts.append(self.ticker)
        if self.section_title:
            parts.append(self.section_title)
        if self.page_number:
            parts.append(f"p.{self.page_number}")
        return " · ".join(parts) if parts else ""

    def __repr__(self) -> str:
        return f"<RetrievedChunk id={self.chunk_id} score={self.score:.3f} source={self.source}>"


_INTENT_PATTERNS: dict[str, set[str]] = {
    "revenue_mix": {
        "revenue mix", "product mix", "segment mix", "revenue share",
        "revenue shift", "mix shift", "product contribution",
        "revenue breakdown", "breakdown of revenue",
        "revenue composition", "revenue split", "net sales split",
        "sales mix", "category mix", "revenue by category",
        "product revenue", "services revenue",
        "net sales by category",
        "how has revenue", "how did revenue",
        "revenue trends", "revenue trend",
        "what percentage of", "percentage of revenue",
        "how much comes from",
    },
    "company_comparison": {
        "compare", "comparison", "vs ", " versus ",
        "difference between", "compared to", "compared with",
        "which company", "who has better", "who is winning",
        "benchmark", "peer comparison",
    },
    "risk_factor_diff": {
        "risk factor", "risk-factor", "risk disclosure", "item 1a",
        "what changed in risk", "risk comparison",
        "added risk", "removed risk", "risk language",
        "risk section", "risk update", "risk change",
        "new risk", "updated risk",
    },
    "financial_metrics": {
        "operating margin", "gross margin", "net margin",
        "profit margin", "free cash flow", "fcf",
        "capital expenditure", "capex", "capital expenditures",
        "purchase commitment", "buyback", "share repurchase",
        "dividend", "roi", "return on", "effective tax rate",
        "tax rate", "diluted eps", "earnings per share",
        "revenue growth", "net income", "operating income",
        "cost of revenue", "r&d expense", "selling general",
        "sga", "s&a", "depreciation", "amortization",
        "balance sheet", "cash flow", "liquidity",
        "revenue exposure", "geographic revenue",
        "year-over-year change",
        "cagr", "compound annual",
        "revenue in fy", "revenue in fiscal",
    },
    "business_segment": {
        "data center", "cloud business", "cloud revenue",
        "aws", "azure", "google cloud", "gcp",
        "services segment", "segment revenue",
        "segment profit", "business segment",
        "segment operating", "reportable segment",
        "revenue by segment", "segment breakdown",
        "revenue per segment", "by segment",
        "segment results",
    },
    "ai_disclosure": {
        "ai disclosure", "artificial intelligence",
        "machine learning", "generative ai", "gen ai",
        "ai infrastructure", "ai regulation", "ai risk",
        "llm", "large language model", "deep learning",
        "neural network", "ai capabilities", "ai investment",
        "ai strategy", "ai mention", "ai references",
        "ai-related", "ai related", "investments in ai",
        "ai spending", "ai capex", "spending on ai",
        "ai expenditure", "ai platform",
    },
}

_SECTION_BOOST_MAP: dict[str, list[tuple[str, float]]] = {
    "revenue_mix": [
        ("results of operations", 2.5),
        ("management discussion", 2.0),
        ("item 7", 2.0),
        ("item 8", 1.5),
        ("financial condition", 1.5),
    ],
    "company_comparison": [
        ("results of operations", 2.5),
        ("item 7", 2.5),
        ("management discussion", 2.0),
        ("item 8", 1.5),
        ("financial statements", 1.5),
    ],
    "risk_factor_diff": [
        ("item 1a", 3.0),
        ("risk factors", 2.5),
    ],
    "financial_metrics": [
        ("results of operations", 2.5),
        ("item 7", 2.5),
        ("item 8", 2.0),
        ("management discussion", 2.0),
        ("financial statements", 1.5),
        ("financial condition", 1.5),
        ("item 1", 1.5),
        ("item 1a", 1.5),
        ("business", 1.3),
    ],
    "business_segment": [
        ("business segment", 2.5),
        ("results of operations", 2.0),
        ("item 1", 1.5),
        ("item 7", 1.5),
    ],
    "ai_disclosure": [
        ("item 1", 2.0),
        ("business", 1.8),
        ("item 7", 1.5),
        ("risk factors", 1.5),
        ("item 1a", 1.5),
    ],
}

_INTENT_BOOST_PHRASES: dict[str, list[tuple[str, float]]] = {
    "revenue_mix": [
        ("disaggregated by significant products and services", 1.5),
        ("net sales by category", 2.0),
        ("products and services performance", 2.0),
    ],
    "company_comparison": [
        ("consolidated results of operations", 1.5),
        ("results of operations", 1.5),
        ("net income", 1.3),
        ("operating income", 1.3),
        ("revenue", 1.2),
        ("net sales", 1.2),
    ],
    "risk_factor_diff": [
        ("risk factors", 2.5),
        ("item 1a", 2.5),
        ("cautionary statement", 1.5),
    ],
    "financial_metrics": [
        ("results of operations", 1.5),
        ("consolidated results", 1.5),
        ("financial condition", 1.3),
        ("liquidity and capital resources", 1.3),
        ("contractual obligations", 1.3),
        ("critical accounting", 1.2),
    ],
    "business_segment": [
        ("segment results", 2.0),
        ("business segment", 1.8),
        ("reportable segments", 1.8),
        ("aws", 2.0),
        ("azure", 2.0),
        ("intelligent cloud", 2.0),
        ("google cloud", 2.0),
        ("data center", 1.5),
        ("cloud revenue", 1.5),
        # ── Phase 3: Cloud boost phrases ──
        ("cloud services", 1.8),
        ("cloud infrastructure", 1.8),
        ("cloud computing", 1.7),
        ("cloud platform", 1.7),
        ("cloud offerings", 1.6),
    ],
    "ai_disclosure": [
        ("risk factors", 1.5),
        ("business", 1.2),
        ("management discussion", 1.5),
        ("item 1", 1.2),
        ("item 7", 1.5),
        ("artificial intelligence", 2.0),
        ("generative ai", 2.0),
        ("accelerated computing", 2.0),
        ("capital expenditures", 1.8),
        ("ai infrastructure", 2.0),
        ("data center", 1.5),
        ("ai", 1.5),
        # ── Phase 3: Enhanced AI & Capex boost phrases ──
        ("large language model", 2.0),
        ("llm", 2.0),
        ("machine learning", 1.9),
        ("deep learning", 1.9),
        ("neural network", 1.8),
        ("ai model", 1.8),
        ("ai capability", 1.7),
        ("ai investment", 1.8),
        ("ai-related", 1.7),
        ("capex", 1.9),
        ("capital expenditure", 1.9),
        ("capital spending", 1.8),
        ("capex spending", 1.8),
        ("capital intensity", 1.7),
        ("infrastructure investment", 1.7),
        ("gpu", 1.8),
        ("processor", 1.6),
        ("tensor", 1.7),
    ],
}


def is_single_company_query(query: str) -> bool:
    """Check if the query mentions exactly one company."""
    tickers = detect_tickers(query)
    return len(tickers) == 1


def filter_chunks_by_ticker(
    chunks: list[RetrievedChunk],
    ticker: str | None,
) -> list[RetrievedChunk]:
    """Retain only chunks belonging to the given ticker.

    Returns chunks unchanged if ticker is None (no company scoping needed).
    """
    if ticker is None:
        return chunks
    ticker_upper = ticker.upper()
    return [c for c in chunks if c.ticker and c.ticker.upper() == ticker_upper]


def detect_intent(query: str) -> str:
    lowered = query.lower()
    tickers_found = detect_tickers(query)

    # Check each intent's patterns — first match wins
    # Ordered from most specific to most general
    intent_order = [
        "revenue_mix",
        "risk_factor_diff",
        "company_comparison",
        "financial_metrics",
        "ai_disclosure",
        "business_segment",
    ]

    for intent in intent_order:
        patterns = _INTENT_PATTERNS.get(intent, set())
        for pattern in patterns:
            if pattern in lowered:
                # Company comparison needs 2+ unique companies or explicit compare words
                if intent == "company_comparison":
                    matched_tickers = set()
                    for name, ticker in COMPANY_TICKER_MAP.items():
                        if re.search(r"\b" + re.escape(name) + r"\b", lowered):
                            matched_tickers.add(ticker)
                    if len(matched_tickers) < 2 and "vs" not in lowered and " versus " not in lowered:
                        continue

                logger.debug("Detected intent", intent=intent, pattern=pattern)
                return intent

    # Fallback: if 2+ unique tickers are named, classify as comparison
    if len(tickers_found) >= 2:
        logger.debug("Detected intent from multi-ticker", intent="company_comparison", tickers=tickers_found)
        return "company_comparison"

    return "general"


def _apply_intent_boost(chunks: list[RetrievedChunk], intent: str) -> list[RetrievedChunk]:
    content_boost_phrases = _INTENT_BOOST_PHRASES.get(intent)
    section_boost_phrases = _SECTION_BOOST_MAP.get(intent)

    if not content_boost_phrases and not section_boost_phrases:
        return chunks

    for chunk in chunks:
        content_lower = chunk.content.lower()
        section_lower = (chunk.section_title or "").lower()
        max_boost = 1.0

        if content_boost_phrases:
            for phrase, multiplier in content_boost_phrases:
                if phrase in content_lower:
                    max_boost = max(max_boost, multiplier)

        if section_boost_phrases:
            for phrase, multiplier in section_boost_phrases:
                if phrase in section_lower:
                    max_boost = max(max_boost, multiplier)

        if max_boost > 1.0:
            chunk.score *= max_boost
            chunk.intent_boost = max_boost
    chunks.sort(key=lambda c: c.score, reverse=True)
    return chunks


def _vector_search(
    query_embedding: list[float],
    db: Session,
    top_k: int | None = None,
    tickers: list[str] | None = None,
    fiscal_years: list[int] | None = None,
) -> list[RetrievedChunk]:
    k = top_k or settings.retrieval_top_k
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    filters: list[str] = [
        "dc.embedding IS NOT NULL",
        "sd.source_type = 'sec_filing'",
    ]
    params: dict = {"embedding": embedding_str, "top_k": k}

    if tickers:
        filters.append("sd.ticker = ANY(:tickers)")
        params["tickers"] = tickers

    if fiscal_years:
        filters.append("sd.fiscal_year = ANY(:fiscal_years)")
        params["fiscal_years"] = fiscal_years

    where_clause = " AND ".join(filters)
    sql = text(f"""
        SELECT
            dc.id,
            dc.document_id,
            dc.content,
            dc.page_number,
            dc.chunk_index,
            dc.section_title,
            sd.ticker,
            sd.fiscal_year,
            sd.company_name,
            1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id
        WHERE {where_clause}
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """)

    results = db.execute(sql, params).fetchall()
    logger.debug("Vector search results", count=len(results), top_k=k)

    if not results:
        return []

    return [
        RetrievedChunk(
            chunk_id=str(row.id),
            document_id=str(row.document_id),
            content=row.content,
            page_number=row.page_number,
            chunk_index=row.chunk_index,
            score=float(row.similarity),
            source="vector",
            ticker=row.ticker,
            fiscal_year=row.fiscal_year,
            company_name=row.company_name,
            section_title=row.section_title,
        )
        for row in results
    ]


_STOP_WORDS: set[str] = {
    "how", "has", "its", "over", "the", "last", "three", "what", "would", "could",
    "should", "about", "been", "were", "was", "are", "have", "had", "does", "much",
    "many", "some", "any", "all", "each", "every", "more", "most", "other", "such",
    "than", "that", "this", "these", "those", "with", "without", "from", "into",
    "onto", "upon", "after", "before", "during", "through", "between", "under",
    "above", "below", "then", "also", "just", "very", "too", "can", "will", "may",
    "might", "must", "shall", "should", "need", "like", "compared", "compare",
}

_SYNONYM_MAP: dict[str, set[str]] = {
    "revenue": {"sales"},
    "sales": {"revenue"},
    "profit": {"income", "margin"},
    "income": {"profit"},
    "margin": {"profit"},
    "year": {"annual"},
    "annual": {"year"},
    "quarter": {"quarterly"},
    "quarterly": {"quarter"},
    "employee": {"employees", "headcount"},
    "workforce": {"employees", "headcount"},
}


def _build_fts_query(query: str, max_terms: int = 5) -> str | None:
    """Build an OR'd tsquery string with prefix matching from query terms.

    Extracts meaningful terms, expands with financial synonyms, and takes
    the top N by length (preferring specific/long words). Each term uses
    ``:*`` suffix for prefix matching so partial words are found.
    """
    raw_terms: set[str] = set(
        re.findall(r"[a-zA-Z0-9]+", query.lower())
    )

    terms: set[str] = set()
    for t in raw_terms:
        if t in _STOP_WORDS or len(t) <= 2:
            continue
        terms.add(t)
        synonyms = _SYNONYM_MAP.get(t)
        if synonyms:
            terms.update(synonyms)

    ranked = sorted(terms, key=len, reverse=True)[:max_terms]
    if not ranked:
        return None
    return " | ".join(f"{t}:*" for t in ranked)


def _fts_search(
    query: str,
    db: Session,
    top_k: int | None = None,
    tickers: list[str] | None = None,
    fiscal_years: list[int] | None = None,
) -> list[RetrievedChunk]:
    k = top_k or settings.retrieval_top_k

    fts_query = _build_fts_query(query)
    if not fts_query:
        logger.debug("FTS query produced no terms", query=query[:80])
        return []

    filters: list[str] = [
        "to_tsvector('english', dc.content) @@ to_tsquery('english', :query)",
        "sd.source_type = 'sec_filing'",
    ]
    params: dict = {"query": fts_query, "top_k": k}

    if tickers:
        filters.append("sd.ticker = ANY(:tickers)")
        params["tickers"] = tickers

    if fiscal_years:
        filters.append("sd.fiscal_year = ANY(:fiscal_years)")
        params["fiscal_years"] = fiscal_years

    where_clause = " AND ".join(filters)
    sql = text(f"""
        SELECT
            dc.id,
            dc.document_id,
            dc.content,
            dc.page_number,
            dc.chunk_index,
            dc.section_title,
            sd.ticker,
            sd.fiscal_year,
            sd.company_name,
            ts_rank(
                to_tsvector('english', dc.content),
                to_tsquery('english', :query)
            ) AS rank
        FROM document_chunks dc
        JOIN source_documents sd ON sd.id = dc.document_id
        WHERE {where_clause}
        ORDER BY rank DESC
        LIMIT :top_k
    """)

    results = db.execute(sql, params).fetchall()
    logger.debug("FTS search results", count=len(results), top_k=k)

    if not results:
        return []

    return [
        RetrievedChunk(
            chunk_id=str(row.id),
            document_id=str(row.document_id),
            content=row.content,
            page_number=row.page_number,
            chunk_index=row.chunk_index,
            score=float(row.rank),
            source="fts",
            ticker=row.ticker,
            fiscal_year=row.fiscal_year,
            company_name=row.company_name,
            section_title=row.section_title,
        )
        for row in results
    ]


def _fuse_results(
    vector_results: list[RetrievedChunk],
    fts_results: list[RetrievedChunk],
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Fuse vector and FTS results with Reciprocal Rank Fusion (RRF).

    RRF assigns a combined score to each document based on its rank position
    in each result set, ensuring both semantic and keyword signals contribute.
    """
    k = top_k or settings.retrieval_top_k
    rrf_k = settings.retrieval_rrf_k

    combined: dict[str, RetrievedChunk] = {}

    def _rank(results: list[RetrievedChunk]) -> None:
        for rank, chunk in enumerate(results):
            rrf_score = 1.0 / (rrf_k + rank + 1)
            if chunk.chunk_id in combined:
                combined[chunk.chunk_id].score += rrf_score
            else:
                chunk.score = rrf_score
                combined[chunk.chunk_id] = chunk

    _rank(vector_results)
    _rank(fts_results)

    fused = sorted(combined.values(), key=lambda c: c.score, reverse=True)

    result = fused[:k]
    logger.debug("RRF fusion complete", input_vector=len(vector_results), input_fts=len(fts_results), output=len(result))
    return result


def hybrid_search(
    query: str,
    db: Session,
    top_k: int | None = None,
    ticker: str | None = None,
    search_depth: int | None = None,
) -> list[RetrievedChunk]:
    top_k = top_k or settings.retrieval_top_k
    search_depth = search_depth or settings.retrieval_search_depth

    intent = detect_intent(query)

    # ── Auto-extract metadata filters from query ────────────────────────
    query_tickers, query_years = extract_filters(query)

    # ── Determine effective filters ─────────────────────────────────────
    # Explicit ticker (from caller) takes precedence; otherwise use ALL
    # detected tickers so multi-ticker queries also get filtered.
    effective_tickers: list[str] | None = None
    if ticker:
        effective_tickers = [ticker]
    elif query_tickers:
        effective_tickers = query_tickers

    # Skip year filtering for intents that inherently require multi-year
    # data (revenue_mix, risk_factor_diff). For these, filtering to a
    # single year would starve the downstream analysis pipeline.
    _multi_year_intents = {"revenue_mix", "risk_factor_diff"}
    effective_years: list[int] | None = (
        query_years if query_years and intent not in _multi_year_intents else None
    )

    logger.info(
        "Hybrid search",
        query=query[:80],
        top_k=top_k,
        search_depth=search_depth,
        tickers=effective_tickers,
        fiscal_years=effective_years,
        intent=intent,
        query_tickers=query_tickers,
        query_years=query_years,
    )

    query_embedding = generate_embedding(query)

    vector_results = _vector_search(query_embedding, db, search_depth, effective_tickers, effective_years)
    fts_results = _fts_search(query, db, search_depth, effective_tickers, effective_years)

    vector_results = _apply_intent_boost(vector_results, intent)
    fts_results = _apply_intent_boost(fts_results, intent)

    fused = _fuse_results(vector_results, fts_results, top_k)

    # ── Post-fusion safety filter ───────────────────────────────────────
    # When filtering by specific tickers, double-check no wrong-company
    # chunks survive (defence in depth).
    if effective_tickers:
        ticker_set = {t.upper() for t in effective_tickers}
        before = len(fused)
        fused = [c for c in fused if c.ticker and c.ticker.upper() in ticker_set]
        if len(fused) < before:
            logger.debug(
                "Post-fusion ticker filter applied",
                tickers=effective_tickers, before=before, after=len(fused),
            )

    logger.info("Hybrid search complete", results=len(fused), query=query[:80], intent=intent)
    return fused
