from __future__ import annotations

import uuid
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class SourceDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "source_documents"

    user_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filing_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        doc="sec_filing | uploaded_document",
    )
    ticker: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    fiscal_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Normalized Markdown content",
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )

    def __repr__(self) -> str:
        return f"<SourceDocument id={self.id} filename={self.filename}>"


class DocumentChunk(UUIDMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(768),
        nullable=True,
    )

    document: Mapped[SourceDocument] = relationship(
        "SourceDocument",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk id={self.id} idx={self.chunk_index}>"


Index("ix_document_chunks_document_id_chunk_index", DocumentChunk.document_id, DocumentChunk.chunk_index, unique=True)
