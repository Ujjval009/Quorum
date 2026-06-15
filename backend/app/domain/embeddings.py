from __future__ import annotations

from openai import OpenAI as OpenAIClient

from app.config import settings
from app.core.logging import logger


def _get_ollama_client() -> OpenAIClient:
    return OpenAIClient(
        base_url=settings.ollama_base_url,
        api_key="ollama",
    )


def generate_embedding(text: str) -> list[float]:
    provider = settings.embedding_provider
    logger.debug("Generating embedding", provider=provider, model=settings.embedding_model)

    if provider == "ollama":
        return _ollama_embed(text)
    else:
        logger.warning("Unknown embedding provider, falling back to ollama", provider=provider)
        return _ollama_embed(text)


def _ollama_embed(text: str) -> list[float]:
    try:
        client = _get_ollama_client()
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )
        return response.data[0].embedding
    except Exception:
        logger.exception("Ollama embedding failed", model=settings.embedding_model)
        raise


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    provider = settings.embedding_provider
    logger.info("Generating embeddings batch", provider=provider, count=len(texts))

    if provider == "ollama":
        try:
            client = _get_ollama_client()
            response = client.embeddings.create(
                model=settings.embedding_model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception:
            logger.exception("Batch embedding failed, falling back to individual")
            return [generate_embedding(t) for t in texts]

    return [generate_embedding(t) for t in texts]
