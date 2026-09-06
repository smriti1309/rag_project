"""Unit tests for Conversational RAG features (LLM query rewriting, prompt formatting, history fetching, and fail-safe fallbacks)."""

from unittest.mock import MagicMock, patch
import pytest

from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.llm_service import LLMService


class TestConversationalRAG:
    """Test suite for Conversational RAG implementation."""

    def test_llm_service_rewrite_query_empty_history_returns_original(self) -> None:
        """Verify rewrite_query returns original query when history is empty."""
        llm_service = LLMService(client=MagicMock())
        result = llm_service.rewrite_query("What are its advantages?", history=[])
        assert result == "What are its advantages?"

    def test_llm_service_rewrite_query_rephrases_with_history(self) -> None:
        """Verify rewrite_query uses Gemini to rephrase ambiguous query when history exists."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '"What are the advantages of supervised learning?"'
        mock_client.models.generate_content.return_value = mock_response

        llm_service = LLMService(client=mock_client)
        history = [
            {"role": "user", "content": "What is supervised learning?"},
            {"role": "assistant", "content": "Supervised learning is a machine learning technique..."},
        ]

        result = llm_service.rewrite_query("What are its advantages?", history=history)

        assert result == "What are the advantages of supervised learning?"
        mock_client.models.generate_content.assert_called_once()
        prompt_arg = mock_client.models.generate_content.call_args[1]["contents"]
        assert "CONVERSATION HISTORY" in prompt_arg
        assert "Supervised learning is a machine learning technique" in prompt_arg
        assert "What are its advantages?" in prompt_arg

    def test_llm_service_prompt_formats_history_section(self) -> None:
        """Verify _build_prompt includes formatted CONVERSATION HISTORY when history is passed."""
        llm_service = LLMService(client=MagicMock())
        chunks = [{"text": "Sample document content.", "source_file": "doc.pdf", "page": 1}]
        history = [
            {"role": "user", "content": "What is machine learning?"},
            {"role": "assistant", "content": "Machine learning is a field of AI."},
        ]

        prompt = llm_service._build_prompt(
            query="What are its applications?", chunks=chunks, history=history
        )

        assert "====================" in prompt
        assert "CONVERSATION HISTORY" in prompt
        assert "User: What is machine learning?" in prompt
        assert "Assistant: Machine learning is a field of AI." in prompt
        assert "Sample document content." in prompt
        assert "What are its applications?" in prompt

    def test_chat_service_first_turn_skips_rewriting(self) -> None:
        """Verify first turn (empty history) skips query rewriting and passes raw query to retrieval."""
        mock_emb = MagicMock()
        mock_qdrant = MagicMock()
        mock_bm25 = MagicMock()
        mock_llm = MagicMock()
        mock_repo = MagicMock()

        mock_repo.get_conversation.return_value = {"id": "conv-1", "user_id": "user-1"}
        mock_repo.list_conversation_messages.return_value = []
        mock_qdrant.search_vectors.return_value = [
            {"document_id": "doc-1", "chunk_id": 1, "score": 0.9, "text": "Supervised learning definition."}
        ]
        mock_bm25.search_chunks.return_value = [
            {"document_id": "doc-1", "chunk_id": 1, "bm25_score": 5.0, "text": "Supervised learning definition."}
        ]
        mock_llm.generate_answer.return_value = "Supervised learning is..."

        chat_service = ChatService(
            embedding_service=mock_emb,
            qdrant_service=mock_qdrant,
            bm25_service=mock_bm25,
            llm_service=mock_llm,
            conversation_repository=mock_repo,
        )

        request = ChatRequest(query="What is supervised learning?", conversation_id="conv-1")
        response = chat_service.generate_response(request, user_id="user-1")

        # History should have been fetched BEFORE message insertion
        mock_repo.list_conversation_messages.assert_called_once_with("user-1", "conv-1")
        # Query rewriter should NOT have been called
        mock_llm.rewrite_query.assert_not_called()
        # Embed and BM25 search must use raw query
        mock_emb.embed_query.assert_called_once_with("What is supervised learning?")
        mock_bm25.search_chunks.assert_called_once_with(
            query="What is supervised learning?", user_id="user-1", document_id=None, top_k=20
        )
        # LLM generate answer called with empty history
        mock_llm.generate_answer.assert_called_once()
        assert mock_llm.generate_answer.call_args[1]["history"] == []

    def test_chat_service_followup_turn_uses_rewritten_query(self) -> None:
        """Verify follow-up turn (with history) rewrites query and uses standalone query for Qdrant & BM25."""
        mock_emb = MagicMock()
        mock_qdrant = MagicMock()
        mock_bm25 = MagicMock()
        mock_llm = MagicMock()
        mock_repo = MagicMock()

        history_messages = [
            {"id": "m1", "role": "user", "content": "What is supervised learning?"},
            {"id": "m2", "role": "assistant", "content": "Supervised learning is a ML method."},
        ]

        mock_repo.get_conversation.return_value = {"id": "conv-1", "user_id": "user-1"}
        mock_repo.list_conversation_messages.return_value = history_messages
        mock_llm.rewrite_query.return_value = "What are the advantages of supervised learning?"
        mock_qdrant.search_vectors.return_value = [
            {"document_id": "doc-1", "chunk_id": 2, "score": 0.88, "text": "Advantages of supervised learning..."}
        ]
        mock_bm25.search_chunks.return_value = [
            {"document_id": "doc-1", "chunk_id": 2, "bm25_score": 4.5, "text": "Advantages of supervised learning..."}
        ]
        mock_llm.generate_answer.return_value = "Advantages include accuracy..."

        chat_service = ChatService(
            embedding_service=mock_emb,
            qdrant_service=mock_qdrant,
            bm25_service=mock_bm25,
            llm_service=mock_llm,
            conversation_repository=mock_repo,
        )

        request = ChatRequest(query="What are its advantages?", conversation_id="conv-1")
        response = chat_service.generate_response(request, user_id="user-1")

        # Verify rewrite_query was called with history
        mock_llm.rewrite_query.assert_called_once_with("What are its advantages?", history=history_messages)
        # Verify standalone query was passed to embedding & BM25 search
        mock_emb.embed_query.assert_called_once_with("What are the advantages of supervised learning?")
        mock_bm25.search_chunks.assert_called_once_with(
            query="What are the advantages of supervised learning?", user_id="user-1", document_id=None, top_k=20
        )
        # Verify generate_answer received original question + history
        mock_llm.generate_answer.assert_called_once()
        call_args = mock_llm.generate_answer.call_args[1]
        assert call_args["query"] == "What are its advantages?"
        assert call_args["history"] == history_messages

    def test_chat_service_rewriter_error_fallback(self) -> None:
        """Verify that if query rewriter raises an error, ChatService falls back to raw query."""
        mock_emb = MagicMock()
        mock_qdrant = MagicMock()
        mock_bm25 = MagicMock()
        mock_llm = MagicMock()
        mock_repo = MagicMock()

        mock_repo.get_conversation.return_value = {"id": "conv-1", "user_id": "user-1"}
        mock_repo.list_conversation_messages.return_value = [
            {"role": "user", "content": "What is supervised learning?"}
        ]
        mock_llm.rewrite_query.side_effect = Exception("Gemini API timeout")
        mock_qdrant.search_vectors.return_value = []
        mock_bm25.search_chunks.return_value = []

        chat_service = ChatService(
            embedding_service=mock_emb,
            qdrant_service=mock_qdrant,
            bm25_service=mock_bm25,
            llm_service=mock_llm,
            conversation_repository=mock_repo,
        )

        request = ChatRequest(query="What are its advantages?", conversation_id="conv-1")
        chat_service.generate_response(request, user_id="user-1")

        # Embedding & BM25 should fallback to raw query
        mock_emb.embed_query.assert_called_once_with("What are its advantages?")
        mock_bm25.search_chunks.assert_called_once_with(
            query="What are its advantages?", user_id="user-1", document_id=None, top_k=20
        )
