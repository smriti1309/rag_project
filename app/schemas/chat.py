"""Pydantic schemas for RAG chat retrieval requests and responses."""

from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Schema representing incoming chat search request."""

    query: str = Field(
        ..., min_length=1, description="User search query string for RAG retrieval."
    )
    document_id: Optional[str] = Field(
        default=None, description="Optional document ID filter."
    )
    conversation_id: Optional[str] = Field(
        default=None, description="Optional conversation ID to associate and persist chat history."
    )
    top_k: int = Field(
        default=5, ge=1, description="Maximum number of relevant chunks to retrieve."
    )


class RetrievedChunk(BaseModel):
    """Schema representing an individual retrieved document chunk with similarity score."""

    document_id: str = Field(..., description="Document identifier.")
    chunk_id: int = Field(..., description="Chunk ID within the document.")
    page: Optional[int] = Field(
        default=None, description="Page number of the chunk if available."
    )
    source_file: Optional[str] = Field(
        default=None, description="Original uploaded filename."
    )
    text: str = Field(..., description="Complete chunk text content.")
    score: float = Field(..., description="Vector similarity score (Cosine).")


class SourceCitation(BaseModel):
    """Schema representing a citation reference source for a retrieved chunk."""

    document_id: str = Field(..., description="Document identifier.")
    chunk_id: int = Field(..., description="Chunk ID within the document.")
    page: Optional[int] = Field(
        default=None, description="Page number of the chunk if available."
    )
    source_file: Optional[str] = Field(
        default=None, description="Original uploaded filename."
    )
    score: float = Field(..., description="Vector similarity score (Cosine).")
    text: Optional[str] = Field(
        default=None, description="Complete chunk text content."
    )


class ChatResponse(BaseModel):
    """Schema representing the grounded RAG chat response."""

    query: str = Field(..., description="Original user query.")
    answer: str = Field(..., description="Grounded AI response generated from context.")
    conversation_id: Optional[str] = Field(
        default=None, description="Optional conversation ID associated with the response."
    )
    sources: list[SourceCitation] = Field(
        default_factory=list, description="List of source citations for the retrieved context."
    )
    retrieved_chunk_count: int = Field(
        default=0, description="Total number of chunks retrieved matching threshold."
    )
    retrieval_time_ms: int = Field(
        default=0, description="Vector search retrieval time in milliseconds."
    )


