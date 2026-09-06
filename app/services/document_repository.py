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
        self._chunks_memory_store: list[dict[str, Any]] = []

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
            self._chunks_memory_store = [
                c for c in self._chunks_memory_store if c.get("document_id") != document_id
            ]
            return True
        return False

    def insert_document_chunks(self, chunks_data: list[dict[str, Any]]) -> bool:
        """Batch upsert document chunk records into Supabase PostgreSQL document_chunks table.

        Args:
            chunks_data: List of chunk metadata dictionaries.

        Returns:
            bool: True if inserted/upserted successfully.
        """
        if not chunks_data:
            return True

        if self.client:
            try:
                self.client.table("document_chunks").upsert(
                    chunks_data, on_conflict="document_id,chunk_id"
                ).execute()
                return True
            except Exception as e:
                logger.error("Failed to upsert document chunks into Supabase DB: %s", e)

        # Fallback to memory store (prevent duplicate (document_id, chunk_id) keys)
        new_keys = {(c["document_id"], c["chunk_id"]) for c in chunks_data}
        self._chunks_memory_store = [
            c
            for c in self._chunks_memory_store
            if (c.get("document_id"), c.get("chunk_id")) not in new_keys
        ]
        self._chunks_memory_store.extend(chunks_data)
        return True

    def _get_indexed_doc_ids(self, user_id: str) -> set[str]:
        """Fetch set of document IDs owned by user_id that are in status='indexed'."""
        if self.client:
            try:
                res = (
                    self.client.table("documents")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("status", "indexed")
                    .execute()
                )
                if res.data is not None:
                    return {doc["id"] for doc in res.data}
            except Exception as e:
                logger.error("Failed to fetch indexed document IDs: %s", e)

        # Fallback to memory store
        return {
            doc_id
            for doc_id, doc in self._memory_store.items()
            if doc.get("user_id") == user_id and doc.get("status") == "indexed"
        }

    def get_user_chunks(
        self, user_id: str, document_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Retrieve document chunks for specified user_id belonging ONLY to documents with status='indexed'.

        Args:
            user_id: Authenticated user ID.
            document_id: Optional document UUID filter.

        Returns:
            list[dict[str, Any]]: List of matching document chunk dictionaries from indexed documents.
        """
        indexed_doc_ids = self._get_indexed_doc_ids(user_id)
        if not indexed_doc_ids:
            return []

        if document_id and document_id not in indexed_doc_ids:
            return []

        # Fetch chunks belonging to indexed document IDs
        if self.client:
            try:
                target_doc_ids = [document_id] if document_id else list(indexed_doc_ids)
                query = (
                    self.client.table("document_chunks")
                    .select("*")
                    .eq("user_id", user_id)
                    .in_("document_id", target_doc_ids)
                )
                res = query.order("chunk_id", desc=False).execute()
                if res.data is not None:
                    return res.data
            except Exception as e:
                logger.error("Failed to fetch user chunks from Supabase DB: %s", e)

        # Fallback to memory store
        target_ids = {document_id} if document_id else indexed_doc_ids
        results = [
            c
            for c in self._chunks_memory_store
            if c.get("user_id") == user_id and c.get("document_id") in target_ids
        ]
        return results

    def get_user_watermark(self, user_id: str) -> tuple[Optional[str], int]:
        """Fetch the latest indexed document timestamp and total indexed doc count for watermark checks.

        Args:
            user_id: Authenticated user ID.

        Returns:
            tuple[Optional[str], int]: (latest_updated_at_iso, indexed_document_count)
        """
        if self.client:
            try:
                res = (
                    self.client.table("documents")
                    .select("updated_at")
                    .eq("user_id", user_id)
                    .eq("status", "indexed")
                    .order("updated_at", desc=True)
                    .execute()
                )
                if res.data is not None:
                    count = len(res.data)
                    latest_ts = res.data[0].get("updated_at") if count > 0 else None
                    return (latest_ts, count)
            except Exception as e:
                logger.error("Failed to fetch user watermark from Supabase DB: %s", e)

        # Fallback to memory store
        user_indexed_docs = [
            doc
            for doc in self._memory_store.values()
            if doc.get("user_id") == user_id and doc.get("status") == "indexed"
        ]
        count = len(user_indexed_docs)
        if count == 0:
            return (None, 0)

        latest_ts = max(
            doc.get("updated_at", "") for doc in user_indexed_docs
        )
        return (latest_ts, count)

