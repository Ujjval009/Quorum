from __future__ import annotations

from openai import OpenAI as OpenAIClient

from app.config import settings
from app.core.logging import logger


def _get_client(base_url: str, api_key: str) -> OpenAIClient:
    return OpenAIClient(base_url=base_url, api_key=api_key)


def _huggingface_embed(text: str) -> list[float]:
    client = _get_client(
        base_url="https://router.huggingface.co/v1",
        api_key=settings.hf_token or "",
    )
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return response.data[0].embedding


def _huggingface_embed_batch(texts: list[str]) -> list[list[float]]:
    client = _get_client(
        base_url="https://router.huggingface.co/v1",
        api_key=settings.hf_token or "",
    )
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _ollama_embed(text: str) -> list[float]:
    client = _get_client(
        base_url=settings.ollama_base_url,
        api_key="ollama",
    )
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return response.data[0].embedding


def _ollama_embed_batch(texts: list[str]) -> list[list[float]]:
    client = _get_client(
        base_url=settings.ollama_base_url,
        api_key="ollama",
    )
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


def generate_embedding(text: str) -> list[float]:
    provider = settings.embedding_provider
    logger.debug("Generating embedding", provider=provider, model=settings.embedding_model)

    if provider == "ollama":
        return _ollama_embed(text)
    elif provider == "huggingface":
        return _huggingface_embed(text)
    else:
        logger.warning("Unknown embedding provider, falling back to ollama", provider=provider)
        return _ollama_embed(text)


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    provider = settings.embedding_provider
    logger.info("Generating embeddings batch", provider=provider, count=len(texts))

    if provider == "ollama":
        try:
            return _ollama_embed_batch(texts)
        except Exception:
            logger.exception("Batch embedding failed, falling back to individual")
            return [generate_embedding(t) for t in texts]
    elif provider == "huggingface":
        return _huggingface_embed_batch(texts)

    return [generate_embedding(t) for t in texts]
