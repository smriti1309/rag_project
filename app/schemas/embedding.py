"""Pydantic schemas for document embeddings."""

from typing import Optional
from pydantic import BaseModel, Field


class ChunkEmbedding(BaseModel):
    """Schema representing an individual chunk's embedding vector."""

    chunk_id: int = Field(
        ..., description="Unique integer ID of the chunk within the document."
    )
    page: Optional[int] = Field(
        default=None, description="Page number of the chunk if available, otherwise None."
    )
    text: Optional[str] = Field(
        default=None, description="Complete text content of the chunk."
    )
    embedding: list[float] = Field(
        ..., description="Vector embedding representation for the chunk."
    )


class EmbeddingDocument(BaseModel):
    """Schema representing the root JSON output structure for document embeddings."""

    document_id: str = Field(
        ..., description="Document identifier (filename without extension)."
    )
    user_id: Optional[str] = Field(
        default=None, description="Authenticated owner user ID."
    )
    source_file: Optional[str] = Field(
        default=None, description="Original uploaded filename."
    )
    model: str = Field(
        ..., description="Name of the embedding model used to generate vectors."
    )
    dimension: int = Field(
        ..., description="Vector dimension size of the generated embeddings."
    )
    embeddings: list[ChunkEmbedding] = Field(
        default_factory=list, description="List of chunk embedding records."
    )


