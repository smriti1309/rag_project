from pathlib import Path
from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    # Application server configuration
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    upload_directory: Path = Path("data/uploads")
    processed_directory: Path = Path("data/processed")
    chunk_directory: Path = Path("data/chunks")
    temp_directory: Path = Path("temp")
    max_file_size: int = 50 * 1024 * 1024  # 50 MB in bytes
    allowed_extensions: set[str] = {
        ".pdf",
        ".txt",
        ".docx",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }

    # Cloudflare R2 configuration
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str = "ai-knowledge-engine"
    r2_endpoint: str | None = None

    # Supabase configuration
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    database_url: str | None = None

    # Chunker configuration
    chunk_max_words: int = 500
    chunk_overlap: int = 30
    semantic_similarity_threshold: float = 0.75
    semantic_chunk_min_words: int = 50
    semantic_chunk_max_words: int = 500
    semantic_embedding_concurrency: int = 5

    # Embedding configuration
    embedding_directory: Path = Path("data/embeddings")
    embedding_model: str = "gemini-embedding-2"
    embedding_batch_size: int = 32

    # Qdrant configuration
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "knowledge_base_v2"
    qdrant_batch_size: int = 500

    # BM25 & Hybrid Configuration
    bm25_directory: Path = Path("data/bm25")
    hybrid_candidate_k: int = 20
    hybrid_top_k: int = 5
    rrf_k: int = 60

    @field_validator("qdrant_collection_name", mode="before")
    @classmethod
    def update_qdrant_collection_name(cls, v: Any) -> str:
        if v == "knowledge_base":
            return "knowledge_base_v2"
        return v or "knowledge_base_v2"

    # Gemini LLM configuration
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    max_context_chars: int = 20000
    min_similarity_score: float = 0.65

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
