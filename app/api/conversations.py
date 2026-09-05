"""API router for managing chat conversations and messages."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user_id
from app.schemas.conversation import (
    ChatMessageCreate,
    ChatMessageResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
)
from app.services.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Conversations"])
repo = ConversationRepository()


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat conversation session",
)
def create_conversation(
    request: Optional[ConversationCreate] = None,
    user_id: str = Depends(get_current_user_id),
) -> ConversationResponse:
    """Create a new conversation record for the authenticated user."""
    title = request.title if request and request.title else "New Conversation"
    conv = repo.create_conversation(user_id=user_id, title=title)
    return ConversationResponse.model_validate(conv)


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    status_code=status.HTTP_200_OK,
    summary="List all conversations for authenticated user",
)
def list_conversations(
    user_id: str = Depends(get_current_user_id),
) -> list[ConversationResponse]:
    """Retrieve all conversations belonging to the authenticated user."""
    convs = repo.list_user_conversations(user_id=user_id)
    return [ConversationResponse.model_validate(c) for c in convs]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get conversation details by ID",
)
def get_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> ConversationResponse:
    """Retrieve metadata for a specific conversation owned by the authenticated user."""
    conv = repo.get_conversation(user_id=user_id, conversation_id=conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )
    return ConversationResponse.model_validate(conv)


@router.put(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Update conversation title",
)
def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    user_id: str = Depends(get_current_user_id),
) -> ConversationResponse:
    """Update title for a specific conversation owned by the authenticated user."""
    conv = repo.update_conversation_title(
        user_id=user_id, conversation_id=conversation_id, title=request.title
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )
    return ConversationResponse.model_validate(conv)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete conversation and associated messages",
)
def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> None:
    """Delete a conversation record and its messages owned by the authenticated user."""
    success = repo.delete_conversation(user_id=user_id, conversation_id=conversation_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ChatMessageResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all messages in a conversation",
)
def list_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
) -> list[ChatMessageResponse]:
    """Retrieve all messages in a conversation owned by the authenticated user."""
    messages = repo.list_conversation_messages(
        user_id=user_id, conversation_id=conversation_id
    )
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post a message to a conversation",
)
def create_message(
    conversation_id: str,
    request: ChatMessageCreate,
    user_id: str = Depends(get_current_user_id),
) -> ChatMessageResponse:
    """Insert a new message into a conversation owned by the authenticated user."""
    conv = repo.get_conversation(user_id=user_id, conversation_id=conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )

    msg = repo.insert_message(
        conversation_id=conversation_id,
        role=request.role,
        content=request.content,
        citations=request.citations,
        retrieved_chunk_count=request.retrieved_chunk_count,
        retrieval_time_ms=request.retrieval_time_ms,
    )
    return ChatMessageResponse.model_validate(msg)
