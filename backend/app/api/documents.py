from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_profile
from app.core.logging import logger
from app.models.base import get_db
from app.models.document import DocumentChunk, SourceDocument
from app.models.profile import Profile
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents(
    ticker: str | None = None,
    sort: str = "fiscal_year",
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> DocumentListResponse:
    logger.info("Document list request", ticker=ticker, sort=sort)

    query = db.query(
        SourceDocument,
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == SourceDocument.id)
        .statement.with_only_columns(func.count())
        .scalar_subquery()
        .label("chunk_count"),
    ).filter(
        SourceDocument.source_type == "sec_filing",
    )

    if ticker:
        query = query.filter(SourceDocument.ticker.ilike(ticker))

    if sort == "company":
        query = query.order_by(SourceDocument.company_name, SourceDocument.fiscal_year.desc())
    else:
        query = query.order_by(SourceDocument.fiscal_year.desc(), SourceDocument.ticker)

    rows = query.all()

    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=str(d.id),
                filename=d.filename,
                title=d.title,
                company_name=d.company_name,
                ticker=d.ticker,
                filing_type=d.filing_type,
                fiscal_year=d.fiscal_year,
                page_count=d.page_count,
                chunk_count=chunk_count,
                created_at=d.created_at,
            )
            for d, chunk_count in rows
        ],
        total=len(rows),
    )


@router.get("/{document_id}")
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> DocumentDetailResponse:
    logger.info("Document detail request", document_id=document_id)

    doc = db.query(SourceDocument).filter(SourceDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunk_count = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == doc.id,
    ).count()

    return DocumentDetailResponse(
        id=str(doc.id),
        filename=doc.filename,
        title=doc.title,
        company_name=doc.company_name,
        ticker=doc.ticker,
        filing_type=doc.filing_type,
        fiscal_year=doc.fiscal_year,
        page_count=doc.page_count,
        chunk_count=chunk_count,
        source_url=doc.source_url,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )
