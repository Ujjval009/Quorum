from __future__ import annotations

import re

from app.core.logging import logger
from app.domain.retrieval import detect_intent, detect_tickers

_TICKER_TO_NAME: dict[str, str] = {
    "AAPL": "Apple",
    "AMZN": "Amazon",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "GOOGL": "Google",
}

_INTENT_LABELS: dict[str, str] = {
    "revenue_mix": "Revenue Mix Analysis",
    "financial_metrics": "Financial Overview",
    "company_comparison": "",
    "business_segment": "Segment Analysis",
    "risk_factor_diff": "Risk Factors",
    "ai_disclosure": "AI Analysis",
    "general": "",
}

# Key domain words to extract as topic from comparison queries
_TOPIC_KEYWORDS: list[str] = [
    "cloud", "aws", "azure", "gcp",
    "ai", "artificial intelligence",
    "revenue", "growth", "margin",
    "risk", "investment", "spending",
    "segment", "product", "service",
]


def generate_title(query: str) -> str:
    """Generate a short descriptive title (4–8 words) from the user's first query.

    Priority:
    1. Heuristic: ticker + intent → structured title
    2. Fallback: first 5 meaningful words of query
    3. Last resort: truncated query
    """
    title = _heuristic_title(query)
    if title:
        logger.debug("Generated chat title (heuristic)", title=title, query=query[:60])
        return title

    title = _truncate_title(query)
    logger.debug("Generated chat title (fallback)", title=title, query=query[:60])
    return title


def _heuristic_title(query: str) -> str | None:
    tickers = detect_tickers(query)
    companies = [_TICKER_TO_NAME.get(t) for t in tickers if _TICKER_TO_NAME.get(t)]
    intent = detect_intent(query)

    # Multi-company comparison: "Apple vs Microsoft"
    if intent == "company_comparison" and len(companies) >= 2:
        topic = _extract_comparison_topic(query, companies)
        if topic:
            return f"{companies[0]} vs {companies[1]} {topic}"
        return f"{companies[0]} vs {companies[1]}"

    # Single company + intent topic
    if len(companies) >= 1:
        label = _INTENT_LABELS.get(intent, "")
        if label:
            return f"{companies[0]} {label}"
        return companies[0]

    # Intent-only (no company detected)
    label = _INTENT_LABELS.get(intent, "")
    if label:
        return label

    return None


def _extract_comparison_topic(query: str, companies: list[str]) -> str | None:
    """Extract a topic keyword from a comparison query after removing company names.

    E.g. "Compare Microsoft and Amazon cloud growth" → "Cloud"
    """
    lowered = query.lower()
    for name in companies:
        for alias in (name.lower(), _TICKER_TO_NAME.get(name, "").lower()):
            lowered = lowered.replace(alias, "")

    for kw in _TOPIC_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", lowered):
            return kw.title()
    return None


def _truncate_title(query: str) -> str:
    """Fallback: take first 5 meaningful words."""
    STOP = frozenset({"a", "an", "the", "in", "of", "for", "to", "and", "or",
                      "is", "was", "what", "how", "does", "did", "are", "do",
                      "it", "its", "by", "on", "at", "with", "from", "as",
                      "be", "has", "had", "have", "been", "this", "that"})
    words = query.split()
    meaningful = [w for w in words if w.lower() not in STOP]
    if meaningful:
        title = " ".join(meaningful[:5])
        if len(title) > 60:
            title = title[:57] + "..."
        return title
    return query[:60] if len(query) > 60 else query
