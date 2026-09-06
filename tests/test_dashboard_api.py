import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.dashboard import DashboardStatsResponse


class TestDashboardAPI(unittest.TestCase):
    """Test suite for /dashboard/stats API endpoint."""

    def setUp(self):
        self.client = TestClient(app)
        self.user_id = "user-test-12345"

    @patch("app.api.dashboard.QdrantService")
    @patch("app.api.dashboard.DocumentRepository")
    @patch("app.api.dashboard.get_current_user_id")
    def test_get_dashboard_stats_success(
        self, mock_get_user, mock_repo_cls, mock_qdrant_cls
    ):
        """Test successful dashboard stats retrieval with user isolation."""
        mock_get_user.return_value = self.user_id

        # Mock document repository records for user
        mock_repo = MagicMock()
        mock_repo.list_user_documents.return_value = [
            {
                "id": "doc1",
                "user_id": self.user_id,
                "status": "indexed",
                "chunk_count": 5,
                "uploaded_at": "2026-09-06T12:00:00Z",
            },
            {
                "id": "doc2",
                "user_id": self.user_id,
                "status": "indexed",
                "chunk_count": 10,
                "uploaded_at": "2026-09-06T11:00:00Z",
            },
        ]
        mock_repo_cls.return_value = mock_repo

        # Mock Qdrant service
        mock_qdrant = MagicMock()
        mock_qdrant.client.collection_exists.return_value = True
        mock_qdrant.client.count.return_value = MagicMock(count=15)
        mock_qdrant_cls.return_value = mock_qdrant

        response = self.client.get("/dashboard/stats")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["documents_indexed"], 2)
        self.assertEqual(data["total_chunks"], 15)
        self.assertEqual(data["total_embeddings"], 15)
        self.assertEqual(data["qdrant_status"], "Connected")
        self.assertEqual(data["backend_status"], "Healthy")
        self.assertEqual(data["last_uploaded_time"], "2026-09-06 12:00:00")
        self.assertEqual(data["qdrant_collection"], "knowledge_base_v2")

        # Validate with Pydantic model
        stats_model = DashboardStatsResponse.model_validate(data)
        self.assertEqual(stats_model.documents_indexed, 2)

    @patch("app.api.dashboard.QdrantService")
    @patch("app.api.dashboard.DocumentRepository")
    @patch("app.api.dashboard.get_current_user_id")
    def test_get_dashboard_stats_user_isolation(
        self, mock_get_user, mock_repo_cls, mock_qdrant_cls
    ):
        """Test user isolation when filtering user's stats."""
        mock_get_user.return_value = "user-other-999"

        mock_repo = MagicMock()
        mock_repo.list_user_documents.return_value = []
        mock_repo_cls.return_value = mock_repo

        mock_qdrant = MagicMock()
        mock_qdrant.client.collection_exists.return_value = True
        mock_qdrant.client.count.return_value = MagicMock(count=0)
        mock_qdrant_cls.return_value = mock_qdrant

        response = self.client.get("/dashboard/stats")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["documents_indexed"], 0)
        self.assertEqual(data["total_chunks"], 0)
        self.assertEqual(data["total_embeddings"], 0)
        self.assertIsNone(data["last_uploaded_time"])

    @patch("app.api.dashboard.QdrantService")
    @patch("app.api.dashboard.DocumentRepository")
    @patch("app.api.dashboard.get_current_user_id")
    def test_get_dashboard_stats_qdrant_disconnected_fallback(
        self, mock_get_user, mock_repo_cls, mock_qdrant_cls
    ):
        """Test graceful fallback when Qdrant connection raises an exception."""
        mock_get_user.return_value = self.user_id

        mock_repo = MagicMock()
        mock_repo.list_user_documents.return_value = [
            {
                "id": "doc1",
                "user_id": self.user_id,
                "status": "indexed",
                "chunk_count": 8,
                "uploaded_at": "2026-09-06T14:00:00Z",
            }
        ]
        mock_repo_cls.return_value = mock_repo

        # Force Qdrant initialization or collection check to raise ConnectionError
        mock_qdrant_cls.side_effect = Exception("Qdrant cluster unreachable")

        response = self.client.get("/dashboard/stats")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["documents_indexed"], 1)
        self.assertEqual(data["total_chunks"], 8)
        self.assertEqual(data["total_embeddings"], 0)
        self.assertEqual(data["qdrant_status"], "Disconnected")
        self.assertEqual(data["backend_status"], "Healthy")


if __name__ == "__main__":
    unittest.main()
