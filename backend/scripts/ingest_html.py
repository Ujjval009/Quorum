"""Ingest SEC filing HTML files directly into the database.

Usage: .venv/bin/python scripts/ingest_html.py
"""

from __future__ import annotations

import json
import os
import re
import uuid
from html.parser import HTMLParser

from app.core.logging import logger
from app.domain.embeddings import generate_embedding
from app.models.base import SessionLocal
from app.models.document import DocumentChunk, SourceDocument


class SECHTMLParser(HTMLParser):
    """Strip HTML tags, skip script/style, extract text."""

    def __init__(self) -> None:
        super().__init__()
        self._text_parts: list[str] = []
        self._skip = 0  # nesting depth of script/style

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self._text_parts.append(data)

    def get_text(self) -> str:
        raw = " ".join(self._text_parts)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw


_ITEM_PATTERN = re.compile(
    r"(Item\s+(?:\d+[A-Za-z]?)(?:\.|\b))"
    r"(.*?)(?=(?:Item\s+(?:\d+[A-Za-z]?)(?:\.|\b))|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_SECONDARY_HEADING = re.compile(
    r"^\s*(?:Overview|Business|Risk Factors|Management[‘']s? Discussion|"
    r"Results of Operations|Financial (?:Statements|Data)|"
    r"Quantitative and Qualitative|Controls and Procedures|"
    r"Directors[,\s]+Executive|Executive (?:Officers|Compensation)|"
    r"Principal (?:Accountant|Stockholder)|"
    r"Exhibits[,\s]+Financial|Market for Registrant[‘']s?|"
    r"Selected Financial|Supplementary (?:Financial|Data)|"
    r"Disclosures? About|Mine Safety|"
    r"Changes? In and Disagreements?|"
    r"Part\s+(?:I|II|III|IV)\b)",
    re.IGNORECASE,
)

_COMMON_SECTION_TITLES: dict[str, str] = {
    "item 1.": "Item 1. Business",
    "item 1a": "Item 1A. Risk Factors",
    "item 1b": "Item 1B. Unresolved Staff Comments",
    "item 1c": "Item 1C. Cybersecurity",
    "item 2.": "Item 2. Properties",
    "item 3.": "Item 3. Legal Proceedings",
    "item 4.": "Item 4. Mine Safety Disclosures",
    "item 5.": "Item 5. Market for Registrant's Common Equity",
    "item 6.": "Item 6. [Reserved]",
    "item 7.": "Item 7. Management's Discussion and Analysis",
    "item 7a": "Item 7A. Quantitative and Qualitative Disclosures",
    "item 8.": "Item 8. Financial Statements and Supplementary Data",
    "item 9.": "Item 9. Changes in and Disagreements",
    "item 9a": "Item 9A. Controls and Procedures",
    "item 9b": "Item 9B. Other Information",
    "item 9c": "Item 9C. Disclosure Regarding Foreign Jurisdictions",
    "item 10.": "Item 10. Directors, Executive Officers and Corporate Governance",
    "item 11.": "Item 11. Executive Compensation",
    "item 12.": "Item 12. Security Ownership of Certain Beneficial Owners",
    "item 13.": "Item 13. Certain Relationships and Related Transactions",
    "item 14.": "Item 14. Principal Accountant Fees and Services",
    "item 15.": "Item 15. Exhibits and Financial Statement Schedules",
    "item 16.": "Item 16. Form 10-K Summary",
}


