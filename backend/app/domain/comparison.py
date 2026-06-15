from __future__ import annotations

from app.domain.retrieval import RetrievedChunk

SEGMENT_TERMINOLOGY: dict[str, dict[str, list[str]]] = {
    "AMZN": {
        "display": "Amazon (AMZN)",
        "segments": {
            "Amazon Web Services (AWS)": [
                "aws", "amazon web services", "aws revenue", "aws operating income",
                "aws operating expense", "aws margin", "aws segment",
            ],
            "eCommerce & Retail": [
                "online store", "physical store", "retail", "ecommerce",
                "third-party seller", "advertising",
            ],
        },
        "segment_revenue_headers": [
            "aws", "amazon web services",
        ],
    },
    "MSFT": {
        "display": "Microsoft (MSFT)",
        "segments": {
            "Intelligent Cloud (Azure)": [
                "azure", "intelligent cloud", "server products", "cloud revenue",
                "azure revenue", "microsoft cloud", "azure ai", "azure openai",
                "azure infrastructure", "azure services",
            ],
            "Productivity & Business": [
                "office", "microsoft 365", "linkedin", "dynamics", "copilot",
            ],
            "Personal Computing": [
                "windows", "xbox", "surface", "search advertising", "devices",
            ],
        },
        "segment_revenue_headers": [
            "intelligent cloud", "azure",
        ],
    },
    "GOOGL": {
        "display": "Alphabet (GOOGL)",
        "segments": {
            "Google Cloud": [
                "google cloud", "gcp", "cloud revenue", "google workspace",
                "cloud platform",
            ],
            "Google Advertising": [
                "google advertising", "search revenue", "youtube ads",
                "google network", "ad revenue",
            ],
            "Other Bets": [
                "other bets", "waymo", "verily",
            ],
        },
        "segment_revenue_headers": [
            "google cloud",
        ],
    },
    "NVDA": {
        "display": "NVIDIA (NVDA)",
        "segments": {
            "Data Center": [
                "data center", "datacenter", "compute & networking",
                "data center revenue", "accelerated computing",
            ],
            "Gaming": [
                "gaming", "geforce", "game", "gpu gaming",
            ],
            "Professional Visualization": [
                "professional visualization", "quadro", "design & visualization",
            ],
            "Automotive": [
                "automotive", "autonomous vehicle", "drive platform",
            ],
        },
        "segment_revenue_headers": [
            "data center",
        ],
    },
    "AAPL": {
        "display": "Apple (AAPL)",
        "segments": {
            "iPhone": [
                "iphone", "net sales iphone",
            ],
            "Services": [
                "services revenue", "app store", "apple music", "icloud",
                "apple care", "services net sales",
            ],
            "Mac": [
                "mac", "macbook",
            ],
            "iPad": [
                "ipad",
            ],
            "Wearables & Accessories": [
                "wearables", "apple watch", "airpods", "home accessories",
            ],
        },
        "segment_revenue_headers": [
            "iphone", "services revenue",
        ],
    },
}


def _company_display_name(ticker: str) -> str:
    info = SEGMENT_TERMINOLOGY.get(ticker)
    return info["display"] if info else ticker


def _label_company_chunks(
    chunks: list[RetrievedChunk],
    ticker: str,
) -> list[RetrievedChunk]:
    """Classify chunks into their business segments based on content keywords.
    
    For each chunk, find the best-matching business segment from SEGMENT_TERMINOLOGY
    and annotate the chunk with that segment name.
    """
    company_info = SEGMENT_TERMINOLOGY.get(ticker)
    if not company_info:
        return chunks
    
    segments_dict = company_info.get("segments", {})
    
    for chunk in chunks:
        content_lower = chunk.content.lower()
        best_segment: str | None = None
        best_match_count = 0
        
        # Match chunk content against segment keywords
        for segment_name, keywords in segments_dict.items():
            match_count = sum(1 for kw in keywords if kw in content_lower)
            if match_count > best_match_count:
                best_match_count = match_count
                best_segment = segment_name
        
        # Annotate chunk with segment if found
        if best_segment and best_match_count > 0:
            chunk.segment = best_segment
    
    return chunks


