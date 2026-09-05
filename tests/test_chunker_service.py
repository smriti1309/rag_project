"""Unit tests for Chunker Service."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import Settings, settings
from app.schemas.chunk import ChunkDocument
from app.services.chunker_service import ChunkerService, chunk_document, cosine_similarity


class TestChunkerService(unittest.TestCase):
    """Test suite for Chunker Service."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        self.chunk_dir = self.tmp_path / "chunks"

        # Patch settings.chunk_directory for isolated test environment
        self.patcher = patch.object(settings, "chunk_directory", self.chunk_dir)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_cosine_similarity_utility(self) -> None:
        """Test cosine_similarity helper function calculation."""
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]

        self.assertAlmostEqual(cosine_similarity(v1, v2), 1.0, places=5)
        self.assertAlmostEqual(cosine_similarity(v1, v3), 0.0, places=5)
        self.assertEqual(cosine_similarity([], v1), 0.0)

    def test_semantic_similarity_boundary_topic_shift(self) -> None:
        """Test that controlled semantic similarity boundary creates chunks on topic shift."""
        doc_file = self.tmp_path / "topic_shift_doc.txt"
        doc_content = (
            "This paragraph discusses cardiovascular health and heart diseases.\n\n"
            "This second paragraph continues explaining blood circulation and heart functions.\n\n"
            "This third paragraph shifts topic completely to quantum physics and particle dynamics.\n\n"
            "This fourth paragraph continues explaining subatomic particles and wave functions."
        )
        doc_file.write_text(doc_content, encoding="utf-8")

        # Mock embedding service returning controlled vectors:
        # P1 and P2: Topic A vector [1.0, 0.0, 0.0...]
        # P3 and P4: Topic B vector [0.0, 1.0, 0.0...]
        mock_embedding_service = MagicMock()
        vec_topic_a = [1.0 if i == 0 else 0.0 for i in range(768)]
        vec_topic_b = [1.0 if i == 1 else 0.0 for i in range(768)]

        mock_embedding_service._generate_embeddings.return_value = [
            vec_topic_a,
            vec_topic_a,
            vec_topic_b,
            vec_topic_b,
        ]

        custom_settings = Settings(
            chunk_directory=self.chunk_dir,
            semantic_similarity_threshold=0.75,
            semantic_chunk_min_words=5,
            semantic_chunk_max_words=500,
        )
        service = ChunkerService(
            embedding_service=mock_embedding_service, settings=custom_settings
        )

        result_path = service.chunk_document(doc_file)
        chunk_doc = ChunkDocument.model_validate_json(result_path.read_text(encoding="utf-8"))

        # Exactly 2 chunks should be produced due to topic shift at P3
        self.assertEqual(len(chunk_doc.chunks), 2)
        self.assertIn("cardiovascular health", chunk_doc.chunks[0].text)
        self.assertIn("blood circulation", chunk_doc.chunks[0].text)

        self.assertIn("quantum physics", chunk_doc.chunks[1].text)
        self.assertIn("subatomic particles", chunk_doc.chunks[1].text)

        # Deterministic IDs check
        self.assertEqual(chunk_doc.chunks[0].chunk_id, 1)
        self.assertEqual(chunk_doc.chunks[1].chunk_id, 2)

    def test_priority_hierarchy_max_over_min_and_semantic(self) -> None:
        """Test priority hierarchy: MAX SIZE > SEMANTIC BOUNDARY > MIN SIZE."""
        doc_file = self.tmp_path / "max_priority.txt"
        p1 = " ".join(["word"] * 25)
        p2 = " ".join(["term"] * 25)
        doc_content = f"{p1}\n\n{p2}"
        doc_file.write_text(doc_content, encoding="utf-8")

        mock_embedding_service = MagicMock()
        vec_same = [1.0 if i == 0 else 0.0 for i in range(768)]
        mock_embedding_service._generate_embeddings.return_value = [vec_same, vec_same]

        # max_words = 30, min_words = 50. Even though similarity is 1.0 and min_words is 50,
        # max_words 30 forces chunk split after p1!
        custom_settings = Settings(
            chunk_directory=self.chunk_dir,
            semantic_similarity_threshold=0.75,
            semantic_chunk_min_words=50,
            semantic_chunk_max_words=30,
        )
        service = ChunkerService(
            embedding_service=mock_embedding_service, settings=custom_settings
        )

        result_path = service.chunk_document(doc_file)
        chunk_doc = ChunkDocument.model_validate_json(result_path.read_text(encoding="utf-8"))

        self.assertEqual(len(chunk_doc.chunks), 2)
        self.assertLessEqual(len(chunk_doc.chunks[0].text.split()), 30)
        self.assertLessEqual(len(chunk_doc.chunks[1].text.split()), 30)

    def test_chunk_document_normal(self) -> None:
        """Test successful chunking of a normal multi-paragraph document."""
        doc_file = self.tmp_path / "sample_doc.txt"
        doc_content = (
            "Paragraph one introduces the main topic of discussion.\n\n"
            "Paragraph two provides detailed background information and context.\n\n"
            "Paragraph three concludes the introductory overview."
        )
        doc_file.write_text(doc_content, encoding="utf-8")

        result_path = chunk_document(doc_file, source_file="sample_doc.pdf")

        self.assertEqual(result_path, self.chunk_dir / "sample_doc.json")
        self.assertTrue(result_path.exists())

        raw_json = result_path.read_text(encoding="utf-8")
        chunk_doc = ChunkDocument.model_validate_json(raw_json)

        self.assertEqual(chunk_doc.document_id, "sample_doc")
        self.assertEqual(chunk_doc.source_file, "sample_doc.pdf")
        self.assertGreater(len(chunk_doc.chunks), 0)

        first_chunk = chunk_doc.chunks[0]
        self.assertEqual(first_chunk.chunk_id, 1)
        self.assertIsNone(first_chunk.page)
        self.assertIn("Paragraph one", first_chunk.text)
        self.assertEqual(
            doc_content[first_chunk.start_char : first_chunk.end_char],
            first_chunk.text,
        )

    def test_chunk_document_file_not_found(self) -> None:
        """Test that FileNotFoundError is raised for non-existent files."""
        missing_file = self.tmp_path / "missing.txt"
        with self.assertRaises(FileNotFoundError):
            chunk_document(missing_file)

    def test_chunk_document_empty(self) -> None:
        """Test that ValueError is raised for empty or whitespace files."""
        empty_file = self.tmp_path / "empty.txt"
        empty_file.write_text("   \n\n  ", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            chunk_document(empty_file)
        self.assertIn("empty", str(ctx.exception).lower())

    def test_chunk_document_oversized_paragraph(self) -> None:
        """Test handling of oversized paragraph exceeding max_words limit."""
        doc_file = self.tmp_path / "oversized.txt"
        sentence_1 = " ".join([f"word{i}" for i in range(30)]) + "."
        sentence_2 = " ".join([f"term{i}" for i in range(30)]) + "."
        doc_content = f"{sentence_1} {sentence_2}"
        doc_file.write_text(doc_content, encoding="utf-8")

        custom_settings = Settings(
            chunk_directory=self.chunk_dir,
            semantic_chunk_max_words=25,
            semantic_chunk_min_words=5,
        )
        service = ChunkerService(settings=custom_settings)
        result_path = service.chunk_document(doc_file)

        raw_json = result_path.read_text(encoding="utf-8")
        data = json.loads(raw_json)

        self.assertEqual(data["document_id"], "oversized")
        self.assertGreater(len(data["chunks"]), 1)

    def test_chunk_document_page_tracking(self) -> None:
        """Test that ===== PAGE N ===== markers are correctly parsed into page metadata."""
        doc_file = self.tmp_path / "paged_doc.txt"
        doc_content = (
            "===== PAGE 1 =====\n"
            "This is content on page one.\n\n"
            "===== PAGE 2 =====\n"
            "This is content on page two."
        )
        doc_file.write_text(doc_content, encoding="utf-8")

        custom_settings = Settings(
            chunk_directory=self.chunk_dir,
            semantic_chunk_max_words=10,
            semantic_chunk_min_words=2,
        )
        service = ChunkerService(settings=custom_settings)
        result_path = service.chunk_document(doc_file)
        chunk_doc = ChunkDocument.model_validate_json(result_path.read_text(encoding="utf-8"))

        self.assertEqual(len(chunk_doc.chunks), 2)
        self.assertEqual(chunk_doc.chunks[0].page, 1)
        self.assertEqual(chunk_doc.chunks[1].page, 2)

    def test_chunk_document_invalid_config(self) -> None:
        """Test that ValueError is raised for invalid chunk configuration."""
        bad_settings_1 = Settings(semantic_chunk_max_words=0)
        with self.assertRaises(ValueError):
            ChunkerService(settings=bad_settings_1)

        bad_settings_2 = Settings(semantic_similarity_threshold=1.5)
        with self.assertRaises(ValueError):
            ChunkerService(settings=bad_settings_2)


if __name__ == "__main__":
    unittest.main()