def _clean_text(raw: str) -> str:
    text = re.sub(r"\bix:[a-zA-Z0-9.-]+\b", " ", raw)
    text = re.sub(r"\b[0-9A-Za-z-]+:[0-9A-Za-z.-]+\b", " ", text)
    text = re.sub(r"\bhttp\S+\b", " ", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_narrative(html: str) -> str:
    """Extract narrative text, skipping XBRL context / ix namespace junk."""
    parser = SECHTMLParser()
    parser.feed(html)
    text = parser.get_text()

    text = _clean_text(text)

    markers = [
        r"UNITED STATES\s+SECURITIES\s+AND\s+EXCHANGE\s+COMMISSION",
        r"Commission\s+file\s+number",
        r"TABLE\s+OF\s+CONTENTS",
    ]
    earliest = len(text)
    for marker in markers:
        m = re.search(marker, text, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 200)
            if start < earliest:
                earliest = start

    text = text[earliest:] if earliest < len(text) else text

    return text.strip()


def extract_sections(text: str) -> list[tuple[str, str]]:
    """Split extracted text into Item-based sections.

    Returns a list of ``(section_title, section_content)`` tuples.
    """
    matches = list(_ITEM_PATTERN.finditer(text))
    sections: list[tuple[str, str]] = []

    for i, m in enumerate(matches):
        raw_label = m.group(1).strip()
        content = m.group(2).strip()

        label_lower = raw_label.lower().rstrip(".")
        key = label_lower[:7]
        title = _COMMON_SECTION_TITLES.get(key, raw_label)

        sections.append((title, content))

    if not sections:
        sections.append(("Full Filing", text))

    return sections


def chunk_into_sections(
    sections: list[tuple[str, str]],
    max_chars: int = 4000,
    overlap: int = 200,
) -> list[tuple[str, str, int]]:
    """Split each section into chunks, returning list of (section_title, chunk_text, global_chunk_index)."""
    result: list[tuple[str, str, int]] = []
    global_idx = 0
    for section_title, section_text in sections:
        chunks = _chunk_text(section_text, max_chars, overlap)
        for text in chunks:
            result.append((section_title, text, global_idx))
            global_idx += 1
    return result


def _chunk_text(text: str, max_chars: int = 4000, overlap: int = 200) -> list[str]:
    """Split text into chunks by character count on sentence/paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]
    seps = ["\n\n", "\n", ". "]
    for sep in seps:
        parts = text.split(sep)
        if len(parts) <= 1:
            continue
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for part in parts:
            part_len = len(part) + len(sep)
            if current_len + part_len > max_chars and current:
                chunks.append(sep.join(current))
                overlap_chars = 0
                overlap_parts: list[str] = []
                for p in reversed(current):
                    pl = len(p) + len(sep)
                    if overlap_chars + pl > overlap:
                        break
                    overlap_parts.insert(0, p)
                    overlap_chars += pl
                current = overlap_parts
                current_len = overlap_chars
            current.append(part)
            current_len += part_len
        if current:
            chunks.append(sep.join(current))
        if len(chunks) > 1:
            return chunks
    words = text.split()
    chunks = []
    for i in range(0, len(words), 800):
        chunk = " ".join(words[i : i + 800])
        chunks.append(chunk)
    return chunks


def main() -> None:
    p = os.path.join(os.path.dirname(__file__), "..", "..", "data", "downloads")
    manifest_path = os.path.join(p, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)

    db = SessionLocal()
    # Clear old data
    db.query(DocumentChunk).delete()
    db.query(SourceDocument).delete()
    db.commit()

    for filing in manifest["filings"]:
        html_path = os.path.join(p, filing["local_path"])
        if not os.path.exists(html_path):
            logger.warning("File not found", path=html_path)
            continue

        with open(html_path, encoding="utf-8", errors="ignore") as f:
            html = f.read()

        text = extract_narrative(html)
        if not text:
            logger.warning("No text extracted", path=html_path)
            continue

        ticker = filing["ticker"]
        year = filing["report_date"].split("-")[0]

        sections = extract_sections(text)
        logger.info(
            "Sections extracted",
            ticker=ticker, year=year, total_chars=len(text), section_count=len(sections),
        )

        doc_id = uuid.uuid4()
        doc = SourceDocument(
            id=doc_id,
            source_type="sec_filing",
            filename=f"{ticker}_{year}.txt",
            title=f"{ticker} 10-K {year}",
            ticker=ticker.upper(),
            filing_type="10-K",
            fiscal_year=int(year),
            page_count=len(sections),
            content=text[:500000],
        )
        db.add(doc)
        db.flush()

        chunked_sections = chunk_into_sections(sections, max_chars=4000, overlap=200)
        logger.info(
            "Processing",
            ticker=ticker, year=year, chars=len(text),
            sections=len(sections), chunks=len(chunked_sections),
        )

        for section_title, chunk_text, chunk_idx in chunked_sections:
            try:
                emb = generate_embedding(chunk_text)
            except Exception:
                logger.exception("Embedding failed, chunk too long", length=len(chunk_text))
                for sub in _chunk_text(chunk_text, max_chars=2000, overlap=0):
                    emb = generate_embedding(sub)
                    c = DocumentChunk(
                        document_id=doc_id,
                        chunk_index=chunk_idx,
                        content=sub,
                        page_number=1,
                        section_title=section_title,
                        token_count=len(sub.split()),
                        embedding=emb,
                    )
                    db.add(c)
                continue

            c = DocumentChunk(
                document_id=doc_id,
                chunk_index=chunk_idx,
                content=chunk_text,
                page_number=1,
                section_title=section_title,
                token_count=len(chunk_text.split()),
                embedding=emb,
            )
            db.add(c)

        db.commit()
        print(f"  {ticker} {year}: {len(text):,} chars, {len(sections)} sections, {len(chunked_sections)} chunks")

    db.close()
    print("Done!")


if __name__ == "__main__":
    main()
