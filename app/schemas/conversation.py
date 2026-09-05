"""Pydantic schemas for Conversation and ChatMessage CRUD operations."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    """Schema for creating a new conversation."""

    title: Optional[str] = Field(
        default="New Conversation", description="Optional title for the conversation."
    )


class ConversationUpdate(BaseModel):
    """Schema for updating a conversation title."""

    title: str = Field(..., min_length=1, description="New title for the conversation.")


class ConversationResponse(BaseModel):
    """Schema representing a stored conversation."""

    id: str = Field(..., description="Unique conversation UUID.")
    user_id: str = Field(..., description="Authenticated owner user UUID.")
    title: str = Field(..., description="Conversation title.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    updated_at: datetime = Field(..., description="Last update timestamp.")


class ChatMessageCreate(BaseModel):
    """Schema for creating a chat message."""

    role: str = Field(..., description="Message role ('user' or 'assistant').")
    content: str = Field(..., description="Message text content.")
    citations: Optional[list[dict[str, Any]]] = Field(
        default=None, description="Optional source citations for assistant messages."
    )
    retrieved_chunk_count: int = Field(
        default=0, description="Number of retrieved chunks for assistant message."
    )
    retrieval_time_ms: int = Field(
        default=0, description="Retrieval time in milliseconds."
    )


class ChatMessageResponse(BaseModel):
    """Schema representing a stored chat message."""

    id: str = Field(..., description="Unique message UUID.")
    conversation_id: str = Field(..., description="Parent conversation UUID.")
    role: str = Field(..., description="Message role ('user' or 'assistant').")
    content: str = Field(..., description="Message text content.")
    citations: Optional[list[dict[str, Any]]] = Field(
        default=None, description="Optional source citations."
    )
    retrieved_chunk_count: int = Field(
        default=0, description="Number of retrieved chunks."
    )
    retrieval_time_ms: int = Field(
        default=0, description="Retrieval time in ms."
    )
    created_at: datetime = Field(..., description="Creation timestamp.")
