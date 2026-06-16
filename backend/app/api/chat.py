from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_profile
from app.core.logging import logger
from app.core.rate_limiter import RateLimiter, RateLimitExceeded
from app.domain.coverage import (
    expand_coverage,
    filter_expanded_to_single_ticker,
    validate_coverage,
)
from app.domain.rag import generate_answer, generate_answer_stream
from app.domain.retrieval import (
    COMPANY_TICKER_MAP,
    detect_intent,
    detect_ticker,
    detect_tickers,
    filter_chunks_by_ticker,
    hybrid_search,
)
from app.domain.titles import generate_title
from app.domain.workflows import STRUCTURED_INTENTS, check_sufficient_evidence
from app.models.base import get_db
from app.models.chat import ChatMessage, ChatThread, MessageCitation
from app.models.profile import Profile
from app.schemas.chat import (
    AskRequest,
    AskResponse,
    CitationItem,
    MessageResponse,
    ThreadCreate,
    ThreadDetailResponse,
    ThreadListResponse,
    ThreadResponse,
    ThreadUpdate,
)
from app.schemas.retrieval import SearchRequest, SearchResponse, SearchResultItem

router = APIRouter(prefix="/chat", tags=["chat"])

# ── Shared rate limiter for chat endpoints ──
_chat_limiter = RateLimiter(window=60, max_requests=30)


def _check_chat_rate_limit(request: Request, profile: Profile) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"chat:{profile.id}:{client_ip}"
    try:
        _chat_limiter.check(key)
    except RateLimitExceeded:
        logger.warning("Chat rate limit exceeded", user_id=profile.id, endpoint="ask")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


def _thread_to_response(thread: ChatThread) -> ThreadResponse:
    return ThreadResponse(
        id=str(thread.id),
        title=thread.title,
        created_at=thread.created_at,
    )


@router.post("/search")
def search(
    body: SearchRequest,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> SearchResponse:
    logger.info("Search request", query=body.query[:80], user_id=profile.id)

    ticker = detect_ticker(body.query)
    results = hybrid_search(
        query=body.query,
        db=db,
        top_k=body.top_k,
        ticker=ticker,
    )

    return SearchResponse(
        results=[
            SearchResultItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                content=r.content,
                page_number=r.page_number,
                section_title=r.section_title,
                score=r.score,
                source=r.source,
                ticker=r.ticker,
                fiscal_year=r.fiscal_year,
                company_name=r.company_name,
            )
            for r in results
        ],
        total=len(results),
    )


