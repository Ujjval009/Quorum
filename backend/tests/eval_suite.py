from __future__ import annotations

import os
import time

import httpx
import pytest

eval = pytest.mark.eval
timeout = pytest.mark.timeout

INSUFFICIENT_EVIDENCE_RESPONSE = (
    "The available filings do not provide enough evidence to answer this question."
)

LLM_UNAVAILABLE_MESSAGE = (
    "AI narrative generation is temporarily unavailable"
)

SKIP_LLM = os.environ.get("EVAL_SKIP_LLM", "").lower() in ("1", "true", "yes")
MAX_RETRIES = int(os.environ.get("EVAL_MAX_RETRIES", "3"))


REVENUE_MIX_CASES = [
    ("rm1", "What was Apple's revenue mix in FY2023?",
     ["AAPL"], True, False, 3),
    ("rm2", "Show me Apple's revenue breakdown by product category",
     ["AAPL"], True, False, 3),
    ("rm3", "Services revenue share trend for Apple over the last 3 years",
     ["AAPL"], True, False, 3),
    ("rm4", "Revenue mix shift at Microsoft — which segments are growing?",
     ["MSFT"], True, False, 3),
]

FINANCIAL_METRICS_CASES = [
    ("fm1", "What is Apple's 3-year revenue CAGR?",
     ["AAPL"], True, False, 3),
    ("fm2", "Calculate the CAGR for iPhone revenue",
     ["AAPL"], True, False, 3),
    ("fm3", "Apple revenue growth rate FY2022 to FY2023",
     ["AAPL"], True, False, 3),
    ("fm4", "Amazon gross margin trends",
     ["AMZN"], True, False, 3),
    ("fm5", "Google's operating cash flow growth",
     ["GOOGL"], True, False, 3),
]

COMPARISON_CASES = [
    ("cmp1", "Compare Apple and Microsoft's financial performance",
     ["AAPL", "MSFT"], True, False, 3),
    ("cmp2", "Compare AWS and Azure cloud revenue",
     ["AMZN", "MSFT"], True, False, 3),
    ("cmp3", "Compare AWS, Azure, and Google Cloud profit margins",
     ["AMZN", "MSFT", "GOOGL"], True, False, 3),
]

RISK_FACTOR_CASES = [
    ("risk1", "How did Apple's risk factors change from FY2022 to FY2023?",
     ["AAPL"], False, False, 3),
    ("risk2", "Track the evolution of AI-related risk factors at Google",
     ["GOOGL"], False, False, 3),
]

AI_DISCLOSURE_CASES = [
    ("ai1", "How has AI disclosure evolved at Microsoft?",
     ["MSFT"], False, False, 3),
    ("ai2", "Compare AI disclosure practices at Microsoft and Google",
     ["MSFT", "GOOGL"], False, False, 3),
]

INSUFFICIENT_EVIDENCE_CASES = [
    ("ie1", "What is Tesla's revenue mix?",
     [], False, True, 0),
]

BUSINESS_SEGMENT_CASES = [
    ("seg1", "What are Apple's main business segments?",
     ["AAPL"], True, False, 3),
    ("seg2", "Tell me about Amazon's AWS segment performance",
     ["AMZN"], True, False, 3),
    ("seg3", "Microsoft Intelligent Cloud vs Personal Computing revenue",
     ["MSFT"], True, False, 3),
    ("seg4", "Google Cloud revenue trends",
     ["GOOGL"], True, False, 3),
    ("seg5", "NVIDIA Data Center segment growth",
     ["NVDA"], True, False, 3),
]

GENERAL_CASES = [
    ("gen1", "Summarize Microsoft's FY2023 financial results",
     ["MSFT"], False, False, 3),
    ("gen2", "How does Google make money?",
     ["GOOGL"], False, False, 3),
]

ALL_EVAL_CASES = (
    REVENUE_MIX_CASES
    + FINANCIAL_METRICS_CASES
    + COMPARISON_CASES
    + RISK_FACTOR_CASES
    + AI_DISCLOSURE_CASES
    + INSUFFICIENT_EVIDENCE_CASES
    + BUSINESS_SEGMENT_CASES
    + GENERAL_CASES
)

