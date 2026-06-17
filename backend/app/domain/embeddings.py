from __future__ import annotations

from huggingface_hub import InferenceClient as HFInferenceClient
from openai import OpenAI as OpenAIClient

from app.config import settings
from app.core.logging import logger


def _get_ollama_client() -> OpenAIClient:
    return OpenAIClient(
        base_url=settings.ollama_base_url,
        api_key="ollama",
    )


def _get_hf_client() -> HFInferenceClient:
    return HFInferenceClient(api_key=settings.hf_token or "")


def _huggingface_embed(text: str) -> list[float]:
    client = _get_hf_client()
    result = client.feature_extraction(
        text=text,
        model=settings.embedding_model,
    )
    if hasattr(result, "tolist"):
        return result.tolist()
    if isinstance(result, list) and result and isinstance(result[0], (int, float)):
        return result
    if isinstance(result, list) and result and isinstance(result[0], list):
        return result[0]
    raise RuntimeError(f"Unexpected HF feature_extraction response: {result}")


def _huggingface_embed_batch(texts: list[str]) -> list[list[float]]:
    client = _get_hf_client()
    result = client.feature_extraction(
        text=texts,
        model=settings.embedding_model,
    )
    if hasattr(result, "tolist"):
        return result.tolist()
    if isinstance(result, list) and result and isinstance(result[0], list):
        return result
    raise RuntimeError(f"Unexpected HF batch response: {result}")


def _ollama_embed(text: str) -> list[float]:
    client = _get_ollama_client()
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return response.data[0].embedding


def _ollama_embed_batch(texts: list[str]) -> list[list[float]]:
    client = _get_ollama_client()
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
