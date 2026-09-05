"""Conversation repository module for Supabase Database metadata CRUD operations for chat history."""

from datetime import datetime, timezone
import logging
from typing import Any, Optional
import uuid
from supabase import Client, create_client

from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


class ConversationRepository:
    """Repository for managing chat conversations and messages in Supabase PostgreSQL."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initialize ConversationRepository with Supabase client.

        Args:
            settings: Optional Settings instance.
        """
        self.settings = settings or default_settings
        self.client: Optional[Client] = self._init_supabase_client()
        # In-memory dev fallback store
        self._conversations_mem: dict[str, dict[str, Any]] = {}
        self._messages_mem: dict[str, list[dict[str, Any]]] = {}

    def _init_supabase_client(self) -> Optional[Client]:
        """Initialize official supabase-py Client using application settings.

        Returns:
            Client or None: Configured Supabase client or None if unconfigured.
        """
        url = self.settings.supabase_url
        key = self.settings.supabase_service_role_key or self.settings.supabase_anon_key

        if not (url and key):
            logger.warning(
                "Supabase URL/Key missing. Using in-memory ConversationRepository fallback for local development."
            )
            return None

        try:
            client = create_client(url, key)
            logger.info("Successfully initialized supabase-py client for ConversationRepository.")
            return client
        except Exception as e:
            logger.error("Failed to initialize supabase-py client for ConversationRepository: %s", e)
            return None

    def create_conversation(
        self, user_id: str, title: str = "New Conversation"
    ) -> dict[str, Any]:
        """Create a new conversation record for user_id.

        Args:
            user_id: Authenticated user UUID.
            title: Title string.

        Returns:
            dict: Created conversation record.
        """
        conv_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        conv_data = {
            "id": conv_id,
            "user_id": user_id,
            "title": title,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        if self.client:
            try:
                res = self.client.table("conversations").insert(conv_data).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error("Failed to insert conversation into Supabase DB: %s", e)

        # Fallback to memory store
        self._conversations_mem[conv_id] = conv_data
        self._messages_mem[conv_id] = []
        return conv_data

    def list_user_conversations(self, user_id: str) -> list[dict[str, Any]]:
        """List all conversations belonging to user_id ordered by updated_at desc.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            list[dict]: List of conversation records.
        """
        if self.client:
            try:
                res = (
                    self.client.table("conversations")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("updated_at", desc=True)
                    .execute()
                )
                if res.data is not None:
                    return res.data
            except Exception as e:
                logger.error("Failed to list user conversations from Supabase DB: %s", e)

        # Fallback to memory store
        return sorted(
            [c for c in self._conversations_mem.values() if c.get("user_id") == user_id],
            key=lambda x: x.get("updated_at", ""),
            reverse=True,
        )

    def get_conversation(self, user_id: str, conversation_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a specific conversation belonging to user_id.

        Args:
            user_id: Authenticated user UUID.
            conversation_id: Conversation UUID.

        Returns:
            dict or None: Conversation record if found and owned by user_id.
        """
        if self.client:
            try:
                res = (
                    self.client.table("conversations")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("id", conversation_id)
                    .execute()
                )
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error("Failed to fetch conversation from Supabase DB: %s", e)

        # Fallback to memory store
        conv = self._conversations_mem.get(conversation_id)
        if conv and conv.get("user_id") == user_id:
            return conv
        return None

    def update_conversation_title(
        self, user_id: str, conversation_id: str, title: str
    ) -> Optional[dict[str, Any]]:
        """Update conversation title and updated_at timestamp.

        Args:
            user_id: Authenticated user UUID.
            conversation_id: Conversation UUID.
            title: New title string.

        Returns:
            dict or None: Updated conversation record.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        update_data = {"title": title, "updated_at": now_iso}

        if self.client:
            try:
                res = (
                    self.client.table("conversations")
                    .update(update_data)
                    .eq("user_id", user_id)
                    .eq("id", conversation_id)
                    .execute()
                )
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error("Failed to update conversation title in Supabase DB: %s", e)

        # Fallback to memory store
        conv = self._conversations_mem.get(conversation_id)
        if conv and conv.get("user_id") == user_id:
            conv.update(update_data)
            return conv
        return None

    def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        """Delete conversation and its cascade messages.

        Args:
            user_id: Authenticated user UUID.
            conversation_id: Conversation UUID.

        Returns:
            bool: True if deleted successfully.
        """
        if self.client:
            try:
                res = (
                    self.client.table("conversations")
                    .delete()
                    .eq("user_id", user_id)
                    .eq("id", conversation_id)
                    .execute()
                )
                return bool(res.data)
            except Exception as e:
                logger.error("Failed to delete conversation from Supabase DB: %s", e)

        # Fallback to memory store
        conv = self._conversations_mem.get(conversation_id)
        if conv and conv.get("user_id") == user_id:
            del self._conversations_mem[conversation_id]
            self._messages_mem.pop(conversation_id, None)
            return True
        return False

    def insert_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: Optional[list[dict[str, Any]]] = None,
        retrieved_chunk_count: int = 0,
        retrieval_time_ms: int = 0,
    ) -> dict[str, Any]:
        """Insert a message record into public.chat_messages.

        Args:
            conversation_id: Parent conversation UUID.
            role: 'user' or 'assistant'.
            content: Message content text.
            citations: Source citations list.
            retrieved_chunk_count: Number of chunks retrieved.
            retrieval_time_ms: Retrieval latency in ms.

        Returns:
            dict: Inserted message record.
        """
        msg_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        msg_data = {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "citations": citations,
            "retrieved_chunk_count": retrieved_chunk_count,
            "retrieval_time_ms": retrieval_time_ms,
            "created_at": now_iso,
        }

        if self.client:
            try:
                res = self.client.table("chat_messages").insert(msg_data).execute()
                # Touch parent conversation updated_at
                self.client.table("conversations").update({"updated_at": now_iso}).eq(
                    "id", conversation_id
                ).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error("Failed to insert chat_message into Supabase DB: %s", e)

        # Fallback to memory store
        if conversation_id not in self._messages_mem:
            self._messages_mem[conversation_id] = []
        self._messages_mem[conversation_id].append(msg_data)
        if conversation_id in self._conversations_mem:
            self._conversations_mem[conversation_id]["updated_at"] = now_iso
        return msg_data

    def list_conversation_messages(
        self, user_id: str, conversation_id: str
    ) -> list[dict[str, Any]]:
        """List all messages for conversation_id belonging to user_id ordered by created_at asc.

        Args:
            user_id: Authenticated user UUID.
            conversation_id: Conversation UUID.

        Returns:
            list[dict]: List of chat message records.
        """
        # First verify conversation ownership
        conv = self.get_conversation(user_id, conversation_id)
        if not conv:
            return []

        if self.client:
            try:
                res = (
                    self.client.table("chat_messages")
                    .select("*")
                    .eq("conversation_id", conversation_id)
                    .order("created_at", desc=False)
                    .execute()
                )
                if res.data is not None:
                    return res.data
            except Exception as e:
                logger.error("Failed to list chat_messages from Supabase DB: %s", e)

        # Fallback to memory store
        return sorted(
            self._messages_mem.get(conversation_id, []),
            key=lambda x: x.get("created_at", ""),
        )
