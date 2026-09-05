"""API router for document upload, listing, and deletion with user isolation and R2 integration."""

from datetime import datetime, timezone
import logging
from typing import Any
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from qdrant_client import models

from app.core.auth import get_current_user_id
from app.core.config import settings
from app.schemas.upload import UploadResponse
from app.services.document_repository import DocumentRepository
from app.services.ingestion_service import ingest_document
from app.services.qdrant_service import QdrantService
from app.services.r2_storage_service import R2StorageService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Upload"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document or image",
)
def upload_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
) -> UploadResponse:
    """Upload a PDF, TXT, DOCX, or Image file to Cloudflare R2 and run ingestion pipeline for text documents.

    Accepts PDF, TXT, DOCX, PNG, JPG, JPEG, and WEBP files up to 50MB. Uploads to R2
    under user-isolated path {user_id}/{document_id}/{filename} and records metadata in
    Supabase Database. Runs RAG indexing for PDFs/TXTs.
    """
    try:
        import os
        print("=== TEMPORARY LOGGING BEFORE QDRANTSERVICE CREATION ===")
        print("settings.qdrant_url:", settings.qdrant_url)
        print("settings.qdrant_collection_name:", settings.qdrant_collection_name)
        print("settings.qdrant_api_key (first 5):", settings.qdrant_api_key[:5] if settings.qdrant_api_key else None)
        print("current working directory:", os.getcwd())
        print("os.environ.get('QDRANT_URL'):", os.environ.get("QDRANT_URL"))
        print("os.environ['QDRANT_API_KEY'] exists?:", "QDRANT_API_KEY" in os.environ)

        return ingest_document(file, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage failure: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failure: {e}",
        )


@router.get(
    "/documents",
    response_model=list[UploadResponse],
    status_code=status.HTTP_200_OK,
    summary="List all documents owned by authenticated user",
)
def list_documents(
    user_id: str = Depends(get_current_user_id),
) -> list[UploadResponse]:
    """Query Supabase Database and return metadata for all documents owned by the authenticated user."""
    repo = DocumentRepository()
    records = repo.list_user_documents(user_id)

    documents: list[UploadResponse] = []
    for doc in records:
        uploaded_at = doc.get("uploaded_at")
        if isinstance(uploaded_at, str):
            try:
                uploaded_at_dt = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
            except Exception:
                uploaded_at_dt = datetime.now(timezone.utc)
        elif isinstance(uploaded_at, datetime):
            uploaded_at_dt = uploaded_at
        else:
            uploaded_at_dt = datetime.now(timezone.utc)

        filename = doc.get("filename", "")
        documents.append(
            UploadResponse(
                document_id=doc.get("id", ""),
                original_filename=filename,
                stored_filename=filename,
                size=doc.get("file_size", 0),
                uploaded_at=uploaded_at_dt,
                status=doc.get("status", "uploaded"),
                chunk_count=doc.get("chunk_count", 0),
                file_type=doc.get("file_type", "pdf"),
                mime_type=doc.get("mime_type", "application/pdf"),
                object_key=doc.get("object_key"),
                user_id=doc.get("user_id"),
                width=doc.get("width"),
                height=doc.get("height"),
            )
        )

    return documents


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete document owned by authenticated user",
)
def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Purge document from Cloudflare R2, Qdrant vector DB, chunk outputs, and Supabase Database."""
    repo = DocumentRepository()
    doc = repo.get_document(user_id, document_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or unauthorized to delete.",
        )

    # 1. Delete object from Cloudflare R2
    object_key = doc.get("object_key")
    if object_key:
        r2_service = R2StorageService()
        r2_service.delete_file(object_key)

    # 2. Delete vectors from Qdrant Vector DB
    try:
        qdrant_service = QdrantService()
        if qdrant_service.client.collection_exists(settings.qdrant_collection_name):
            qdrant_service.client.delete(
                collection_name=settings.qdrant_collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
            )
            logger.info("Deleted Qdrant vector points for document '%s'.", document_id)
    except Exception as e:
        logger.warning("Failed to delete Qdrant vectors for '%s': %s", document_id, e)

    # 3. Clean up local chunk and embedding output files if existing
    chunk_file = settings.chunk_directory / f"{document_id}.json"
    if chunk_file.exists():
        try:
            chunk_file.unlink()
        except Exception:
            pass

    embedding_file = settings.embedding_directory / f"{document_id}.embeddings.json"
    if embedding_file.exists():
        try:
            embedding_file.unlink()
        except Exception:
            pass

    # 4. Delete document metadata row from Supabase Database
    repo.delete_document(user_id, document_id)

    return {"success": True, "message": f"Document '{document_id}' deleted successfully."}
