from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.services.r2_storage_service import R2StorageService


class TestR2StorageService(unittest.TestCase):
    """Unit test suite for R2StorageService."""

    def setUp(self):
        self.settings = Settings(
            r2_account_id="test_account",
            r2_access_key_id="test_access_key",
            r2_secret_access_key="test_secret_key",
            r2_bucket_name="test_bucket",
        )

    def test_object_key_generation(self):
        """Test structured object key creation in user-isolated hierarchy."""
        service = R2StorageService(settings=self.settings)
        key = service.generate_object_key("user-123", "doc-456", "test_report.pdf")
        self.assertEqual(key, "user-123/doc-456/test_report.pdf")

    @patch("boto3.client")
    def test_upload_file_with_r2_client(self, mock_boto_client):
        """Test uploading file bytes to Cloudflare R2 when S3 client is initialized."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        service = R2StorageService(settings=self.settings)
        key = "user-123/doc-456/test.pdf"
        result_key = service.upload_file(b"test data", key, "application/pdf")

        self.assertEqual(result_key, key)
        mock_s3.put_object.assert_called_once_with(
            Bucket="test_bucket",
            Key=key,
            Body=b"test data",
            ContentType="application/pdf",
        )

    def test_local_filesystem_fallback_upload_and_download(self):
        """Test local filesystem storage fallback when R2 credentials are absent."""
        with tempfile.TemporaryDirectory() as temp_dir:
            fallback_settings = Settings(
                upload_directory=Path(temp_dir),
                r2_access_key_id=None,
            )
            service = R2StorageService(settings=fallback_settings)
            self.assertIsNone(service.s3_client)

            key = "user-abc/doc-xyz/local.pdf"
            service.upload_file(b"local content", key)

            target_path = Path(temp_dir) / "downloaded.pdf"
            service.download_file(key, target_path)

            self.assertTrue(target_path.exists())
            self.assertEqual(target_path.read_bytes(), b"local content")

    @patch("boto3.client")
    def test_delete_file_r2(self, mock_boto_client):
        """Test deleting object from Cloudflare R2."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        service = R2StorageService(settings=self.settings)
        key = "user-123/doc-456/test.pdf"
        success = service.delete_file(key)

        self.assertTrue(success)
        mock_s3.delete_object.assert_called_once_with(
            Bucket="test_bucket",
            Key=key,
        )


if __name__ == "__main__":
    unittest.main()
