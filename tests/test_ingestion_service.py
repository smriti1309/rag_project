from datetime import datetime, timezone
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from fastapi import UploadFile

from app.schemas.upload import UploadResponse
from app.services.ingestion_service import IngestionService, ingest_document


class TestIngestionService(unittest.TestCase):
    """Unit test suite for IngestionService orchestration pipeline."""

    def setUp(self):
        self.mock_file = MagicMock(spec=UploadFile)
        self.mock_file.filename = "sample.pdf"
        self.mock_file.file = io.BytesIO(b"%PDF-1.4 Mock PDF content")

        self.user_id = "user-test-12345"
        self.sample_txt_path = Path("temp/doc-123/sample.txt")
        self.sample_chunk_path = Path("data/chunks/doc-123.json")
        self.sample_embedding_path = Path("data/embeddings/doc-123.embeddings.json")

    @patch("app.services.ingestion_service.shutil.rmtree")
    @patch("app.services.ingestion_service.parse_pdf")
    @patch("app.services.ingestion_service.chunk_document")
    @patch("app.services.ingestion_service.embed_document")
    @patch("builtins.open")
    def test_ingest_pdf_document_success(
        self,
        mock_open,
        mock_embed,
        mock_chunk,
        mock_parse,
        mock_rmtree,
    ):
        """Test full successful PDF document ingestion pipeline execution."""
        mock_parse.return_value = self.sample_txt_path
        mock_chunk.return_value = self.sample_chunk_path
        mock_embed.return_value = self.sample_embedding_path

        mock_file_handle = MagicMock()
        mock_file_handle.__enter__.return_value = io.StringIO(json.dumps({"chunks": [{"id": 1}, {"id": 2}]}))
        mock_open.return_value = mock_file_handle

        mock_qdrant = MagicMock()
        mock_bm25 = MagicMock()
        mock_r2 = MagicMock()
        mock_r2.generate_object_key.return_value = f"{self.user_id}/doc-123/sample.pdf"
        mock_repo = MagicMock()

        service = IngestionService(
            qdrant_service=mock_qdrant,
            bm25_service=mock_bm25,
            r2_storage_service=mock_r2,
            document_repository=mock_repo,
        )

        result = service.ingest_document(self.mock_file, self.user_id)

        self.assertIsInstance(result, UploadResponse)
        self.assertEqual(result.original_filename, "sample.pdf")
        self.assertEqual(result.file_type, "pdf")
        self.assertEqual(result.status, "indexed")
        self.assertEqual(result.chunk_count, 2)
        self.assertEqual(result.user_id, self.user_id)

        mock_r2.upload_file.assert_called_once()
        mock_repo.insert_document.assert_called_once()
        mock_parse.assert_called_once()
        mock_chunk.assert_called_once()
        mock_embed.assert_called_once()
        embed_kwargs = mock_embed.call_args[1]
        self.assertEqual(embed_kwargs["user_id"], self.user_id)
        self.assertEqual(embed_kwargs["source_file"], "sample.pdf")
        mock_qdrant.index_document.assert_called_once_with(self.sample_embedding_path)
        mock_repo.update_document_status.assert_called_once()

    @patch("app.services.ingestion_service.shutil.rmtree")
    @patch("app.services.ingestion_service.parse_docx")
    @patch("app.services.ingestion_service.chunk_document")
    @patch("app.services.ingestion_service.embed_document")
    @patch("builtins.open")
    def test_ingest_docx_document_success(
        self,
        mock_open,
        mock_embed,
        mock_chunk,
        mock_parse_docx,
        mock_rmtree,
    ):
        """Test full successful DOCX document ingestion pipeline execution."""
        mock_docx_file = MagicMock(spec=UploadFile)
        mock_docx_file.filename = "sample.docx"
        mock_docx_file.file = io.BytesIO(b"Mock DOCX binary content")

        mock_parse_docx.return_value = self.sample_txt_path
        mock_chunk.return_value = self.sample_chunk_path
        mock_embed.return_value = self.sample_embedding_path

        mock_file_handle = MagicMock()
        mock_file_handle.__enter__.return_value = io.StringIO(json.dumps({"chunks": [{"id": 1}, {"id": 2}, {"id": 3}]}))
        mock_open.return_value = mock_file_handle

        mock_qdrant = MagicMock()
        mock_bm25 = MagicMock()
        mock_r2 = MagicMock()
        mock_r2.generate_object_key.return_value = f"{self.user_id}/doc-123/sample.docx"
        mock_repo = MagicMock()

        service = IngestionService(
            qdrant_service=mock_qdrant,
            bm25_service=mock_bm25,
            r2_storage_service=mock_r2,
            document_repository=mock_repo,
        )

        result = service.ingest_document(mock_docx_file, self.user_id)

        self.assertIsInstance(result, UploadResponse)
        self.assertEqual(result.original_filename, "sample.docx")
        self.assertEqual(result.file_type, "docx")
        self.assertEqual(result.status, "indexed")
        self.assertEqual(result.chunk_count, 3)
        self.assertEqual(result.user_id, self.user_id)

        mock_r2.upload_file.assert_called_once()
        mock_repo.insert_document.assert_called_once()
        mock_parse_docx.assert_called_once()
        mock_chunk.assert_called_once()
        mock_embed.assert_called_once()
        embed_kwargs = mock_embed.call_args[1]
        self.assertEqual(embed_kwargs["user_id"], self.user_id)
        self.assertEqual(embed_kwargs["source_file"], "sample.docx")
        mock_qdrant.index_document.assert_called_once_with(self.sample_embedding_path)
        mock_repo.update_document_status.assert_called_once()

    def test_ingest_document_invalid_extension(self):
        """Test that invalid file extensions raise ValueError."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "invalid.exe"

        service = IngestionService()
        with self.assertRaises(ValueError):
            service.ingest_document(mock_file, self.user_id)

    def test_ingest_document_empty_file(self):
        """Test that uploading empty file content raises ValueError."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "empty.pdf"
        mock_file.file = io.BytesIO(b"")

        service = IngestionService()
        with self.assertRaises(ValueError):
            service.ingest_document(mock_file, self.user_id)

    def test_ingest_document_exceeds_max_file_size(self):
        """Test that uploading file over size limit raises ValueError."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "large.pdf"
        mock_file.file = io.BytesIO(b"x" * (51 * 1024 * 1024))

        service = IngestionService()
        with self.assertRaises(ValueError):
            service.ingest_document(mock_file, self.user_id)

    @patch("app.services.ingestion_service.IngestionService.ingest_document")
    def test_public_ingest_document_helper(self, mock_ingest_method):
        """Test public convenience function ingest_document."""
        mock_response = UploadResponse(
            document_id="doc-123",
            original_filename="sample.pdf",
            stored_filename="sample.pdf",
            size=100,
            uploaded_at=datetime.now(timezone.utc),
            status="indexed",
            user_id=self.user_id,
        )
        mock_ingest_method.return_value = mock_response

        res = ingest_document(self.mock_file, self.user_id)
        self.assertEqual(res, mock_response)

    @patch("app.services.ingestion_service.shutil.rmtree")
    @patch("app.services.ingestion_service.parse_pdf")
    @patch("app.services.ingestion_service.chunk_document")
    @patch("app.services.ingestion_service.embed_document")
    @patch("builtins.open")
    def test_ingest_pdf_document_stream_success(
        self,
        mock_open,
        mock_embed,
        mock_chunk,
        mock_parse,
        mock_rmtree,
    ):
        """Test full successful PDF document ingestion streaming pipeline execution."""
        mock_parse.return_value = self.sample_txt_path
        mock_chunk.return_value = self.sample_chunk_path
        mock_embed.return_value = self.sample_embedding_path

        mock_file_handle = MagicMock()
        mock_file_handle.__enter__.return_value = io.StringIO(json.dumps({"chunks": [{"id": 1}, {"id": 2}]}))
        mock_open.return_value = mock_file_handle

        mock_qdrant = MagicMock()
        mock_bm25 = MagicMock()
        mock_r2 = MagicMock()
        mock_r2.generate_object_key.return_value = f"{self.user_id}/doc-123/sample.pdf"
        mock_repo = MagicMock()

        service = IngestionService(
            qdrant_service=mock_qdrant,
            bm25_service=mock_bm25,
            r2_storage_service=mock_r2,
            document_repository=mock_repo,
        )

        events = [json.loads(line) for line in service.ingest_document_stream(self.mock_file, self.user_id)]
        stages = [e["stage"] for e in events]
        progresses = [e["progress"] for e in events]

        self.assertEqual(stages, ["uploading", "parsing", "chunking", "embedding", "indexing", "completed"])
        self.assertEqual(progresses, [20, 40, 60, 80, 95, 100])
        self.assertEqual(events[-1]["data"]["original_filename"], "sample.pdf")
        self.assertEqual(events[-1]["data"]["chunk_count"], 2)

    def test_ingest_document_stream_invalid_extension(self):
        """Test that invalid file extension yields failed stage event in stream."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "invalid.exe"

        service = IngestionService()
        events = [json.loads(line) for line in service.ingest_document_stream(mock_file, self.user_id)]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["stage"], "failed")
        self.assertEqual(events[0]["progress"], 0)
        self.assertIn("not allowed", events[0]["error"])


if __name__ == "__main__":
    unittest.main()
