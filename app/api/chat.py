"""API router for chat document retrieval operations."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user_id
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import generate_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate grounded AI answer from document chunks",
)
def chat_completion(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
) -> ChatResponse:
    """Perform RAG search and generate grounded AI answer using Google Gemini API.

    Enforces user isolation by restricting search results to document chunks owned by
    the authenticated user. Includes source citations and retrieval metadata in response.
    """
    try:
        return generate_response(request, user_id=user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Chat generation failure for user '%s': %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat generation failure: {e}",
        )

