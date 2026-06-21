from __future__ import annotations
import os, time, httpx, pytest

eval = pytest.mark.eval
URL = os.environ.get("EVAL_API_URL", "http://localhost:8000")
EMAIL, PASSWORD = os.environ.get("EVAL_EMAIL"), os.environ.get("EVAL_PASSWORD")
CASES = [("Apple revenue FY2024", "AAPL", 3), ("NVIDIA Data Center revenue", "NVDA", 3)]

@pytest.fixture(scope="module")
def client() -> httpx.Client:
    c = httpx.Client(base_url=URL, timeout=60.0)
    r = c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code in (400, 401):
        c.post("/auth/signup", json={"email": EMAIL, "password": PASSWORD})
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c

def ask(c: httpx.Client, q: str) -> dict:
    for i in range(3):
        r = c.post("/chat/threads", json={})
        if r.status_code == 200: tid = r.json()["id"]; break
        if r.status_code == 429: time.sleep(5 * i + 5)
        else: r.raise_for_status()
    for i in range(3):
        r = c.post(f"/chat/threads/{tid}/ask", json={"query": q})
        if r.status_code == 200: return r.json()
        if r.status_code == 429: time.sleep(5 * i + 5)
        else: r.raise_for_status()

@eval
def test_retrieval_quality(client: httpx.Client) -> None:
    r5 = p5 = mr = 0.0
    for q, ticker, _ in CASES:
        data = ask(client, q)
        citations = data.get("citations", [])
        r5 += 1.0 if any(c.get("ticker") == ticker for c in citations[:5]) else 0.0
        p5 += sum(c.get("ticker") == ticker for c in citations[:5]) / 5 if citations else 0.0
        for i, c in enumerate(citations, 1):
            if c.get("ticker") == ticker: mr += 1.0 / i; break
    n = len(CASES)
    print(f"Recall@5: {r5/n:.3f} | Precision@5: {p5/n:.3f} | MRR: {mr/n:.3f}")
    assert r5/n >= 0.80 and p5/n >= 0.90 and mr/n >= 0.70

@eval
@pytest.mark.parametrize("q,ticker,n_cit", CASES, ids=[c[1] for c in CASES])
def test_citations(client: httpx.Client, q: str, ticker: str, n_cit: int) -> None:
    data = ask(client, q)
    assert data.get("answer")
    citations = data["citations"]
    assert len(citations) >= n_cit
    assert len({c["chunk_id"] for c in citations}) == len(citations)
    for c in citations:
        assert c.get("ticker") and c.get("fiscal_year") and c.get("section_title")
    assert all(c.get("ticker") == ticker for c in citations), "cross-company leak"
    assert "=== STRUCTURED FINANCIAL DATA" in data["answer"], "missing structured output"
