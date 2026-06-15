from __future__ import annotations

from collections.abc import Generator

from openai import APIError, APIConnectionError, APIStatusError, OpenAI as OpenAIClient, RateLimitError

from app.config import settings
from app.core.logging import logger
from app.domain.retrieval import RetrievedChunk
from app.domain.workflows import (
    STRUCTURED_INTENTS,
    build_structured_answer,
    build_workflow_context,
    check_sufficient_evidence,
    validate_evidence,
)

LLM_UNAVAILABLE_MESSAGE = (
    "⚠️ **AI narrative generation is temporarily unavailable** — the language model "
    "is currently rate-limited. However, the **pre-computed financial tables above** "
    "contain all the extracted data and are complete and accurate. "
    "Please try again in a few minutes for the full narrative analysis."
)


_LLM_TIMEOUT = 120.0  # max seconds for LLM call


def _get_groq_client() -> OpenAIClient:
    return OpenAIClient(
        base_url=settings.groq_base_url,
        api_key=settings.groq_api_key,
        timeout=_LLM_TIMEOUT,
    )


def _build_messages(
    query: str,
    chunks: list[RetrievedChunk],
    intent: str = "general",
    history: list[dict] | None = None,
) -> tuple[str, str, list[dict]]:
    return ("", "", build_workflow_context(query, chunks, intent, history))


def generate_answer(
    query: str,
    chunks: list[RetrievedChunk],
    intent: str = "general",
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    logger.info(
        "Generating RAG answer",
        query=query[:80],
        chunk_count=len(chunks),
        model=settings.groq_llm_model,
        intent=intent,
        history_count=len(history) if history else 0,
    )

    if intent in STRUCTURED_INTENTS:
        tables, messages = build_structured_answer(query, chunks, intent, history=history)
        if not messages:
            return tables, _build_citations(chunks)
    else:
        validation_msg = validate_evidence(query, chunks, intent)
        if validation_msg is not None:
            logger.info(
                "Pre-generation validation failed for non-structured intent",
                query=query[:80], intent=intent, detail=validation_msg,
            )
            return validation_msg, _build_citations(chunks)
        _, _, messages = _build_messages(query, chunks, intent, history=history)
        tables = ""

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=settings.groq_llm_model,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )
        narrative = response.choices[0].message.content or ""
        narrative = check_sufficient_evidence(narrative, chunks)
    except RateLimitError:
        logger.warning("Groq rate limit reached in generate_answer", query=query[:80])
        narrative = LLM_UNAVAILABLE_MESSAGE
    except (APIError, APIConnectionError, APIStatusError) as e:
        logger.error("LLM API error in generate_answer", error=str(e), query=query[:80])
        narrative = (
            "⚠️ **AI narrative generation encountered an error.** "
            "The pre-computed financial data above is complete and accurate. "
            "Please try your query again."
        )

    answer = f"{tables}\n\n{narrative}" if tables else narrative

    citations = _build_citations(chunks)

    return answer, citations


def generate_answer_stream(
    query: str,
    chunks: list[RetrievedChunk],
    intent: str = "general",
    history: list[dict] | None = None,
) -> Generator[str, None, list[dict]]:
    logger.info(
        "Generating streaming RAG answer",
        query=query[:80],
        chunk_count=len(chunks),
        model=settings.groq_llm_model,
        intent=intent,
        history_count=len(history) if history else 0,
    )

    if intent in STRUCTURED_INTENTS:
        tables, messages = build_structured_answer(query, chunks, intent, history=history)
        if not messages:
            yield tables
            return _build_citations(chunks)
        yield f"{tables}\n\n"
    else:
        validation_msg = validate_evidence(query, chunks, intent)
        if validation_msg is not None:
            logger.info(
                "Pre-generation validation failed for non-structured streaming intent",
                query=query[:80], intent=intent, detail=validation_msg,
            )
            yield validation_msg
            return _build_citations(chunks)
        _, _, messages = _build_messages(query, chunks, intent, history=history)

    try:
        client = _get_groq_client()
        stream = client.chat.completions.create(
            model=settings.groq_llm_model,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
    except RateLimitError:
        logger.warning("Groq rate limit reached in generate_answer_stream", query=query[:80])
        yield LLM_UNAVAILABLE_MESSAGE
    except (APIError, APIConnectionError, APIStatusError) as e:
        logger.error("LLM API error in generate_answer_stream", error=str(e), query=query[:80])
        yield (
            "⚠️ **AI narrative generation encountered an error.** "
            "The pre-computed financial data above is complete and accurate. "
            "Please try your query again."
        )

    citations = _build_citations(chunks)

    logger.info("Streaming RAG answer complete", query=query[:80], intent=intent)
    return citations


def _build_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for chunk in chunks:
        cid = str(chunk.chunk_id)
        if cid in seen:
            continue
        seen.add(cid)
        result.append({
            "chunk_id": chunk.chunk_id,
            "page_number": chunk.page_number,
            "section_title": chunk.section_title,
            "ticker": chunk.ticker,
            "fiscal_year": chunk.fiscal_year,
            "excerpt": chunk.content[:500],
        })
    return result
