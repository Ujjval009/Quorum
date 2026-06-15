from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    filename: str
    title: str | None = None
    company_name: str | None = None
    ticker: str | None = None
    filing_type: str | None = None
    fiscal_year: int | None = None
    page_count: int | None = None
    chunk_count: int | None = None
    source_url: str | None = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class DocumentDetailResponse(BaseModel):
    id: str
    filename: str
    title: str | None = None
    company_name: str | None = None
    ticker: str | None = None
    filing_type: str | None = None
    fiscal_year: int | None = None
    page_count: int | None = None
    chunk_count: int = 0
    source_url: str | None = None
    created_at: datetime
    updated_at: datetime