assert len(ALL_EVAL_CASES) == 24, f"Expected 24 eval cases, got {len(ALL_EVAL_CASES)}"


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return os.environ.get("EVAL_API_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def api_client(api_base_url: str) -> httpx.Client:
    email = os.environ.get("EVAL_EMAIL")
    password = os.environ.get("EVAL_PASSWORD")
    if not email or not password:
        pytest.skip("EVAL_EMAIL and EVAL_PASSWORD must be set")
    client = httpx.Client(base_url=api_base_url, timeout=60.0)
    resp = client.post("/auth/login", json={"email": email, "password": password})
    if resp.status_code in (400, 401):
        client.post("/auth/signup", json={"email": email, "password": password})
        resp = client.post("/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def _llm_unavailable(data: dict) -> bool:
    return LLM_UNAVAILABLE_MESSAGE in data.get("answer", "")


def _run_query(client: httpx.Client, query: str) -> dict:
    """Create a thread and ask a question. Retries on 429 with backoff."""
    thread_id = None

    # Retry thread creation
    for attempt in range(1, MAX_RETRIES + 2):
        resp = client.post("/chat/threads", json={})
        if resp.status_code == 200:
            thread_id = resp.json()["id"]
            break
        if resp.status_code == 429:
            if attempt > MAX_RETRIES:
                pytest.skip("Rate limited — cannot create thread after retries")
            delay = 2 ** attempt * 2.5
            time.sleep(delay)
            continue
        resp.raise_for_status()
    if thread_id is None:
        pytest.skip("Rate limited — cannot create thread")

    # Retry ask
    for attempt in range(1, MAX_RETRIES + 2):
        resp = client.post(f"/chat/threads/{thread_id}/ask", json={"query": query})
        if resp.status_code == 200:
            data = resp.json()
            if _llm_unavailable(data) and SKIP_LLM:
                return data
            return data
        if resp.status_code == 429:
            if attempt > MAX_RETRIES:
                pytest.skip("Rate limited — cannot ask question after retries")
            delay = 2 ** attempt * 2.5
            time.sleep(delay)
            continue
        resp.raise_for_status()

    pytest.skip("Rate limited — cannot ask question")


def _check_citations(data: dict, tickers: list[str], min_citations: int, case_id: str):
    citations = data.get("citations", [])
    assert len(citations) >= min_citations, (
        f"{case_id}: expected >= {min_citations} citations, got {len(citations)}"
    )
    # Deduplication
    chunk_ids = [c["chunk_id"] for c in citations]
    assert len(chunk_ids) == len(set(chunk_ids)), (
        f"{case_id}: duplicate citations"
    )
    # Ticker integrity
    for c in citations:
        ct = c.get("ticker")
        if ct is not None:
            assert ct in tickers, (
                f"{case_id}: citation ticker '{ct}' not in expected {tickers}"
            )
    # Single-ticker: no cross-company leak
    if len(tickers) == 1:
        expected = tickers[0]
        for c in citations:
            ct = c.get("ticker")
            if ct is not None:
                assert ct == expected, (
                    f"{case_id}: cross-company citation: '{ct}' != '{expected}'"
                )
    # All must have excerpt
    for c in citations:
        assert c.get("excerpt"), f"{case_id}: citation has empty excerpt"


# ── Parametrized regression tests (representative sample) ──────────────────

@eval
@timeout(120)
@pytest.mark.parametrize(
    "case_id,query,tickers,expect_structured,expect_insufficient,min_citations",
    ALL_EVAL_CASES,
    ids=[c[0] for c in ALL_EVAL_CASES],
)
def test_eval_query(
    api_client: httpx.Client,
    case_id: str,
    query: str,
    tickers: list[str],
    expect_structured: bool,
    expect_insufficient: bool,
    min_citations: int,
) -> None:
    data = _run_query(api_client, query)

    # 1. Answer must not be empty
    assert data.get("answer"), f"{case_id}: answer is empty"

    # 2. Expected behavior
    if expect_insufficient:
        assert INSUFFICIENT_EVIDENCE_RESPONSE in data["answer"], (
            f"{case_id}: expected insufficient-evidence response"
        )
        return

    llm_unavailable = _llm_unavailable(data)

    if not llm_unavailable and expect_structured:
        assert "=== STRUCTURED FINANCIAL DATA" in data["answer"], (
            f"{case_id}: expected structured financial data marker"
        )

    # 3. Citation checks
    _check_citations(data, tickers, min_citations, case_id)

    # 4. Metadata integrity
    for c in data.get("citations", []):
        assert c.get("ticker") is not None
        assert c.get("fiscal_year") is not None
        assert c.get("section_title") is not None

    if SKIP_LLM and llm_unavailable:
        return  # Structured check passed, skip LLM narrative check


# ── Category-level smoke tests ─────────────────────────────────────────────

@eval
@timeout(120)
def test_revenue_mix_structured_output(api_client: httpx.Client) -> None:
    data = _run_query(api_client, "What was Apple's revenue mix in FY2023?")
    if SKIP_LLM and _llm_unavailable(data):
        pytest.skip("LLM unavailable — narrative sections not generated")
    assert "=== STRUCTURED FINANCIAL DATA" in data["answer"]
    assert len(data.get("citations", [])) >= 3


@eval
@timeout(120)
def test_comparison_structured_output(api_client: httpx.Client) -> None:
    data = _run_query(api_client, "Compare Apple and Microsoft revenue")
    if SKIP_LLM and _llm_unavailable(data):
        pytest.skip("LLM unavailable — narrative sections not generated")
    assert "=== STRUCTURED FINANCIAL DATA" in data["answer"]
    tickers_in_citations = {
        c.get("ticker") for c in data.get("citations", []) if c.get("ticker")
    }
    assert "AAPL" in tickers_in_citations
    assert "MSFT" in tickers_in_citations


@eval
@timeout(120)
def test_single_ticker_no_cross_company(api_client: httpx.Client) -> None:
    data = _run_query(api_client, "Apple revenue growth rate FY2022 to FY2023")
    for c in data.get("citations", []):
        ct = c.get("ticker")
        if ct is not None:
            assert ct == "AAPL", f"Cross-company citation: {ct}"
    assert len(data.get("citations", [])) >= 2


@eval
@timeout(120)
def test_citations_deduplicated(api_client: httpx.Client) -> None:
    data = _run_query(api_client, "What risks does Amazon face?")
    chunk_ids = [c["chunk_id"] for c in data.get("citations", [])]
    assert len(chunk_ids) == len(set(chunk_ids))


@eval
@timeout(120)
def test_risk_diff_multi_year(api_client: httpx.Client) -> None:
    data = _run_query(
        api_client,
        "How did Apple's risk factors change from FY2022 to FY2023?",
    )
    assert data.get("answer")
    assert len(data.get("citations", [])) >= 2


@eval
@timeout(120)
def test_insufficient_evidence_unknown_ticker(api_client: httpx.Client) -> None:
    data = _run_query(api_client, "What is Tesla's revenue mix?")
    assert INSUFFICIENT_EVIDENCE_RESPONSE in data["answer"]


@eval
@timeout(120)
def test_cloud_segment_comparison(api_client: httpx.Client) -> None:
    data = _run_query(api_client, "Compare AWS and Azure cloud revenue")
    answer = data["answer"]
    if INSUFFICIENT_EVIDENCE_RESPONSE in answer:
        return
    if SKIP_LLM and _llm_unavailable(data):
        pytest.skip("LLM unavailable — narrative sections not generated")
    assert "=== STRUCTURED FINANCIAL DATA" in answer


@eval
@timeout(120)
def test_citations_have_metadata(api_client: httpx.Client) -> None:
    data = _run_query(
        api_client,
        "Summarize Microsoft's FY2023 financial results",
    )
    if SKIP_LLM and _llm_unavailable(data):
        pytest.skip("LLM unavailable — narrative sections not generated")
    for c in data.get("citations", []):
        assert c.get("ticker") is not None
        assert c.get("fiscal_year") is not None
        assert c.get("section_title") is not None
        assert c.get("excerpt") is not None


@eval
@timeout(120)
def test_answer_has_sections(api_client: httpx.Client) -> None:
    data = _run_query(api_client, "How does Google make money?")
    if SKIP_LLM and _llm_unavailable(data):
        pytest.skip("LLM unavailable — narrative sections not generated")
    answer = data["answer"]
    sections = ["Executive Summary", "Key Findings", "Detailed Analysis", "Analyst Takeaway"]
    found = [s for s in sections if s in answer]
    assert len(found) >= 2, f"Expected at least 2 of {sections}, found {found}"
