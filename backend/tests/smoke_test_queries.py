"""Phase 8 — Smoke-test all 10 example queries from the client brief.

Validates:
  1. Intent detection classifies each query correctly
  2. Workflow routing selects the right prompt/context builder
  3. Ticker detection picks the right company/companies
  4. _build_workflow_context returns valid message structures

Run with: python -m pytest tests/smoke_test_queries.py -v
"""

from __future__ import annotations

import pytest

from app.domain.retrieval import detect_intent, detect_ticker, detect_tickers
from app.domain.workflows import _select_workflow
from app.domain.retrieval import RetrievedChunk


def _make_chunk(
    chunk_id: str = "c1",
    content: str = "Sample filing text.",
    ticker: str = "AAPL",
    fiscal_year: int = 2024,
    page: int = 1,
    section: str = "Item 7. Management's Discussion",
    score: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        content=content,
        page_number=page,
        chunk_index=0,
        score=score,
        source="test",
        ticker=ticker,
        fiscal_year=fiscal_year,
        section_title=section,
    )


EXAMPLE_QUERIES = [
    {
        "id": 1,
        "query": "Across Apple's 2021-2025 10-Ks, how did the revenue mix between iPhone, Services, Mac, iPad, and Wearables change, and which category appears to have contributed most to any mix shift?",
        "expected_intent": "revenue_mix",
        "expected_ticker": "AAPL",
        "expected_tickers": ["AAPL"],
        "expected_workflow_keywords": ["revenue mix", "share"],
    },
    {
        "id": 2,
        "query": "For Amazon, compare AWS operating income and margin against North America and International from 2021-2025. In which years did AWS appear to fund losses or weaker profitability elsewhere?",
        "expected_intent": "financial_metrics",
        "expected_ticker": "AMZN",
        "expected_tickers": ["AMZN"],
        "expected_workflow_keywords": ["financial"],
    },
    {
        "id": 3,
        "query": "How did NVIDIA describe demand drivers, customer concentration, and supply constraints for its Data Center business from fiscal 2021 through fiscal 2025?",
        "expected_intent": "business_segment",
        "expected_ticker": "NVDA",
        "expected_tickers": ["NVDA"],
        "expected_workflow_keywords": ["Segment Revenue & Profit", "business segment"],
    },
    {
        "id": 4,
        "query": "Across Microsoft's 2021-2025 filings, what changed in the way the company describes Azure, AI infrastructure, and cloud capacity constraints?",
        "expected_intent": "ai_disclosure",
        "expected_ticker": "MSFT",
        "expected_tickers": ["MSFT"],
    },
    {
        "id": 5,
        "query": "For Alphabet, how did Google Search, YouTube ads, Google Network, subscriptions/platforms/devices, and Google Cloud revenue trends differ across the available 10-Ks?",
        "expected_intent": "revenue_mix",
        "expected_ticker": "GOOGL",
        "expected_tickers": ["GOOGL"],
    },
    {
        "id": 6,
        "query": "Which of the five companies added, removed, or materially changed risk-factor language related to AI, cloud infrastructure, export controls, supply chain concentration, or regulation between 2021 and 2025?",
        "expected_intent": "risk_factor_diff",
        "expected_ticker": None,
        "expected_tickers": [],
    },
    {
        "id": 7,
        "query": "For Apple and NVIDIA, what do the filings say about supplier concentration or dependence on third-party manufacturing, and did the wording become more or less urgent over time?",
        "expected_intent": "company_comparison",
        "expected_ticker": "AAPL",
        "expected_tickers": ["AAPL", "NVDA"],
    },
    {
        "id": 8,
        "query": "Compare capital expenditures and purchase commitments for Microsoft, Alphabet, Amazon, and NVIDIA. What do the filings imply about the scale and timing of AI/cloud infrastructure investment?",
        "expected_intent": "company_comparison",
        "expected_ticker": "MSFT",
        "expected_tickers": ["MSFT", "GOOGL", "AMZN", "NVDA"],
    },
    {
        "id": 9,
        "query": "For each company, summarize the most important geographic revenue exposures disclosed in the latest 10-K, then identify any year-over-year changes that could matter to an analyst.",
        "expected_intent": "financial_metrics",
        "expected_ticker": None,
        "expected_tickers": [],
    },
    {
        "id": 10,
        "query": "If an analyst asks whether the filings prove that generative AI improved margins for any of these companies, what evidence exists in the corpus, and where should the bot refuse to infer beyond the filings?",
        "expected_intent": "ai_disclosure",
        "expected_ticker": None,
        "expected_tickers": [],
    },
]


class TestIntentDetection:
    @pytest.mark.parametrize("q", EXAMPLE_QUERIES, ids=lambda q: f"Q{q['id']}")
    def test_intent_detection(self, q: dict):
        intent = detect_intent(q["query"])
        assert intent == q["expected_intent"], (
            f"Q{q['id']}: expected intent={q['expected_intent']}, got={intent}"
        )

    @pytest.mark.parametrize("q", EXAMPLE_QUERIES, ids=lambda q: f"Q{q['id']}")
    def test_ticker_detection(self, q: dict):
        ticker = detect_ticker(q["query"])
        assert ticker == q["expected_ticker"], (
            f"Q{q['id']}: expected ticker={q['expected_ticker']}, got={ticker}"
        )

    @pytest.mark.parametrize("q", EXAMPLE_QUERIES, ids=lambda q: f"Q{q['id']}")
    def test_multi_ticker_detection(self, q: dict):
        tickers = detect_tickers(q["query"])
        assert set(tickers) == set(q["expected_tickers"]), (
            f"Q{q['id']}: expected tickers={q['expected_tickers']}, got={tickers}"
        )


_REVENUE_MIX_CONTENT = """Products and Services Performance
The following table shows net sales by category for 2024, 2023 and 2022.

2024 Change 2023 Change 2022
iPhone $ 205,489 29,984 26,694
Services $ 45,000 12,000 10,000
Mac $ 30,000 8,000 7,000
iPad $ 25,000 6,000 5,000
Wearables, Home and Accessories $ 20,000 4,000 3,000
Total Net Sales $ 325,489"""


class TestWorkflowRouting:
    @pytest.mark.parametrize("q", EXAMPLE_QUERIES, ids=lambda q: f"Q{q['id']}")
    def test_workflow_selects_correct_prompt(self, q: dict):
        content = _REVENUE_MIX_CONTENT if q["expected_intent"] == "revenue_mix" else "Sample filing text."
        sample_chunks = [
            _make_chunk(ticker="AAPL", fiscal_year=2024, content=content),
            _make_chunk(ticker="NVDA", fiscal_year=2024, content="Sample filing text."),
            _make_chunk(ticker="MSFT", fiscal_year=2024, content="Sample filing text."),
            _make_chunk(ticker="AMZN", fiscal_year=2024, content="Sample filing text."),
            _make_chunk(ticker="GOOGL", fiscal_year=2024, content="Sample filing text."),
        ]
        prompt, context = _select_workflow(q["query"], sample_chunks, q["expected_intent"])
        assert len(prompt) > 100, f"Q{q['id']}: prompt too short"
        assert len(context) > 0, f"Q{q['id']}: empty context"
        if "expected_workflow_keywords" in q:
            for kw in q["expected_workflow_keywords"]:
                assert kw in prompt or kw in context, (
                    f"Q{q['id']}: keyword '{kw}' not found in workflow output"
                )
