"""Document repository module for Supabase Database metadata CRUD operations using supabase-py."""

from datetime import datetime, timezone
import logging
from typing import Any, Optional
from supabase import Client, create_client

from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Repository for managing document metadata in Supabase PostgreSQL using supabase-py."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initialize DocumentRepository with Supabase client.

        Args:
            settings: Optional Settings instance.
        """
        self.settings = settings or default_settings
        self.client: Optional[Client] = self._init_supabase_client()
        # In-memory dev fallback store if Supabase database is unconfigured locally
        self._memory_store: dict[str, dict[str, Any]] = {}

    def _init_supabase_client(self) -> Optional[Client]:
        """Initialize official supabase-py Client using application settings.

        Returns:
            Client or None: Configured Supabase client or None if unconfigured.
        """
        url = self.settings.supabase_url
        key = self.settings.supabase_service_role_key or self.settings.supabase_anon_key

        if not (url and key):
            logger.warning(
                "Supabase URL/Key missing. Using in-memory DocumentRepository fallback for local development."
            )
            return None

        try:
            client = create_client(url, key)
            logger.info("Successfully initialized supabase-py client for DocumentRepository.")
            return client
        except Exception as e:
            logger.error("Failed to initialize supabase-py client: %s", e)
            return None

    def insert_document(self, doc_data: dict[str, Any]) -> dict[str, Any]:
        """Insert a document metadata record into Supabase PostgreSQL documents table.

        Args:
            doc_data: Metadata dictionary containing document attributes.

        Returns:
            dict: Stored document metadata.
        """
        doc_id = doc_data.get("id")
        user_id = doc_data.get("user_id")

        if self.client:
            try:
                res = self.client.table("documents").insert(doc_data).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error("Failed to insert document metadata into Supabase DB: %s", e)

        # Fallback to memory store
        if doc_id:
            self._memory_store[doc_id] = doc_data
        return doc_data

    def list_user_documents(self, user_id: str) -> list[dict[str, Any]]:
        """List all document metadata records belonging to the specified user_id.

        Args:
            user_id: Authenticated Supabase user ID.

        Returns:
            list[dict]: List of document metadata dictionaries.
        """
        if self.client:
            try:
                res = (
                    self.client.table("documents")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("uploaded_at", desc=True)
                    .execute()
                )
                if res.data is not None:
                    return res.data
            except Exception as e:
                logger.error("Failed to list user documents from Supabase DB: %s", e)

        # Fallback to memory store
        return [
            doc for doc in self._memory_store.values() if doc.get("user_id") == user_id
        ]

    def get_document(self, user_id: str, document_id: str) -> Optional[dict[str, Any]]:
        """Retrieve document metadata for a specific document belonging to user_id.

        Args:
            user_id: Authenticated user ID.
            document_id: Document UUID.

        Returns:
            dict or None: Document metadata if found and owned by user_id.
        """
        if self.client:
            try:
                res = (
                    self.client.table("documents")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("id", document_id)
                    .execute()
                )
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error("Failed to fetch document metadata from Supabase DB: %s", e)

        # Fallback to memory store
        doc = self._memory_store.get(document_id)
        if doc and doc.get("user_id") == user_id:
            return doc
        return None

    def update_document_status(
        self, document_id: str, status: str, chunk_count: int = 0
    ) -> Optional[dict[str, Any]]:
        """Update the status and chunk_count of a document metadata record.

        Args:
            document_id: Document UUID.
            status: New status string ('uploaded', 'processing', 'indexed', 'failed').
            chunk_count: Number of chunks parsed/indexed.

        Returns:
            dict or None: Updated document metadata.
        """
        update_data = {
            "status": status,
            "chunk_count": chunk_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if self.client:
            try:
                res = (
                    self.client.table("documents")
                    .update(update_data)
                    .eq("id", document_id)
                    .execute()
                )
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error("Failed to update document status in Supabase DB: %s", e)

        # Fallback to memory store
        if document_id in self._memory_store:
            self._memory_store[document_id].update(update_data)
            return self._memory_store[document_id]
        return None

    def delete_document(self, user_id: str, document_id: str) -> bool:
        """Delete document metadata record belonging to user_id.

        Args:
            user_id: Authenticated user ID.
            document_id: Document UUID.

        Returns:
            bool: True if deleted successfully.
        """
        if self.client:
            try:
                res = (
                    self.client.table("documents")
                    .delete()
                    .eq("user_id", user_id)
                    .eq("id", document_id)
                    .execute()
                )
                return bool(res.data)
            except Exception as e:
                logger.error("Failed to delete document metadata from Supabase DB: %s", e)

        # Fallback to memory store
        if document_id in self._memory_store and self._memory_store[document_id].get("user_id") == user_id:
            del self._memory_store[document_id]
            return True
        return False