@router.post("/threads")
def create_thread(
    body: ThreadCreate,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> ThreadResponse:
    logger.info("Creating thread", title=body.title, user_id=profile.id)
    thread = ChatThread(user_id=profile.id, title=body.title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return _thread_to_response(thread)


@router.get("/threads")
def list_threads(
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> ThreadListResponse:
    threads = (
        db.query(ChatThread)
        .filter(ChatThread.user_id == profile.id)
        .order_by(ChatThread.created_at.desc())
        .all()
    )
    return ThreadListResponse(threads=[_thread_to_response(t) for t in threads])


@router.get("/threads/{thread_id}")
def get_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> ThreadDetailResponse:
    thread = (
        db.query(ChatThread)
        .options(
            selectinload(ChatThread.messages).selectinload(ChatMessage.citations),
        )
        .filter(
            ChatThread.id == thread_id,
            ChatThread.user_id == profile.id,
        )
        .first()
    )
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    return ThreadDetailResponse(
        id=str(thread.id),
        title=thread.title,
        created_at=thread.created_at,
        messages=[
            MessageResponse(
                id=str(m.id),
                role=m.role,
                content=m.content,
                citations=[
                    CitationItem(
                        chunk_id=str(c.chunk_id),
                        page_number=c.page_number,
                        section_title=c.section_title,
                        ticker=(c.metadata_ or {}).get("ticker"),
                        fiscal_year=(c.metadata_ or {}).get("fiscal_year"),
                        excerpt=c.excerpt,
                    )
                    for c in m.citations
                ],
                created_at=m.created_at,
            )
            for m in thread.messages
        ],
    )


@router.patch("/threads/{thread_id}")
def update_thread(
    thread_id: str,
    body: ThreadUpdate,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> ThreadResponse:
    logger.info("Updating thread title", thread_id=thread_id, user_id=profile.id)
    thread = db.query(ChatThread).filter(
        ChatThread.id == thread_id,
        ChatThread.user_id == profile.id,
    ).first()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    thread.title = body.title
    db.commit()
    db.refresh(thread)
    return _thread_to_response(thread)


@router.delete("/threads/{thread_id}")
def delete_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> dict:
    thread = db.query(ChatThread).filter(
        ChatThread.id == thread_id,
        ChatThread.user_id == profile.id,
    ).first()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    db.delete(thread)
    db.commit()
    return {"detail": "Thread deleted"}


@router.post("/threads/{thread_id}/ask")
def ask_question(
    thread_id: str,
    body: AskRequest,
    request: Request,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> AskResponse:
    _check_chat_rate_limit(request, profile)
    logger.info("Ask question", thread_id=thread_id, query=body.query[:80], user_id=profile.id)

    thread = db.query(ChatThread).filter(
        ChatThread.id == thread_id,
        ChatThread.user_id == profile.id,
    ).first()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    user_msg = ChatMessage(thread_id=thread.id, role="user", content=body.query)
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # Auto-generate title from first user message
    thread_title: str | None = None
    prior_count = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread.id, ChatMessage.id != user_msg.id)
        .count()
    )
    if prior_count == 0:
        thread_title = generate_title(body.query)
        thread.title = thread_title
        db.commit()

    ticker = detect_ticker(body.query)
    intent = detect_intent(body.query)

    if intent == "company_comparison":
        tickers = detect_tickers(body.query)
        logger.info("Company comparison detected", tickers=tickers)
        effective_top_k = max(body.top_k or 15, 40)
        chunks: list = []
        for t in tickers:
            # Generate a ticker-specific query for each company so the
            # vector search and FTS surface the right financial tables.
            # E.g. for AMZN: "aws segment revenue financial performance AMZN"
            company_query = body.query
            company_name = next(
                (name for name, tk in COMPANY_TICKER_MAP.items()
                 if tk == t and re.search(r"\b" + re.escape(name) + r"\b", body.query.lower())),
                None,
            )
            if not company_name:
                company_name = t.lower()
                company_query = f"{company_name} {body.query}"
            t_chunks = hybrid_search(
                query=company_query,
                db=db,
                top_k=effective_top_k,
                ticker=t,
                search_depth=80,
            )
            chunks.extend(t_chunks)
    elif intent == "risk_factor_diff":
        chunks = hybrid_search(
            query=body.query,
            db=db,
            top_k=30,
            ticker=ticker,
            search_depth=60,
        )
        item_1a_chunks = [
            c for c in chunks 
            if c.section_title and "item 1a" in c.section_title.lower()
        ]
        if item_1a_chunks:
            chunks = item_1a_chunks
    else:
        effective_top_k = max(body.top_k or 25, 25)
        if intent in STRUCTURED_INTENTS:
            effective_top_k = max(effective_top_k, 80)
            logger.debug(
                "Structured intent — using deeper retrieval",
                intent=intent, top_k=effective_top_k,
            )
        chunks = hybrid_search(
            query=body.query,
            db=db,
            top_k=effective_top_k,
            ticker=ticker,
            search_depth=80 if intent in STRUCTURED_INTENTS else 75,
        )

    if ticker and detect_tickers(body.query) == [ticker] and intent != "company_comparison":
        chunks = filter_chunks_by_ticker(chunks, ticker)

    coverage = validate_coverage(body.query, chunks, intent)
    if coverage.has_gaps:
        chunks = expand_coverage(body.query, chunks, coverage, intent, db)
        if ticker and intent != "company_comparison":
            chunks = filter_expanded_to_single_ticker(chunks, ticker)
        coverage = validate_coverage(body.query, chunks, intent)

    if coverage.has_gaps and intent in ("financial_metrics", "revenue_mix", "company_comparison", "business_segment"):
        logger.warning("Coverage gaps remain despite expansion", gaps=coverage.gap_description)

    prior = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.thread_id == thread.id,
            ChatMessage.id != user_msg.id,
        )
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in prior[-6:]]

    answer, raw_citations = generate_answer(body.query, chunks, intent=intent, history=history)

    assistant_msg = ChatMessage(thread_id=thread.id, role="assistant", content=answer)
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    citations: list[MessageCitation] = []
    for cite in raw_citations:
        citation = MessageCitation(
            message_id=assistant_msg.id,
            chunk_id=cite["chunk_id"],
            page_number=cite["page_number"],
            section_title=cite.get("section_title"),
            excerpt=cite["excerpt"],
            metadata_={
                "ticker": cite.get("ticker"),
                "fiscal_year": cite.get("fiscal_year"),
            },
        )
        db.add(citation)
        citations.append(citation)

    if citations:
        db.commit()

    return AskResponse(
        answer=answer,
        citations=[
            CitationItem(
                chunk_id=str(c.chunk_id),
                page_number=c.page_number,
                section_title=c.section_title,
                ticker=(c.metadata_ or {}).get("ticker"),
                fiscal_year=(c.metadata_ or {}).get("fiscal_year"),
                excerpt=c.excerpt,
            )
            for c in citations
        ],
        message_id=str(assistant_msg.id),
        title=thread_title,
    )


@router.post("/threads/{thread_id}/ask/stream")
def ask_question_stream(
    thread_id: str,
    body: AskRequest,
    request: Request,
    db: Session = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
) -> StreamingResponse:
    _check_chat_rate_limit(request, profile)
    logger.info("Streaming ask question", thread_id=thread_id, query=body.query[:80], user_id=profile.id)

    thread = db.query(ChatThread).filter(
        ChatThread.id == thread_id,
        ChatThread.user_id == profile.id,
    ).first()
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    user_msg = ChatMessage(thread_id=thread.id, role="user", content=body.query)
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # Auto-generate title from first user message
    thread_title: str | None = None
    prior_count = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread.id, ChatMessage.id != user_msg.id)
        .count()
    )
    if prior_count == 0:
        thread_title = generate_title(body.query)
        thread.title = thread_title
        db.commit()

    ticker = detect_ticker(body.query)
    intent = detect_intent(body.query)

    if intent == "company_comparison":
        tickers = detect_tickers(body.query)
        logger.info("Company comparison detected for streaming", tickers=tickers)
        effective_top_k = max(body.top_k or 15, 40)
        chunks: list = []
        for t in tickers:
            company_query = body.query
            company_name = next(
                (name for name, tk in COMPANY_TICKER_MAP.items()
                 if tk == t and re.search(r"\b" + re.escape(name) + r"\b", body.query.lower())),
                None,
            )
            if not company_name:
                company_name = t.lower()
                company_query = f"{company_name} {body.query}"
            t_chunks = hybrid_search(
                query=company_query,
                db=db,
                top_k=effective_top_k,
                ticker=t,
                search_depth=80,
            )
            chunks.extend(t_chunks)
    elif intent == "risk_factor_diff":
        chunks = hybrid_search(
            query=body.query,
            db=db,
            top_k=30,
            ticker=ticker,
            search_depth=60,
        )
        item_1a_chunks = [
            c for c in chunks 
            if c.section_title and "item 1a" in c.section_title.lower()
        ]
        if item_1a_chunks:
            chunks = item_1a_chunks
    else:
        effective_top_k = max(body.top_k or 25, 25)
        if intent in STRUCTURED_INTENTS:
            effective_top_k = max(effective_top_k, 80)
            logger.debug(
                "Structured intent — using deeper retrieval",
                intent=intent, top_k=effective_top_k,
            )
        chunks = hybrid_search(
            query=body.query,
            db=db,
            top_k=effective_top_k,
            ticker=ticker,
            search_depth=80 if intent in STRUCTURED_INTENTS else 75,
        )

    if ticker and detect_tickers(body.query) == [ticker] and intent != "company_comparison":
        chunks = filter_chunks_by_ticker(chunks, ticker)

    coverage = validate_coverage(body.query, chunks, intent)
    if coverage.has_gaps:
        chunks = expand_coverage(body.query, chunks, coverage, intent, db)
        if ticker and intent != "company_comparison":
            chunks = filter_expanded_to_single_ticker(chunks, ticker)
        coverage = validate_coverage(body.query, chunks, intent)

    if coverage.has_gaps and intent in ("financial_metrics", "revenue_mix", "company_comparison", "business_segment"):
        logger.warning("Coverage gaps remain despite expansion", gaps=coverage.gap_description)

    prior = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.thread_id == thread.id,
            ChatMessage.id != user_msg.id,
        )
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in prior[-6:]]

    def event_stream():
        full_answer: list[str] = []
        raw_citations = None
        assistant_msg = None

        try:
            gen = generate_answer_stream(body.query, chunks, intent=intent, history=history)
            try:
                while True:
                    token = next(gen)
                    full_answer.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            except StopIteration as e:
                raw_citations = e.value
            except Exception:
                logger.exception("Streaming generation failed")
                yield f"data: {json.dumps({'type': 'error', 'content': 'Generation failed'})}\n\n"
                return
        finally:
            # Always save partial or full answer — runs on normal completion,
            # error, OR client disconnect (GeneratorExit).
            answer = "".join(full_answer)
            if answer.strip():
                try:
                    answer = check_sufficient_evidence(answer, chunks)
                    assistant_msg = ChatMessage(thread_id=thread.id, role="assistant", content=answer)
                    db.add(assistant_msg)
                    db.commit()
                    db.refresh(assistant_msg)
                except Exception:
                    db.rollback()
                    logger.exception("Failed to save streaming answer")

        # ── Normal completion path (GeneratorExit doesn't reach here) ──
        if not assistant_msg or raw_citations is None:
            return

        citations: list[MessageCitation] = []
        for cite in raw_citations:
            citation = MessageCitation(
                message_id=assistant_msg.id,
                chunk_id=cite["chunk_id"],
                page_number=cite["page_number"],
                section_title=cite.get("section_title"),
                excerpt=cite["excerpt"],
                metadata_={
                    "ticker": cite.get("ticker"),
                    "fiscal_year": cite.get("fiscal_year"),
                },
            )
            db.add(citation)
            citations.append(citation)

        if citations:
            db.commit()

        citations_data = [
            {
                'chunk_id': str(c.chunk_id), 
                'page_number': c.page_number, 
                'section_title': c.section_title,
                'ticker': (c.metadata_ or {}).get("ticker"),
                'fiscal_year': (c.metadata_ or {}).get("fiscal_year"),
                'excerpt': c.excerpt
            }
            for c in citations
        ]
        done_response = {
            'type': 'done',
            'citations': citations_data,
            'message_id': str(assistant_msg.id),
            'title': thread_title,
        }
        yield f"data: {json.dumps(done_response)}\n\n"

        logger.info(
            "Streaming ask complete",
            thread_id=thread_id,
            chunks=len(chunks),
            citations=len(citations),
            answer_length=len(answer),
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
