from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError

from openai import OpenAI as OpenAIClient

from app.config import settings
from app.core.logging import logger


def _get_ollama_client() -> OpenAIClient:
    return OpenAIClient(
        base_url=settings.ollama_base_url,
        api_key="ollama",
    )


def _huggingface_embed(text: str) -> list[float]:
    url = f"https://api-inference.huggingface.co/models/{settings.embedding_model}"
    headers = {"Content-Type": "application/json"}
    if settings.hf_token:
        headers["Authorization"] = f"Bearer {settings.hf_token}"
    data = json.dumps({"inputs": text}).encode()
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        if isinstance(result, list) and result and isinstance(result[0], (int, float)):
            return result
        if isinstance(result, dict) and "error" in result:
            logger.error("HuggingFace API error", error=result["error"])
            raise RuntimeError(result["error"])
        raise RuntimeError(f"Unexpected HF response: {result}")
    except URLError as e:
        logger.exception("HuggingFace embedding request failed")
        raise RuntimeError(f"HuggingFace request failed: {e.reason}") from e


def _huggingface_embed_batch(texts: list[str]) -> list[list[float]]:
    url = f"https://api-inference.huggingface.co/models/{settings.embedding_model}"
    headers = {"Content-Type": "application/json"}
    if settings.hf_token:
        headers["Authorization"] = f"Bearer {settings.hf_token}"
    data = json.dumps({"inputs": texts}).encode()
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result
        if isinstance(result, dict) and "error" in result:
            logger.error("HuggingFace batch API error", error=result["error"])
            raise RuntimeError(result["error"])
        raise RuntimeError(f"Unexpected HF batch response: {result}")
    except URLError as e:
        logger.exception("HuggingFace batch embedding failed, falling back to individual")
        return [_huggingface_embed(t) for t in texts]


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
    elif provider == "huggingface":
        return _huggingface_embed_batch(texts)

    return [generate_embedding(t) for t in texts]
