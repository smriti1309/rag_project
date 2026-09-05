"""Cloudflare R2 Storage Service module using boto3 S3-compatible client."""

import logging
from pathlib import Path
from typing import Optional
import boto3
from botocore.client import Config

from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


class R2StorageService:
    """Service for managing file storage in Cloudflare R2 using boto3 S3 API."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initialize R2StorageService with configuration and S3 client.

        Args:
            settings: Application settings instance.
        """
        self.settings = settings or default_settings
        self.bucket_name = self.settings.r2_bucket_name
        self.s3_client = self._init_s3_client()

    def _init_s3_client(self) -> Optional[boto3.client]:
        """Initialize boto3 S3 client for Cloudflare R2 endpoint.

        Returns:
            boto3.client or None: Configured S3 client, or None if credentials missing (local fallback).
        """
        endpoint_url = self.settings.r2_endpoint
        if not endpoint_url and self.settings.r2_account_id:
            endpoint_url = f"https://{self.settings.r2_account_id}.r2.cloudflarestorage.com"

        if not (endpoint_url and self.settings.r2_access_key_id and self.settings.r2_secret_access_key):
            logger.warning(
                "Cloudflare R2 credentials not fully configured in environment. Using local filesystem storage fallback."
            )
            return None

        try:
            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=self.settings.r2_access_key_id,
                aws_secret_access_key=self.settings.r2_secret_access_key,
                config=Config(signature_version="s3v4"),
                region_name="auto",
            )
            logger.info("Successfully initialized Cloudflare R2 S3 client for bucket '%s'.", self.bucket_name)
            return client
        except Exception as e:
            logger.error("Failed to initialize boto3 S3 client for Cloudflare R2: %s", e)
            return None

    def generate_object_key(self, user_id: str, document_id: str, original_filename: str) -> str:
        """Generate structured user-isolated object key for Cloudflare R2.

        Hierarchy: {user_id}/{document_id}/{original_filename}

        Args:
            user_id: Authenticated Supabase user ID.
            document_id: Unique UUID document identifier.
            original_filename: Name of the uploaded file.

        Returns:
            str: Object key formatted as user_id/document_id/original_filename
        """
        clean_filename = Path(original_filename).name
        return f"{user_id}/{document_id}/{clean_filename}"

    def upload_file(
        self,
        file_bytes: bytes,
        object_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file content bytes to Cloudflare R2 (or local fallback).

        Args:
            file_bytes: Raw bytes of the file.
            object_key: Destination object key in R2.
            content_type: MIME type of the file.

        Returns:
            str: Object key of the stored file.

        Raises:
            OSError: If file upload fails.
        """
        if self.s3_client:
            try:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=object_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
                logger.info("Successfully uploaded %d bytes to R2 bucket '%s' at '%s'.", len(file_bytes), self.bucket_name, object_key)
                return object_key
            except Exception as e:
                logger.error("R2 file upload failed for key '%s': %s", object_key, e)
                raise OSError(f"Cloudflare R2 upload failure: {e}") from e
        else:
            # Fallback to local storage
            local_path = self.settings.upload_directory / object_key
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(file_bytes)
                logger.info("Saved %d bytes to local fallback path: %s", len(file_bytes), local_path)
                return object_key
            except Exception as e:
                raise OSError(f"Local storage fallback failure: {e}") from e

    def download_file(self, object_key: str, target_path: Path) -> Path:
        """Download object from Cloudflare R2 (or local fallback) into target_path.

        Args:
            object_key: Source object key in R2.
            target_path: Local destination file path.

        Returns:
            Path: Path to the downloaded file.

        Raises:
            OSError: If file download fails.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if self.s3_client:
            try:
                self.s3_client.download_file(
                    Bucket=self.bucket_name,
                    Key=object_key,
                    Filename=str(target_path),
                )
                logger.info("Successfully downloaded R2 object '%s' to '%s'.", object_key, target_path)
                return target_path
            except Exception as e:
                logger.error("R2 file download failed for key '%s': %s", object_key, e)
                raise OSError(f"Cloudflare R2 download failure: {e}") from e
        else:
            # Fallback from local storage
            local_path = self.settings.upload_directory / object_key
            if not local_path.exists():
                raise FileNotFoundError(f"File not found in local fallback storage: {local_path}")
            target_path.write_bytes(local_path.read_bytes())
            return target_path

    def delete_file(self, object_key: str) -> bool:
        """Delete object from Cloudflare R2 (or local fallback).

        Args:
            object_key: Object key to delete.

        Returns:
            bool: True if deleted successfully.
        """
        if self.s3_client:
            try:
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=object_key,
                )
                logger.info("Successfully deleted R2 object '%s'.", object_key)
                return True
            except Exception as e:
                logger.error("R2 file deletion failed for key '%s': %s", object_key, e)
                return False
        else:
            local_path = self.settings.upload_directory / object_key
            if local_path.exists():
                try:
                    local_path.unlink()
                    return True
                except Exception as e:
                    logger.error("Failed to delete local fallback file: %s", e)
            return False
