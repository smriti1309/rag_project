"""Unit tests for BM25Service persistent lexical retrieval."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from app.core.config import Settings
from app.services.bm25_service import BM25Service


class TestBM25Service(unittest.TestCase):
    """Test suite for BM25Service indexing, searching, persistence, and isolation."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.chunk_dir = self.temp_dir / "chunks"
        self.bm25_dir = self.temp_dir / "bm25"
        self.chunk_dir.mkdir(parents=True, exist_ok=True)
        self.bm25_dir.mkdir(parents=True, exist_ok=True)

        self.settings = Settings(
            chunk_directory=self.chunk_dir,
            bm25_directory=self.bm25_dir,
        )
        self.service = BM25Service(settings=self.settings)

        self.user_a = "user-alice-111"
        self.user_b = "user-bob-222"
        self.doc_1 = "doc-alpha-123"
        self.doc_2 = "doc-beta-456"
        self.doc_b_1 = "doc-bob-789"

        # Create mock chunk document 1 for User A
        self.chunk_doc_1 = {
            "document_id": self.doc_1,
            "user_id": self.user_a,
            "source_file": "python_guide.pdf",
            "chunks": [
                {
                    "chunk_id": 1,
                    "page": 1,
                    "start_char": 0,
                    "end_char": 69,
                    "text": "Python is a high-level programming language with dynamic semantics.",
                },
                {
                    "chunk_id": 2,
                    "page": 2,
                    "start_char": 70,
                    "end_char": 133,
                    "text": "FastAPI is a modern web framework for building APIs with Python.",
                },
            ],
        }
        self.chunk_file_1 = self.chunk_dir / f"{self.doc_1}.json"
        self.chunk_file_1.write_text(json.dumps(self.chunk_doc_1), encoding="utf-8")

        # Create mock chunk document 2 for User A
        self.chunk_doc_2 = {
            "document_id": self.doc_2,
            "user_id": self.user_a,
            "source_file": "database_guide.pdf",
            "chunks": [
                {
                    "chunk_id": 1,
                    "page": 1,
                    "start_char": 0,
                    "end_char": 65,
                    "text": "PostgreSQL is a powerful open source relational database system.",
                },
            ],
        }
        self.chunk_file_2 = self.chunk_dir / f"{self.doc_2}.json"
        self.chunk_file_2.write_text(json.dumps(self.chunk_doc_2), encoding="utf-8")

        # Create mock chunk document for User B (User isolation test)
        self.chunk_doc_b = {
            "document_id": self.doc_b_1,
            "user_id": self.user_b,
            "source_file": "secret_bob.pdf",
            "chunks": [
                {
                    "chunk_id": 1,
                    "page": 1,
                    "start_char": 0,
                    "end_char": 55,
                    "text": "Python and confidential data belonging strictly to Bob.",
                },
            ],
        }
        self.chunk_file_b = self.chunk_dir / f"{self.doc_b_1}.json"
        self.chunk_file_b.write_text(json.dumps(self.chunk_doc_b), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_index_document_and_retrieve_relevant_chunk(self) -> None:
        """Test indexing a document and retrieving a relevant chunk by keyword."""
        artifact_path = self.service.index_document(self.chunk_file_1)
        self.assertTrue(artifact_path.exists())

        results = self.service.search_chunks(query="FastAPI", user_id=self.user_a)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["chunk_id"], 2)
        self.assertEqual(results[0]["source_file"], "python_guide.pdf")
        self.assertIn("FastAPI", results[0]["text"])
        self.assertGreater(results[0]["bm25_score"], 0.0)

    def test_exact_keyword_matching(self) -> None:
        """Test exact keyword search matching."""
        self.service.index_document(self.chunk_file_1)
        self.service.index_document(self.chunk_file_2)

        results = self.service.search_chunks(query="PostgreSQL", user_id=self.user_a)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["document_id"], self.doc_2)
        self.assertIn("PostgreSQL", results[0]["text"])

    def test_top_k_respect(self) -> None:
        """Test top_k limit parameter is respected."""
        self.service.index_document(self.chunk_file_1)
        self.service.index_document(self.chunk_file_2)

        results = self.service.search_chunks(query="Python", user_id=self.user_a, top_k=1)
        self.assertEqual(len(results), 1)

    def test_user_id_isolation_fail_safe(self) -> None:
        """Test strict fail-safe user_id isolation (never returns chunks for another user)."""
        self.service.index_document(self.chunk_file_1)
        self.service.index_document(self.chunk_file_b)

        # Alice searches for Python -> must NEVER receive Bob's chunk
        alice_results = self.service.search_chunks(query="Python", user_id=self.user_a)
        for chunk in alice_results:
            self.assertNotEqual(chunk["document_id"], self.doc_b_1)
            self.assertNotIn("Bob", chunk["text"])

        # Bob searches for Python -> receives Bob's chunk
        bob_results = self.service.search_chunks(query="Python", user_id=self.user_b)
        self.assertEqual(len(bob_results), 1)
        self.assertEqual(bob_results[0]["document_id"], self.doc_b_1)

    def test_document_id_filtering(self) -> None:
        """Test filtering by specific document_id."""
        self.service.index_document(self.chunk_file_1)
        self.service.index_document(self.chunk_file_2)

        results = self.service.search_chunks(
            query="Python", user_id=self.user_a, document_id=self.doc_1
        )
        self.assertEqual(len(results), 2)
        for chunk in results:
            self.assertEqual(chunk["document_id"], self.doc_1)

    def test_persistence_and_auto_recovery(self) -> None:
        """Test persisted BM25 data works across service instances and auto-rebuilds if missing."""
        self.service.index_document(self.chunk_file_1)

        # Create a new service instance sharing the same directories
        new_service = BM25Service(settings=self.settings)

        # Delete the .bm25.json file to test auto-recovery from chunk JSON
        bm25_artifact = self.bm25_dir / f"{self.doc_1}.bm25.json"
        if bm25_artifact.exists():
            bm25_artifact.unlink()

        # Search using new service -> should auto-rebuild from chunk_file_1 and return results
        results = new_service.search_chunks(query="programming", user_id=self.user_a)
        self.assertEqual(len(results), 1)
        self.assertTrue(bm25_artifact.exists())

    def test_empty_and_no_match_queries(self) -> None:
        """Test handling of empty queries and queries with zero matches."""
        self.service.index_document(self.chunk_file_1)

        self.assertEqual(self.service.search_chunks(query="", user_id=self.user_a), [])
        self.assertEqual(self.service.search_chunks(query="   ", user_id=self.user_a), [])
        self.assertEqual(
            self.service.search_chunks(query="nonexistentxyzkeyword", user_id=self.user_a), []
        )


if __name__ == "__main__":
    unittest.main()
