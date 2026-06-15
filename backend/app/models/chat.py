from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ChatThread(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_threads"

    user_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    profile: Mapped["Profile"] = relationship(
        "Profile",
        back_populates="chat_threads",
    )
    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatThread id={self.id} title={self.title}>"


class ChatMessage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        doc="AI SDK-compatible message metadata",
    )

    thread: Mapped[ChatThread] = relationship(
        "ChatThread",
        back_populates="messages",
    )
    citations: Mapped[list[MessageCitation]] = relationship(
        "MessageCitation",
        back_populates="message",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} role={self.role}>"


class MessageCitation(UUIDMixin, Base):
    __tablename__ = "message_citations"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )

    message: Mapped[ChatMessage] = relationship(
        "ChatMessage",
        back_populates="citations",
    )
    chunk: Mapped["DocumentChunk"] = relationship("DocumentChunk")