def build_comparison_context(
    company_a: str,
    company_b: str,
    chunks_a: list[RetrievedChunk],
    chunks_b: list[RetrievedChunk],
) -> str:
    # Label chunks with their business segments
    chunks_a = _label_company_chunks(chunks_a, company_a)
    chunks_b = _label_company_chunks(chunks_b, company_b)
    
    parts: list[str] = []

    # ── Header ──
    name_a = _company_display_name(company_a)
    name_b = _company_display_name(company_b)
    parts.append(f"# Cross-Company Comparison: {name_a} vs {name_b}\n")

    # ── Company A Overview ──
    parts.append(f"## {name_a}")
    parts.append(f"Chunks retrieved: {len(chunks_a)}")
    years_a = sorted({c.fiscal_year for c in chunks_a if c.fiscal_year})
    if years_a:
        parts.append(f"Fiscal years: {', '.join(f'FY{y}' for y in years_a)}")
    sections_a = sorted({c.section_title for c in chunks_a if c.section_title})
    if sections_a:
        parts.append(f"Sections: {', '.join(sections_a[:5])}")
    segments_a = sorted({c.segment for c in chunks_a if c.segment})
    if segments_a:
        parts.append(f"Segments: {', '.join(segments_a)}")
    parts.append("")

    # ── Company B Overview ──
    parts.append(f"## {name_b}")
    parts.append(f"Chunks retrieved: {len(chunks_b)}")
    years_b = sorted({c.fiscal_year for c in chunks_b if c.fiscal_year})
    if years_b:
        parts.append(f"Fiscal years: {', '.join(f'FY{y}' for y in years_b)}")
    sections_b = sorted({c.section_title for c in chunks_b if c.section_title})
    if sections_b:
        parts.append(f"Sections: {', '.join(sections_b[:5])}")
    segments_b = sorted({c.segment for c in chunks_b if c.segment})
    if segments_b:
        parts.append(f"Segments: {', '.join(segments_b)}")
    parts.append("")

    # ── Segment Terminology Guide ──
    parts.append("## Segment Terminology Reference")
    for ticker in [company_a, company_b]:
        info = SEGMENT_TERMINOLOGY.get(ticker)
        if info:
            parts.append(f"\n### {info['display']} Segments")
            for segment_name, keywords in info["segments"].items():
                parts.append(f"- **{segment_name}**: appears in filings as {' / '.join(keywords[:3])}")
    parts.append("")

    # ── Company A Chunks (organized by segment) ──
    parts.append(f"## {name_a} — Filing Excerpts by Segment")
    segments_a_dict: dict[str | None, list[RetrievedChunk]] = {}
    for chunk in chunks_a:
        seg = chunk.segment or "General"
        if seg not in segments_a_dict:
            segments_a_dict[seg] = []
        segments_a_dict[seg].append(chunk)
    
    _MAX_CHUNK_CHARS = 2000
    _MAX_CHUNKS_PER_SEGMENT = 20

    for seg_name in sorted(segments_a_dict.keys()):
        seg_chunks = segments_a_dict[seg_name][:_MAX_CHUNKS_PER_SEGMENT]
        if seg_name != "General":
            parts.append(f"\n### {seg_name}")
        for i, chunk in enumerate(seg_chunks, 1):
            label = chunk.citation_label
            text = chunk.content[:_MAX_CHUNK_CHARS]
            parts.append(f"\n[{i}] {label}\n{text}")

    # ── Company B Chunks (organized by segment) ──
    if chunks_b:
        parts.append(f"\n## {name_b} — Filing Excerpts by Segment")
        segments_b_dict: dict[str | None, list[RetrievedChunk]] = {}
        for chunk in chunks_b:
            seg = chunk.segment or "General"
            if seg not in segments_b_dict:
                segments_b_dict[seg] = []
            segments_b_dict[seg].append(chunk)
        
        for seg_name in sorted(segments_b_dict.keys()):
            seg_chunks = segments_b_dict[seg_name][:_MAX_CHUNKS_PER_SEGMENT]
            if seg_name != "General":
                parts.append(f"\n### {seg_name}")
            for i, chunk in enumerate(seg_chunks, 1):
                label = chunk.citation_label
                text = chunk.content[:_MAX_CHUNK_CHARS]
                parts.append(f"\n[{i}] {label}\n{text}")

    return "\n".join(parts)
