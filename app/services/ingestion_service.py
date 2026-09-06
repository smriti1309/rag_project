"""Ingestion service module for orchestrating document uploads, Cloudflare R2 storage, Supabase metadata, and RAG indexing."""

from datetime import datetime, timezone
import io
import json
import logging
import mimetypes
from pathlib import Path
import shutil
from typing import Optional
import uuid
from fastapi import UploadFile
from PIL import Image

from app.core.config import Settings, settings as default_settings
from app.schemas.upload import UploadResponse
from app.services.bm25_service import BM25Service
from app.services.chunker_service import chunk_document
from app.services.document_repository import DocumentRepository
from app.services.docx_parser_service import parse_docx
from app.services.embedding_service import embed_document
from app.services.pdf_parser_service import parse_pdf
from app.services.qdrant_service import QdrantService
from app.services.r2_storage_service import R2StorageService

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestration service for the document ingestion pipeline."""

    def __init__(
        self,
        qdrant_service: Optional[QdrantService] = None,
        bm25_service: Optional[BM25Service] = None,
        r2_storage_service: Optional[R2StorageService] = None,
        document_repository: Optional[DocumentRepository] = None,
        embedding_service: Optional[EmbeddingService] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize IngestionService.

        Args:
            qdrant_service: Optional QdrantService instance.
            bm25_service: Optional BM25Service instance.
            r2_storage_service: Optional R2StorageService instance.
            document_repository: Optional DocumentRepository instance.
            embedding_service: Optional EmbeddingService instance.
            settings: Optional Settings instance.
        """
        self.settings = settings or default_settings
        self.qdrant_service = qdrant_service or QdrantService(settings=self.settings)
        self.bm25_service = bm25_service or BM25Service(settings=self.settings)
        self.r2_storage_service = r2_storage_service or R2StorageService(settings=self.settings)
        self.document_repository = document_repository or DocumentRepository(settings=self.settings)
        self.embedding_service = embedding_service

    def _determine_file_metadata(self, filename: str) -> tuple[str, str]:
        """Determine file_type and mime_type from filename.

        Args:
            filename: Original uploaded filename.

        Returns:
            tuple[str, str]: (file_type, mime_type)
        """
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return "pdf", "application/pdf"
        elif ext == ".txt":
            return "txt", "text/plain"
        elif ext == ".docx":
            return "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif ext in (".png", ".jpg", ".jpeg", ".webp"):
            mime = f"image/{ext[1:]}" if ext != ".jpg" else "image/jpeg"
            return "image", mime
        else:
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            return "document", mime

    def ingest_document(self, file: UploadFile, user_id: str) -> UploadResponse:
        """Upload file to Cloudflare R2, store metadata in Supabase DB, and run RAG pipeline for PDFs/TXTs/DOCXs.

        Args:
            file: Uploaded file object.
            user_id: Authenticated Supabase user ID.

        Returns:
            UploadResponse: Stored document metadata schema.

        Raises:
            ValueError: If validation fails.
            Exception: If pipeline execution fails.
        """
        if not file.filename:
            raise ValueError("Filename must be provided.")

        original_filename = file.filename
        ext = Path(original_filename).suffix.lower()

        if ext not in self.settings.allowed_extensions:
            raise ValueError(f"File extension '{ext}' is not allowed.")

        content = file.file.read()
        if len(content) == 0:
            raise ValueError("Uploaded file is empty.")

        if len(content) > self.settings.max_file_size:
            raise ValueError(
                f"File size ({len(content)} bytes) exceeds the maximum allowed limit of {self.settings.max_file_size} bytes."
            )

        document_id = str(uuid.uuid4())
        file_type, mime_type = self._determine_file_metadata(original_filename)

        # Extract image dimensions for image uploads
        width: Optional[int] = None
        height: Optional[int] = None
        if file_type == "image":
            try:
                with Image.open(io.BytesIO(content)) as img:
                    width, height = img.size
            except Exception as e:
                logger.warning("Failed to extract image dimensions for '%s': %s", original_filename, e)

        # Upload original file to Cloudflare R2
        object_key = self.r2_storage_service.generate_object_key(user_id, document_id, original_filename)
        self.r2_storage_service.upload_file(content, object_key, content_type=mime_type)

        now_iso = datetime.now(timezone.utc).isoformat()
        initial_status = "uploaded" if file_type == "image" else "processing"

        # Record initial metadata in Supabase PostgreSQL
        doc_record = {
            "id": document_id,
            "user_id": user_id,
            "filename": original_filename,
            "object_key": object_key,
            "file_size": len(content),
            "mime_type": mime_type,
            "file_type": file_type,
            "status": initial_status,
            "chunk_count": 0,
            "width": width,
            "height": height,
            "uploaded_at": now_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        self.document_repository.insert_document(doc_record)

        chunk_count = 0
        final_status = initial_status

        # If PDF, TXT, or DOCX, run RAG ingestion pipeline using a temporary directory
        if file_type in ("pdf", "txt", "docx"):
            temp_dir = self.settings.temp_directory / document_id
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / original_filename

            try:
                temp_file_path.write_bytes(content)

                # Step 1: Parse (PDF parser, DOCX parser, or TXT)
                if file_type == "pdf":
                    txt_path = parse_pdf(temp_file_path)
                elif file_type == "docx":
                    txt_path = parse_docx(temp_file_path)
                else:
                    txt_path = temp_file_path

                # Step 2: Chunk
                chunk_json_path = chunk_document(
                    txt_path,
                    source_file=original_filename,
                    document_id=document_id,
                    user_id=user_id,
                    embedding_service=self.embedding_service,
                )

                # Step 2.5: Index in BM25
                self.bm25_service.index_document(chunk_json_path)

                # Step 3: Embed
                embedding_json_path = embed_document(
                    chunk_json_path,
                    user_id=user_id,
                    document_id=document_id,
                    source_file=original_filename,
                )

                # Step 4: Index in Qdrant Vector DB
                self.qdrant_service.index_document(embedding_json_path)

                # Calculate chunk count from chunk JSON
                try:
                    import json
                    with open(chunk_json_path, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                        chunk_count = len(c_data.get("chunks", []))
                except Exception:
                    chunk_count = 0

                final_status = "indexed"
                self.document_repository.update_document_status(document_id, final_status, chunk_count)
            except Exception as e:
                logger.error("Ingestion pipeline error for '%s': %s", original_filename, e)
                self.document_repository.update_document_status(document_id, "failed", 0)
                raise
            finally:
                # Clean up temporary directory completely
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)

        return UploadResponse(
            document_id=document_id,
            original_filename=original_filename,
            stored_filename=original_filename,
            size=len(content),
            uploaded_at=datetime.now(timezone.utc),
            status=final_status,
            chunk_count=chunk_count,
            file_type=file_type,
            mime_type=mime_type,
            object_key=object_key,
            user_id=user_id,
            width=width,
            height=height,
        )

    def ingest_document_stream(self, file: UploadFile, user_id: str):
        """Upload file to Cloudflare R2, store metadata in Supabase DB, and run RAG pipeline with stage streaming.

        Args:
            file: Uploaded file object.
            user_id: Authenticated Supabase user ID.

        Yields:
            str: NDJSON line representing ingestion pipeline stage progress or completion/error payload.
        """
        try:
            if not file.filename:
                raise ValueError("Filename must be provided.")

            original_filename = file.filename
            ext = Path(original_filename).suffix.lower()

            if ext not in self.settings.allowed_extensions:
                raise ValueError(f"File extension '{ext}' is not allowed.")

            content = file.file.read()
            if len(content) == 0:
                raise ValueError("Uploaded file is empty.")

            if len(content) > self.settings.max_file_size:
                raise ValueError(
                    f"File size ({len(content)} bytes) exceeds the maximum allowed limit of {self.settings.max_file_size} bytes."
                )

            document_id = str(uuid.uuid4())
            file_type, mime_type = self._determine_file_metadata(original_filename)

            yield json.dumps({
                "stage": "uploading",
                "progress": 20,
                "message": "Uploading file to storage & creating document record...",
            }) + "\n"

            # Extract image dimensions for image uploads
            width: Optional[int] = None
            height: Optional[int] = None
            if file_type == "image":
                try:
                    with Image.open(io.BytesIO(content)) as img:
                        width, height = img.size
                except Exception as e:
                    logger.warning("Failed to extract image dimensions for '%s': %s", original_filename, e)

            # Upload original file to Cloudflare R2
            object_key = self.r2_storage_service.generate_object_key(user_id, document_id, original_filename)
            self.r2_storage_service.upload_file(content, object_key, content_type=mime_type)

            now_iso = datetime.now(timezone.utc).isoformat()
            initial_status = "uploaded" if file_type == "image" else "processing"

            # Record initial metadata in Supabase PostgreSQL
            doc_record = {
                "id": document_id,
                "user_id": user_id,
                "filename": original_filename,
                "object_key": object_key,
                "file_size": len(content),
                "mime_type": mime_type,
                "file_type": file_type,
                "status": initial_status,
                "chunk_count": 0,
                "width": width,
                "height": height,
                "uploaded_at": now_iso,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            self.document_repository.insert_document(doc_record)

            chunk_count = 0
            final_status = initial_status

            # If PDF, TXT, or DOCX, run RAG ingestion pipeline using a temporary directory
            if file_type in ("pdf", "txt", "docx"):
                temp_dir = self.settings.temp_directory / document_id
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_file_path = temp_dir / original_filename

                try:
                    temp_file_path.write_bytes(content)

                    # Step 1: Parse (PDF parser, DOCX parser, or TXT)
                    yield json.dumps({
                        "stage": "parsing",
                        "progress": 40,
                        "message": "Parsing and extracting document text...",
                    }) + "\n"

                    if file_type == "pdf":
                        txt_path = parse_pdf(temp_file_path)
                    elif file_type == "docx":
                        txt_path = parse_docx(temp_file_path)
                    else:
                        txt_path = temp_file_path

                    # Step 2: Chunk
                    yield json.dumps({
                        "stage": "chunking",
                        "progress": 60,
                        "message": "Chunking document into semantic text units...",
                    }) + "\n"

                    chunk_json_path = chunk_document(
                        txt_path,
                        source_file=original_filename,
                        document_id=document_id,
                        user_id=user_id,
                        embedding_service=self.embedding_service,
                    )

                    # Step 2.5: Index in BM25
                    self.bm25_service.index_document(chunk_json_path)

                    # Step 3: Embed
                    yield json.dumps({
                        "stage": "embedding",
                        "progress": 80,
                        "message": "Generating vector embeddings with Gemini...",
                    }) + "\n"

                    embedding_json_path = embed_document(
                        chunk_json_path,
                        user_id=user_id,
                        document_id=document_id,
                        source_file=original_filename,
                    )

                    # Step 4: Index in Qdrant Vector DB
                    yield json.dumps({
                        "stage": "indexing",
                        "progress": 95,
                        "message": "Storing vectors in Qdrant & updating search index...",
                    }) + "\n"

                    self.qdrant_service.index_document(embedding_json_path)

                    # Calculate chunk count from chunk JSON
                    try:
                        with open(chunk_json_path, "r", encoding="utf-8") as f:
                            c_data = json.load(f)
                            chunk_count = len(c_data.get("chunks", []))
                    except Exception:
                        chunk_count = 0

                    final_status = "indexed"
                    self.document_repository.update_document_status(document_id, final_status, chunk_count)
                except Exception as e:
                    logger.error("Ingestion pipeline error for '%s': %s", original_filename, e)
                    self.document_repository.update_document_status(document_id, "failed", 0)
                    raise
                finally:
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)

            response_payload = UploadResponse(
                document_id=document_id,
                original_filename=original_filename,
                stored_filename=original_filename,
                size=len(content),
                uploaded_at=datetime.now(timezone.utc),
                status=final_status,
                chunk_count=chunk_count,
                file_type=file_type,
                mime_type=mime_type,
                object_key=object_key,
                user_id=user_id,
                width=width,
                height=height,
            )

            yield json.dumps({
                "stage": "completed",
                "progress": 100,
                "message": "Document ingestion completed successfully.",
                "data": response_payload.model_dump(mode="json"),
            }) + "\n"

        except ValueError as e:
            yield json.dumps({
                "stage": "failed",
                "progress": 0,
                "error": str(e),
            }) + "\n"
        except OSError as e:
            yield json.dumps({
                "stage": "failed",
                "progress": 0,
                "error": f"Storage failure: {e}",
            }) + "\n"
        except Exception as e:
            yield json.dumps({
                "stage": "failed",
                "progress": 0,
                "error": f"Ingestion failure: {e}",
            }) + "\n"


def ingest_document(file: UploadFile, user_id: str) -> UploadResponse:
    """Public convenience function to ingest a document using default IngestionService.

    Args:
        file: Uploaded file object.
        user_id: Authenticated Supabase user ID.

    Returns:
        UploadResponse: Public document metadata upon successful ingestion.
    """
    service = IngestionService()
    return service.ingest_document(file, user_id)
