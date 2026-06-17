from __future__ import annotations

from pydantic_settings import BaseSettings
from sqlalchemy.engine.url import URL

from app.core.logging import logger


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "postgres"
    db_user: str = "postgres"
    db_password: str = ""

    # LLM (Groq / OpenRouter / any OpenAI-compatible)
    groq_api_key: str
    groq_llm_model: str = "llama-3.3-70b-versatile"
    llm_base_url: str = ""  # overrides groq_base_url when set (e.g. OpenRouter)

    # Embeddings
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    ollama_base_url: str = "http://localhost:11434/v1"
    hf_token: str = ""

    # Ingestion
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Retrieval
    retrieval_top_k: int = 25
    retrieval_search_depth: int = 75  # per-method search depth (vs output count)
    retrieval_context_chars: int = 1200  # max chars per chunk in LLM context
    retrieval_rrf_k: int = 60
    retrieval_alpha: float = 0.5

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Server
    allowed_origins: str = "http://localhost:5173"

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def groq_base_url(self) -> str:
        return self.llm_base_url or "https://api.groq.com/openai/v1"


settings = Settings()
logger.info(
    "Configuration loaded",
    db_host=settings.db_host,
    db_name=settings.db_name,
    embedding_provider=settings.embedding_provider,
    groq_model=settings.groq_llm_model,
)
