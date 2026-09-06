"""API router for user-isolated dashboard statistics and system health monitoring."""

from datetime import datetime
import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, status
from qdrant_client import models

from app.core.auth import get_current_user_id
from app.core.config import settings
from app.schemas.dashboard import DashboardStatsResponse
from app.services.document_repository import DocumentRepository
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Dashboard"])


def _format_timestamp(ts: Optional[Any]) -> Optional[str]:
    """Format datetime object or ISO string to standard YYYY-MM-DD HH:MM:SS format."""
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ts[:19].replace("T", " ")
    return str(ts)


@router.get(
    "/dashboard/stats",
    response_model=DashboardStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user-isolated dashboard statistics and system health",
)
def get_dashboard_stats(
    user_id: str = Depends(get_current_user_id),
) -> DashboardStatsResponse:
    """Retrieve user-isolated statistics (documents, chunks, vectors) and real-time system health.

    Enforces strict user isolation by filtering documents and Qdrant vector counts by authenticated user_id.
    """
    repo = DocumentRepository()
    doc_records = repo.list_user_documents(user_id)

    indexed_docs = [doc for doc in doc_records if doc.get("status") == "indexed"]
    documents_indexed = len(indexed_docs)
    total_chunks = sum(doc.get("chunk_count", 0) for doc in indexed_docs)

    last_uploaded_time: Optional[str] = None
    if doc_records:
        latest_upload = doc_records[0].get("uploaded_at") or doc_records[0].get("created_at")
        last_uploaded_time = _format_timestamp(latest_upload)

    qdrant_status = "Disconnected"
    total_embeddings = 0

    try:
        qdrant_service = QdrantService()
        if qdrant_service.client.collection_exists(settings.qdrant_collection_name):
            qdrant_status = "Connected"
            count_res = qdrant_service.client.count(
                collection_name=settings.qdrant_collection_name,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id),
                        )
                    ]
                ),
            )
            total_embeddings = count_res.count
    except Exception as e:
        logger.warning("Qdrant health check/count failed for user '%s': %s", user_id, e)
        qdrant_status = "Disconnected"
        total_embeddings = 0

    embedding_model_info = f"{settings.embedding_model} (768D)"

    return DashboardStatsResponse(
        documents_indexed=documents_indexed,
        total_chunks=total_chunks,
        total_embeddings=total_embeddings,
        qdrant_status=qdrant_status,
        backend_status="Healthy",
        embedding_model=embedding_model_info,
        last_uploaded_time=last_uploaded_time,
        qdrant_collection=settings.qdrant_collection_name,
    )
