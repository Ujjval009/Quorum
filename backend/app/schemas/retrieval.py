from __future__ import annotations

from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    user_id: str | None = None


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    page_number: int | None = None
    section_title: str | None = None
    score: float
    source: str
    ticker: str | None = None
    fiscal_year: int | None = None
    company_name: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int
