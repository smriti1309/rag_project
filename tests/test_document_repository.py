import unittest
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.services.document_repository import DocumentRepository


class TestDocumentRepository(unittest.TestCase):
    """Unit test suite for DocumentRepository."""

    def test_in_memory_fallback_crud_operations(self):
        """Test document metadata CRUD operations when Supabase URL/Key are missing (in-memory store)."""
        settings = Settings(supabase_url=None)
        repo = DocumentRepository(settings=settings)
        self.assertIsNone(repo.client)

        doc_data = {
            "id": "doc-001",
            "user_id": "user-abc",
            "filename": "document1.pdf",
            "file_size": 2048,
            "status": "processing",
        }

        # 1. Insert
        inserted = repo.insert_document(doc_data)
        self.assertEqual(inserted["id"], "doc-001")

        # 2. Get document
        retrieved = repo.get_document("user-abc", "doc-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["filename"], "document1.pdf")

        # Unauthorized user fetch returns None
        self.assertIsNone(repo.get_document("user-wrong", "doc-001"))

        # 3. List documents
        user_docs = repo.list_user_documents("user-abc")
        self.assertEqual(len(user_docs), 1)

        # 4. Update document status
        updated = repo.update_document_status("doc-001", "indexed", chunk_count=5)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "indexed")
        self.assertEqual(updated["chunk_count"], 5)

        # 5. Delete document
        deleted = repo.delete_document("user-abc", "doc-001")
        self.assertTrue(deleted)
        self.assertIsNone(repo.get_document("user-abc", "doc-001"))

    @patch("app.services.document_repository.create_client")
    def test_supabase_client_crud_operations(self, mock_create_client):
        """Test document metadata operations when Supabase client is initialized."""
        mock_supabase = MagicMock()
        mock_create_client.return_value = mock_supabase

        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_anon_key="test_key",
        )
        repo = DocumentRepository(settings=settings)
        self.assertIsNotNone(repo.client)

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        doc_data = {
            "id": "doc-002",
            "user_id": "user-xyz",
            "filename": "document2.pdf",
        }
        mock_table.insert.return_value.execute.return_value.data = [doc_data]

        inserted = repo.insert_document(doc_data)
        self.assertEqual(inserted, doc_data)
        mock_supabase.table.assert_called_with("documents")


if __name__ == "__main__":
    unittest.main()
