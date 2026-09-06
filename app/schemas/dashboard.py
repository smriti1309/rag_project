"""Schema module for dashboard statistics and system health indicators."""

from typing import Optional
from pydantic import BaseModel, Field


class DashboardStatsResponse(BaseModel):
    """Schema model for user-isolated dashboard statistics and real-time system health."""

    documents_indexed: int = Field(
        ..., description="Number of successfully indexed documents owned by authenticated user"
    )
    total_chunks: int = Field(
        ..., description="Total count of text chunks across user's indexed documents"
    )
    total_embeddings: int = Field(
        ..., description="Number of vector embeddings stored in Qdrant for authenticated user"
    )
    qdrant_status: str = Field(
        ..., description="Real-time Qdrant connection status ('Connected' or 'Disconnected')"
    )
    backend_status: str = Field(
        ..., description="FastAPI application operational status"
    )
    embedding_model: str = Field(
        ..., description="Configured embedding model name and vector dimension"
    )
    last_uploaded_time: Optional[str] = Field(
        None, description="Timestamp of most recent document upload (YYYY-MM-DD HH:MM:SS) or None"
    )
    qdrant_collection: str = Field(
        ..., description="Active Qdrant collection name"
    )
