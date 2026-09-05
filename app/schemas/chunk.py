"""Pydantic schemas for text document chunking."""

from typing import Optional
from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """Schema representing an individual text chunk."""

    chunk_id: int = Field(
        ..., description="Unique integer ID of the chunk within the document, starting at 1."
    )
    page: Optional[int] = Field(
        default=None, description="Page number of the chunk if available, otherwise None."
    )
    start_char: int = Field(
        ..., description="Starting character index in the source text document."
    )
    end_char: int = Field(
        ..., description="Ending character index in the source text document."
    )
    text: str = Field(..., description="Text content of the chunk.")


class ChunkDocument(BaseModel):
    """Schema representing the root JSON output structure for document chunks."""

    document_id: str = Field(
        ..., description="Document identifier (filename without extension)."
    )
    user_id: Optional[str] = Field(
        default=None, description="Authenticated owner user ID."
    )
    source_file: Optional[str] = Field(
        default=None, description="Original uploaded filename."
    )
    chunks: list[Chunk] = Field(
        default_factory=list, description="List of document chunks."
    )

