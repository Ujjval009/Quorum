"""initial

Revision ID: 8e750286004e
Revises: 
Create Date: 2026-06-09 09:17:08.734575

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision: str = '8e750286004e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "profiles",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "chat_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(255), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(255), sa.ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("filing_type", sa.String(32), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("ticker", sa.String(16), nullable=True),
        sa.Column("fiscal_year", sa.Integer, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("metadata_", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section_title", sa.String(512), nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("metadata_", postgresql.JSONB, nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(768), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_unique_constraint(
        "uq_document_chunks_document_chunk",
        "document_chunks",
        ["document_id", "chunk_index"],
    )

    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 200},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.execute(
        """
        CREATE INDEX ix_document_chunks_fts
        ON document_chunks
        USING GIN (to_tsvector('english', content));
        """
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata_", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "message_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("excerpt", sa.Text, nullable=True),
        sa.Column("metadata_", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("message_citations")
    op.drop_table("chat_messages")
    op.drop_index("ix_document_chunks_fts", table_name="document_chunks")
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_table("source_documents")
    op.drop_table("chat_threads")
    op.drop_table("profiles")
    op.execute("DROP EXTENSION IF EXISTS vector")
