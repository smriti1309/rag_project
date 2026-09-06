"""Unit tests for DocumentRepository chunk persistence and watermark operations."""

import unittest
from app.services.document_repository import DocumentRepository


class TestDocumentChunksRepository(unittest.TestCase):
    """Test suite for DocumentRepository document_chunks operations."""

    def setUp(self) -> None:
        self.repo = DocumentRepository()
        self.user_1 = "user-uuid-1111"
        self.user_2 = "user-uuid-2222"
        self.doc_1 = "doc-uuid-aaaa"
        self.doc_2 = "doc-uuid-bbbb"
        self.doc_failed = "doc-uuid-failed"

        # Register document metadata in repo memory store
        self.repo.insert_document(
            {
                "id": self.doc_1,
                "user_id": self.user_1,
                "filename": "test1.pdf",
                "status": "indexed",
                "updated_at": "2026-09-06T10:00:00+00:00",
            }
        )
        self.repo.insert_document(
            {
                "id": self.doc_2,
                "user_id": self.user_1,
                "filename": "test2.pdf",
                "status": "indexed",
                "updated_at": "2026-09-06T12:00:00+00:00",
            }
        )
        self.repo.insert_document(
            {
                "id": self.doc_failed,
                "user_id": self.user_1,
                "filename": "failed_file.pdf",
                "status": "failed",
                "updated_at": "2026-09-06T13:00:00+00:00",
            }
        )

    def test_insert_and_get_user_chunks(self) -> None:
        """Test inserting document chunks and fetching them by user_id."""
        chunks = [
            {
                "document_id": self.doc_1,
                "user_id": self.user_1,
                "chunk_id": 1,
                "page": 1,
                "source_file": "test1.pdf",
                "text": "Hello world from chunk 1",
            },
            {
                "document_id": self.doc_1,
                "user_id": self.user_1,
                "chunk_id": 2,
                "page": 1,
                "source_file": "test1.pdf",
                "text": "FastAPI and Supabase integration",
            },
        ]
        self.assertTrue(self.repo.insert_document_chunks(chunks))

        fetched = self.repo.get_user_chunks(self.user_1)
        self.assertEqual(len(fetched), 2)
        self.assertEqual(fetched[0]["text"], "Hello world from chunk 1")

    def test_reindexing_prevents_duplicate_chunks(self) -> None:
        """Test that re-indexing the same document_id and chunk_id updates without duplicating."""
        initial_chunks = [
            {
                "document_id": self.doc_1,
                "user_id": self.user_1,
                "chunk_id": 1,
                "page": 1,
                "source_file": "test1.pdf",
                "text": "Initial text v1",
            }
        ]
        self.repo.insert_document_chunks(initial_chunks)

        # Re-index same chunk with updated text
        updated_chunks = [
            {
                "document_id": self.doc_1,
                "user_id": self.user_1,
                "chunk_id": 1,
                "page": 1,
                "source_file": "test1.pdf",
                "text": "Updated text v2",
            }
        ]
        self.repo.insert_document_chunks(updated_chunks)

        fetched = self.repo.get_user_chunks(self.user_1)
        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0]["text"], "Updated text v2")

    def test_failed_document_chunks_excluded(self) -> None:
        """Test that chunks belonging to a document with status='failed' are excluded from get_user_chunks."""
        self.repo.insert_document_chunks(
            [
                {
                    "document_id": self.doc_1,
                    "user_id": self.user_1,
                    "chunk_id": 1,
                    "source_file": "test1.pdf",
                    "text": "Valid indexed text",
                },
                {
                    "document_id": self.doc_failed,
                    "user_id": self.user_1,
                    "chunk_id": 1,
                    "source_file": "failed_file.pdf",
                    "text": "Failed document chunk text",
                },
            ]
        )

        fetched = self.repo.get_user_chunks(self.user_1)
        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0]["document_id"], self.doc_1)
        self.assertEqual(fetched[0]["text"], "Valid indexed text")

    def test_user_isolation(self) -> None:
        """Test that get_user_chunks strictly filters by user_id."""
        self.repo.insert_document(
            {
                "id": "doc-uuid-cccc",
                "user_id": self.user_2,
                "filename": "test3.pdf",
                "status": "indexed",
                "updated_at": "2026-09-06T10:00:00+00:00",
            }
        )
        self.repo.insert_document_chunks(
            [
                {
                    "document_id": self.doc_1,
                    "user_id": self.user_1,
                    "chunk_id": 1,
                    "source_file": "test1.pdf",
                    "text": "User 1 chunk text",
                },
                {
                    "document_id": "doc-uuid-cccc",
                    "user_id": self.user_2,
                    "chunk_id": 1,
                    "source_file": "test3.pdf",
                    "text": "User 2 chunk text",
                },
            ]
        )

        user_1_chunks = self.repo.get_user_chunks(self.user_1)
        self.assertEqual(len(user_1_chunks), 1)
        self.assertEqual(user_1_chunks[0]["text"], "User 1 chunk text")

        user_2_chunks = self.repo.get_user_chunks(self.user_2)
        self.assertEqual(len(user_2_chunks), 1)
        self.assertEqual(user_2_chunks[0]["text"], "User 2 chunk text")

    def test_get_user_watermark(self) -> None:
        """Test fetching the latest watermark timestamp and count."""
        latest_ts, count = self.repo.get_user_watermark(self.user_1)
        self.assertEqual(count, 2)
        self.assertEqual(latest_ts, "2026-09-06T12:00:00+00:00")

    def test_delete_document_clears_chunks(self) -> None:
        """Test deleting a document removes its chunks in memory fallback."""
        self.repo.insert_document_chunks(
            [
                {
                    "document_id": self.doc_1,
                    "user_id": self.user_1,
                    "chunk_id": 1,
                    "source_file": "test1.pdf",
                    "text": "Doc 1 text",
                },
                {
                    "document_id": self.doc_2,
                    "user_id": self.user_1,
                    "chunk_id": 1,
                    "source_file": "test2.pdf",
                    "text": "Doc 2 text",
                },
            ]
        )

        self.assertTrue(self.repo.delete_document(self.user_1, self.doc_1))

        chunks_after = self.repo.get_user_chunks(self.user_1)
        self.assertEqual(len(chunks_after), 1)
        self.assertEqual(chunks_after[0]["document_id"], self.doc_2)


if __name__ == "__main__":
    unittest.main()
