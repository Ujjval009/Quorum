from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CitationItem(BaseModel):
    chunk_id: str
    page_number: int | None = None
    section_title: str | None = None
    ticker: str | None = None
    fiscal_year: int | None = None
    excerpt: str | None = None


class ThreadCreate(BaseModel):
    title: str = "New Chat"


class ThreadResponse(BaseModel):
    id: str
    title: str
    created_at: datetime


class ThreadListResponse(BaseModel):
    threads: list[ThreadResponse]


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    citations: list[CitationItem] = []
    created_at: datetime


class ThreadDetailResponse(BaseModel):
    id: str
    title: str
    messages: list[MessageResponse]
    created_at: datetime


class ThreadUpdate(BaseModel):
    title: str


class AskRequest(BaseModel):
    query: str
    top_k: int = 25


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationItem]
    message_id: str
    title: str | None = None
