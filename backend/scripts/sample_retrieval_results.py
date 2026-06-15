"""Sample chunks from the retrieval endpoint to build ground-truth eval set.

Usage:
    uv run python scripts/sample_retrieval_results.py
"""

import httpx

BASE = "http://localhost:8000"

QUERIES = [
    "What was Apple's AWS revenue in FY2023?",
    "Amazon AWS revenue FY2023",
    "Apple iPhone revenue FY2024",
    "Amazon AWS operating income FY2024",
    "Microsoft Azure revenue growth FY2023",
    "NVIDIA data center revenue FY2024",
    "Google Cloud revenue FY2023",
    "Apple risk factors FY2022",
    "Microsoft AI disclosure risk factors FY2024",
    "Amazon revenue FY2021",
    "NVIDIA operating margin FY2025",
    "Apple services revenue FY2023",
    "Microsoft intelligent cloud revenue FY2022",
    "Google Search advertising revenue FY2024",
    "Amazon net income FY2023",
]


def login() -> str:
    resp = httpx.post(
        f"{BASE}/auth/login",
        json={"email": "123@gmail.com", "password": "Password123!"},
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token") or data.get("token") or data["access_token"]
    return token


def search(query: str, token: str, top_k: int = 10) -> list[dict]:
    resp = httpx.post(
        f"{BASE}/chat/search",
        json={"query": query, "top_k": top_k},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results") or data.get("chunks") or data
    if isinstance(results, list):
        return results
    if isinstance(results, dict):
        return results.get("results", [])
    return []


def format_result(r: dict) -> str:
    chunk_id = r.get("chunk_id") or r.get("id") or "?"
    ticker = r.get("ticker") or r.get("metadata", {}).get("ticker", "?")
    fiscal_year = r.get("fiscal_year") or r.get("metadata", {}).get("fiscal_year", "?")
    section = r.get("section_title") or r.get("metadata", {}).get("section_title", "?")
    page = r.get("page_number") or r.get("metadata", {}).get("page_number", "?")
    score = r.get("score") or r.get("similarity") or "?"
    content = r.get("content") or r.get("text") or r.get("chunk_text") or ""
    preview = content[:200].replace("\n", " ")
    return (
        f"  chunk_id={chunk_id}, ticker={ticker}, fiscal_year={fiscal_year}, "
        f'section_title="{section}", page={page}, score={score}, '
        f'content_preview="{preview}"'
    )


def main():
    print("Logging in...")
    token = login()
    print(f"Token: {token[:20]}...\n")

    for q in QUERIES:
        print(f"Query: {q!r}")
        results = search(q, token)
        if not results:
            print("  [no results returned]")
        else:
            for i, r in enumerate(results[:10], 1):
                print(f"  {i}. {format_result(r)}")
        print()


if __name__ == "__main__":
    main()
