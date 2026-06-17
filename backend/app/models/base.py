from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generator

from sqlalchemy import DateTime, MetaData, create_engine, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings
from app.core.logging import logger

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    metadata = metadata


try:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=3,
        pool_timeout=30,
    )
    SessionLocal = sessionmaker(engine, expire_on_commit=False)
    logger.info("Database engine created", host=settings.db_host, db=settings.db_name)
except Exception:
    logger.exception("Failed to create database engine")
    raise


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
