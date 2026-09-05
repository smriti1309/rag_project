"""Unit tests for Qdrant Service."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import uuid

from qdrant_client import models

from app.core.config import Settings, settings
from app.schemas.embedding import ChunkEmbedding, EmbeddingDocument
from app.services.qdrant_service import QdrantService


class TestQdrantService(unittest.TestCase):
    """Test suite for Qdrant Service."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        self.mock_client = MagicMock()
        self.patcher = patch.object(settings, "qdrant_collection_name", "knowledge_base_v2")
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def _create_sample_embedding_file(
        self, filename: str = "doc123.embeddings.json", num_chunks: int = 3, dimension: int = 768
    ) -> Path:
        """Helper to create a sample EmbeddingDocument JSON file."""
        embeddings = [
            ChunkEmbedding(
                chunk_id=i + 1,
                page=i + 1,
                text=f"Sample text content for chunk {i + 1}",
                embedding=[0.1 * (i + 1)] * dimension,
            )
            for i in range(num_chunks)
        ]
        embedding_doc = EmbeddingDocument(
            document_id="doc123",
            user_id="user123",
            source_file="sample.pdf",
            model="gemini-embedding-2",
            dimension=dimension,
            embeddings=embeddings,
        )

        file_path = self.tmp_path / filename
        file_path.write_text(embedding_doc.model_dump_json(indent=2), encoding="utf-8")
        return file_path

    def test_index_document_success_new_collection(self) -> None:
        """Test successful indexing when target collection does not exist."""
        self.mock_client.collection_exists.return_value = False

        embedding_file = self._create_sample_embedding_file(num_chunks=2, dimension=768)

        service = QdrantService(client=self.mock_client)
        service.index_document(embedding_file)

        # Verify collection creation check and call
        self.mock_client.collection_exists.assert_called_once_with(collection_name="knowledge_base_v2")
        self.mock_client.create_collection.assert_called_once()
        create_args = self.mock_client.create_collection.call_args[1]
        self.assertEqual(create_args["collection_name"], "knowledge_base_v2")
        self.assertEqual(create_args["vectors_config"].size, 768)
        self.assertEqual(create_args["vectors_config"].distance, models.Distance.COSINE)

        # Verify upsert call
        self.mock_client.upsert.assert_called_once()
        upsert_kwargs = self.mock_client.upsert.call_args[1]
        self.assertEqual(upsert_kwargs["collection_name"], "knowledge_base_v2")
        points = upsert_kwargs["points"]
        self.assertEqual(len(points), 2)

        # Verify point IDs and payload structure
        expected_point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "doc123_1"))
        self.assertEqual(points[0].id, expected_point_id)
        self.assertEqual(points[0].payload["user_id"], "user123")
        self.assertEqual(points[0].payload["document_id"], "doc123")
        self.assertEqual(points[0].payload["chunk_id"], 1)
        self.assertEqual(points[0].payload["page"], 1)
        self.assertEqual(points[0].payload["text"], "Sample text content for chunk 1")
        self.assertEqual(points[0].payload["source_file"], "sample.pdf")
        self.assertEqual(points[0].payload["model"], "gemini-embedding-2")


    def test_index_document_existing_collection_valid(self) -> None:
        """Test successful indexing when collection exists and parameters match."""
        self.mock_client.collection_exists.return_value = True

        mock_info = MagicMock()
        mock_info.config.params.vectors = models.VectorParams(
            size=768, distance=models.Distance.COSINE
        )
        self.mock_client.get_collection.return_value = mock_info

        embedding_file = self._create_sample_embedding_file(dimension=768)

        service = QdrantService(client=self.mock_client)
        service.index_document(embedding_file)

        # Collection creation should not be called
        self.mock_client.create_collection.assert_not_called()
        self.mock_client.get_collection.assert_called_once_with(collection_name="knowledge_base_v2")
        self.mock_client.upsert.assert_called_once()

    def test_index_document_existing_collection_dimension_mismatch(self) -> None:
        """Test ValueError raised when existing collection dimension does not match document."""
        self.mock_client.collection_exists.return_value = True

        mock_info = MagicMock()
        mock_info.config.params.vectors = models.VectorParams(
            size=128, distance=models.Distance.COSINE
        )
        self.mock_client.get_collection.return_value = mock_info

        embedding_file = self._create_sample_embedding_file(dimension=768)

        service = QdrantService(client=self.mock_client)
        with self.assertRaises(ValueError) as ctx:
            service.index_document(embedding_file)
        self.assertIn("vector dimension (128) does not match", str(ctx.exception))

    def test_index_document_existing_collection_distance_mismatch(self) -> None:
        """Test ValueError raised when existing collection distance metric is not Cosine."""
        self.mock_client.collection_exists.return_value = True

        mock_info = MagicMock()
        mock_info.config.params.vectors = models.VectorParams(
            size=768, distance=models.Distance.DOT
        )
        self.mock_client.get_collection.return_value = mock_info

        embedding_file = self._create_sample_embedding_file(dimension=768)

        service = QdrantService(client=self.mock_client)
        with self.assertRaises(ValueError) as ctx:
            service.index_document(embedding_file)
        self.assertIn("distance metric", str(ctx.exception).lower())

    def test_index_document_missing_file(self) -> None:
        """Test FileNotFoundError raised when embedding JSON does not exist."""
        missing_file = self.tmp_path / "missing.json"
        service = QdrantService(client=self.mock_client)

        with self.assertRaises(FileNotFoundError):
            service.index_document(missing_file)

    def test_index_document_invalid_json(self) -> None:
        """Test ValueError raised when file contains malformed JSON."""
        bad_json = self.tmp_path / "bad.json"
        bad_json.write_text("NOT A VALID JSON", encoding="utf-8")

        service = QdrantService(client=self.mock_client)
        with self.assertRaises(ValueError) as ctx:
            service.index_document(bad_json)
        self.assertIn("Invalid JSON format", str(ctx.exception))

    def test_index_document_empty_embeddings(self) -> None:
        """Test ValueError raised when embedding document contains empty embeddings list."""
        doc = EmbeddingDocument(
            document_id="empty_doc", model="gemini-embedding-2", dimension=768, embeddings=[]
        )
        empty_file = self.tmp_path / "empty_doc.json"
        empty_file.write_text(doc.model_dump_json(), encoding="utf-8")

        service = QdrantService(client=self.mock_client)
        with self.assertRaises(ValueError) as ctx:
            service.index_document(empty_file)
        self.assertIn("contains no embeddings", str(ctx.exception).lower())

    def test_index_document_configurable_batching(self) -> None:
        """Test points are upserted in multiple configurable batches."""
        self.mock_client.collection_exists.return_value = False

        embedding_file = self._create_sample_embedding_file(num_chunks=5)

        custom_settings = Settings(qdrant_batch_size=2)
        service = QdrantService(client=self.mock_client, settings=custom_settings)
        service.index_document(embedding_file)

        # 5 points with batch_size=2 -> 3 upsert calls (2 + 2 + 1)
        self.assertEqual(self.mock_client.upsert.call_count, 3)

    @patch("app.services.qdrant_service.QdrantClient")
    def test_qdrant_client_connection_failure(self, mock_client_cls: MagicMock) -> None:
        """Test RuntimeError raised when QdrantClient initialization fails."""
        mock_client_cls.side_effect = Exception("Connection refused")

        with self.assertRaises(RuntimeError) as ctx:
            QdrantService()
        self.assertIn("Failed to connect to Qdrant server", str(ctx.exception))

    def test_index_document_upsert_failure(self) -> None:
        """Test RuntimeError raised when Qdrant upsert call fails."""
        self.mock_client.collection_exists.return_value = False
        self.mock_client.upsert.side_effect = Exception("Qdrant server timeout")

        embedding_file = self._create_sample_embedding_file()

        service = QdrantService(client=self.mock_client)
        with self.assertRaises(RuntimeError) as ctx:
            service.index_document(embedding_file)
        self.assertIn("Failed to upsert batch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
