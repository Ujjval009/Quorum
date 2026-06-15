from __future__ import annotations

from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        doc="Supabase auth.users.id",
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    chat_threads: Mapped[list[ChatThread]] = relationship(
        "ChatThread",
        back_populates="profile",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Profile id={self.id} email={self.email}>"
