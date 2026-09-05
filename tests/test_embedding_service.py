"""Unit tests for Embedding Service."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import Settings, settings
from app.schemas.chunk import Chunk, ChunkDocument
from app.schemas.embedding import EmbeddingDocument
from app.services.embedding_service import EmbeddingService, embed_document


class TestEmbeddingService(unittest.TestCase):
    """Test suite for Embedding Service."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        self.embedding_dir = self.tmp_path / "embeddings"

        # Patch settings.embedding_directory for isolated test environment
        self.patcher = patch.object(settings, "embedding_directory", self.embedding_dir)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def _create_sample_chunk_json(
        self, filename: str, document_id: str = "doc123", num_chunks: int = 2
    ) -> Path:
        """Helper to create a test chunk JSON file."""
        chunks = [
            Chunk(
                chunk_id=i + 1,
                page=i + 1,
                start_char=i * 50,
                end_char=(i + 1) * 50,
                text=f"This is test chunk text number {i + 1}.",
            )
            for i in range(num_chunks)
        ]
        chunk_doc = ChunkDocument(
            document_id=document_id,
            source_file="sample.pdf",
            chunks=chunks,
        )

        file_path = self.tmp_path / filename
        file_path.write_text(chunk_doc.model_dump_json(indent=2), encoding="utf-8")
        return file_path

    @patch("app.services.embedding_service.genai.Client")
    def test_embed_document_success(self, mock_client_cls: MagicMock) -> None:
        """Test successful embedding generation and file output creation."""
        mock_client = MagicMock()
        emb1 = MagicMock()
        emb1.values = [0.1] * 768
        emb2 = MagicMock()
        emb2.values = [0.2] * 768
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[emb1, emb2])
        mock_client_cls.return_value = mock_client

        chunk_file = self._create_sample_chunk_json("doc123.json", "doc123", 2)

        test_settings = Settings(gemini_api_key="test-key", embedding_directory=self.embedding_dir)
        service = EmbeddingService(settings=test_settings)
        result_path = service.embed_document(chunk_file)

        self.assertEqual(result_path, self.embedding_dir / "doc123.embeddings.json")
        self.assertTrue(result_path.exists())

        raw_json = result_path.read_text(encoding="utf-8")
        data = json.loads(raw_json)

        self.assertEqual(data["document_id"], "doc123")
        self.assertEqual(data["source_file"], "sample.pdf")
        self.assertEqual(data["model"], "gemini-embedding-2")
        self.assertEqual(data["dimension"], 768)
        self.assertEqual(len(data["embeddings"]), 2)

        first_emb = data["embeddings"][0]
        self.assertEqual(first_emb["chunk_id"], 1)
        self.assertEqual(first_emb["page"], 1)
        self.assertEqual(first_emb["embedding"], [0.1] * 768)

        # Verify chunk text is stored in embedding JSON for RAG retrieval
        self.assertEqual(first_emb["text"], "This is test chunk text number 1.")

        # Validate with Pydantic model
        emb_doc = EmbeddingDocument.model_validate_json(raw_json)
        self.assertEqual(emb_doc.document_id, "doc123")
        self.assertEqual(emb_doc.source_file, "sample.pdf")
        self.assertEqual(emb_doc.embeddings[0].page, 1)
        self.assertEqual(emb_doc.dimension, 768)

    @patch("app.services.embedding_service.genai.Client")
    def test_embed_document_missing_file(self, mock_client_cls: MagicMock) -> None:
        """Test that FileNotFoundError is raised when input file does not exist."""
        mock_client_cls.return_value = MagicMock()
        test_settings = Settings(gemini_api_key="test-key", embedding_directory=self.embedding_dir)
        service = EmbeddingService(settings=test_settings)

        missing_file = self.tmp_path / "non_existent.json"
        with self.assertRaises(FileNotFoundError):
            service.embed_document(missing_file)

    @patch("app.services.embedding_service.genai.Client")
    def test_embed_document_invalid_json(self, mock_client_cls: MagicMock) -> None:
        """Test that ValueError is raised for malformed JSON file."""
        mock_client_cls.return_value = MagicMock()
        test_settings = Settings(gemini_api_key="test-key", embedding_directory=self.embedding_dir)
        service = EmbeddingService(settings=test_settings)

        bad_json_file = self.tmp_path / "bad.json"
        bad_json_file.write_text("NOT A VALID JSON {{{", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            service.embed_document(bad_json_file)
        self.assertIn("Invalid JSON format", str(ctx.exception))

    @patch("app.services.embedding_service.genai.Client")
    def test_embed_document_empty_chunks(self, mock_client_cls: MagicMock) -> None:
        """Test that ValueError is raised when chunk document has no chunks."""
        mock_client_cls.return_value = MagicMock()
        test_settings = Settings(gemini_api_key="test-key", embedding_directory=self.embedding_dir)
        service = EmbeddingService(settings=test_settings)

        empty_chunk_doc = ChunkDocument(document_id="empty_doc", chunks=[])
        empty_file = self.tmp_path / "empty_chunks.json"
        empty_file.write_text(empty_chunk_doc.model_dump_json(), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            service.embed_document(empty_file)
        self.assertIn("no chunks", str(ctx.exception).lower())

    def test_embed_document_invalid_config(self) -> None:
        """Test that ValueError is raised for invalid settings parameters."""
        bad_settings = Settings(gemini_api_key="test-key", embedding_batch_size=0)
        with self.assertRaises(ValueError) as ctx:
            EmbeddingService(settings=bad_settings)
        self.assertIn("embedding_batch_size", str(ctx.exception))

    @patch("app.services.embedding_service.genai.Client")
    def test_embed_document_batch_encoding_behavior(
        self, mock_client_cls: MagicMock
    ) -> None:
        """Test parameters passed to genai embed_content call."""
        mock_client = MagicMock()
        emb1 = MagicMock()
        emb1.values = [0.1] * 768
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[emb1])
        mock_client_cls.return_value = mock_client

        chunk_file = self._create_sample_chunk_json("single.json", "single", 1)

        custom_settings = Settings(
            gemini_api_key="test-key",
            embedding_directory=self.embedding_dir,
            embedding_batch_size=16,
        )
        service = EmbeddingService(settings=custom_settings)
        service.embed_document(chunk_file)

        mock_client.models.embed_content.assert_called_once()
        call_kwargs = mock_client.models.embed_content.call_args[1]
        self.assertEqual(call_kwargs["model"], "gemini-embedding-2")
        self.assertEqual(call_kwargs["contents"], "This is test chunk text number 1.")
        self.assertEqual(call_kwargs["config"].output_dimensionality, 768)
        self.assertEqual(call_kwargs["config"].task_type, "RETRIEVAL_DOCUMENT")

    @patch("app.services.embedding_service.genai.Client")
    def test_embed_document_mismatched_embedding_count(
        self, mock_client_cls: MagicMock
    ) -> None:
        """Test ValueError is raised if model returns mismatched count of embeddings."""
        mock_client_cls.return_value = MagicMock()
        chunk_file = self._create_sample_chunk_json("mismatch.json", "mismatch", 2)

        test_settings = Settings(gemini_api_key="test-key", embedding_directory=self.embedding_dir)
        service = EmbeddingService(settings=test_settings)
        chunk_doc = service._load_chunk_document(chunk_file)

        with self.assertRaises(ValueError) as ctx:
            service._create_embedding_document(chunk_doc, [[0.1] * 768])
        self.assertIn("Embedding count does not match chunk count", str(ctx.exception))

    @patch("app.services.embedding_service.genai.Client")
    def test_embed_document_model_loading_failure(
        self, mock_client_cls: MagicMock
    ) -> None:
        """Test ValueError is raised when GenAI Client initialization fails."""
        mock_client_cls.side_effect = Exception("API Key error")

        test_settings = Settings(gemini_api_key="test-key", embedding_directory=self.embedding_dir)
        with self.assertRaises(ValueError) as ctx:
            EmbeddingService(settings=test_settings)
        self.assertIn("Failed to initialize Google GenAI Client", str(ctx.exception))

    @patch("app.services.embedding_service.genai.Client")
    def test_embed_query_success(self, mock_client_cls: MagicMock) -> None:
        """Test successful query embedding generation."""
        mock_client = MagicMock()
        emb = MagicMock()
        emb.values = [0.05] * 768
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[emb])
        mock_client_cls.return_value = mock_client

        test_settings = Settings(gemini_api_key="test-key", embedding_directory=self.embedding_dir)
        service = EmbeddingService(settings=test_settings)
        query_vector = service.embed_query("What is AI?")

        self.assertEqual(len(query_vector), 768)
        self.assertEqual(query_vector[0], 0.05)
        call_kwargs = mock_client.models.embed_content.call_args[1]
        self.assertEqual(call_kwargs["model"], "gemini-embedding-2")
        self.assertEqual(call_kwargs["contents"], "What is AI?")
        self.assertEqual(call_kwargs["config"].output_dimensionality, 768)
        self.assertEqual(call_kwargs["config"].task_type, "RETRIEVAL_QUERY")


if __name__ == "__main__":
    unittest.main()

