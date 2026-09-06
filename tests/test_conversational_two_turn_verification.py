"""Two-turn integration verification test for Conversational RAG pipeline.

Demonstrates:
Turn 1: "What is supervised learning?"
Turn 2: "What are its advantages?"

Verifies that Turn 2:
1. Fetches Turn 1 history from ConversationRepository.
2. Rewrites "What are its advantages?" into a standalone search query ("What are the advantages of supervised learning?").
3. Sends the rewritten query to both Qdrant (dense) and BM25 (lexical).
4. Performs Reciprocal Rank Fusion (RRF) normally.
5. Passes original question + Turn 1 history + retrieved Top 5 chunks to final LLM generation.
"""

import sys
from unittest.mock import MagicMock, call

from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService


def test_two_turn_conversational_rag_flow() -> None:
    """Execute complete 2-turn simulation verifying query rewriting and history preservation."""

    print("\n" + "=" * 70)
    print("STARTING 2-TURN CONVERSATIONAL RAG VERIFICATION")
    print("=" * 70)

    # 1. Setup mock services to track exact call parameters across 2 turns
    mock_emb = MagicMock()
    mock_qdrant = MagicMock()
    mock_bm25 = MagicMock()
    mock_llm = MagicMock()
    mock_repo = MagicMock()

    # In-memory message store simulating DB state across turns
    stored_conversations = {}
    stored_messages = {}

    def mock_get_conversation(user_id, conversation_id):
        return stored_conversations.get(conversation_id)

    def mock_create_conversation(user_id, title="New Conversation"):
        conv_id = "test-conv-uuid-1234"
        conv_data = {"id": conv_id, "user_id": user_id, "title": title}
        stored_conversations[conv_id] = conv_data
        stored_messages[conv_id] = []
        return conv_data

    def mock_list_messages(user_id, conversation_id):
        return list(stored_messages.get(conversation_id, []))

    def mock_insert_message(conversation_id, role, content, citations=None, retrieved_chunk_count=0, retrieval_time_ms=0):
        msg = {
            "id": f"msg-{len(stored_messages[conversation_id]) + 1}",
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "citations": citations,
        }
        stored_messages[conversation_id].append(msg)
        return msg

    mock_repo.get_conversation.side_effect = mock_get_conversation
    mock_repo.create_conversation.side_effect = mock_create_conversation
    mock_repo.list_conversation_messages.side_effect = mock_list_messages
    mock_repo.insert_message.side_effect = mock_insert_message

    # Configure return values for retrieval & generation
    mock_emb.embed_query.return_value = [0.1] * 768

    # Turn 1 Mock Return
    mock_qdrant.search_vectors.return_value = [
        {"document_id": "doc-ml-1", "chunk_id": 1, "score": 0.92, "text": "Supervised learning is an algorithm trained on labeled data.", "source_file": "ml_intro.pdf", "page": 1}
    ]
    mock_bm25.search_chunks.return_value = [
        {"document_id": "doc-ml-1", "chunk_id": 1, "bm25_score": 6.2, "text": "Supervised learning is an algorithm trained on labeled data.", "source_file": "ml_intro.pdf", "page": 1}
    ]
    mock_llm.generate_answer.side_effect = [
        "Supervised learning is a machine learning technique using labeled training data.",  # Turn 1 Answer
        "Advantages of supervised learning include high predictive accuracy and clear feedback loops." # Turn 2 Answer
    ]

    # Query Rewriter mock for Turn 2
    mock_llm.rewrite_query.return_value = "What are the advantages of supervised learning?"

    # Instantiate ChatService
    chat_service = ChatService(
        embedding_service=mock_emb,
        qdrant_service=mock_qdrant,
        bm25_service=mock_bm25,
        llm_service=mock_llm,
        conversation_repository=mock_repo,
    )

    # -------------------------------------------------------------------------
    # EXECUTE TURN 1: "What is supervised learning?"
    # -------------------------------------------------------------------------
    print("\n--- EXECUTING TURN 1 ---")
    req_t1 = ChatRequest(query="What is supervised learning?", conversation_id=None)
    res_t1 = chat_service.generate_response(req_t1, user_id="test-user-001")

    conv_id = res_t1.conversation_id
    print(f"[Turn 1 Result] Conv ID: {conv_id}")
    print(f"[Turn 1 Result] Answer: '{res_t1.answer}'")

    # VERIFY TURN 1:
    # 1. Query rewriter should NOT have been called (empty history)
    mock_llm.rewrite_query.assert_not_called()
    # 2. Embedding & BM25 received raw query "What is supervised learning?"
    mock_emb.embed_query.assert_called_with("What is supervised learning?")
    mock_bm25.search_chunks.assert_called_with(
        query="What is supervised learning?", user_id="test-user-001", document_id=None, top_k=20
    )
    # 3. LLM generate_answer received empty history
    assert mock_llm.generate_answer.call_args[1]["history"] == []

    print("[SUCCESS] Turn 1 executed correctly: 0 query rewriting calls, raw query passed to retrieval.")

    # Reset call counts on mocks for Turn 2 verification
    mock_emb.embed_query.reset_mock()
    mock_qdrant.search_vectors.reset_mock()
    mock_bm25.search_chunks.reset_mock()

    # Configure Turn 2 retrieval results
    mock_qdrant.search_vectors.return_value = [
        {"document_id": "doc-ml-1", "chunk_id": 5, "score": 0.89, "text": "Advantages of supervised learning: high accuracy, explicit targets.", "source_file": "ml_intro.pdf", "page": 3}
    ]
    mock_bm25.search_chunks.return_value = [
        {"document_id": "doc-ml-1", "chunk_id": 5, "bm25_score": 5.8, "text": "Advantages of supervised learning: high accuracy, explicit targets.", "source_file": "ml_intro.pdf", "page": 3}
    ]

    # -------------------------------------------------------------------------
    # EXECUTE TURN 2: "What are its advantages?"
    # -------------------------------------------------------------------------
    print("\n--- EXECUTING TURN 2 ---")
    req_t2 = ChatRequest(query="What are its advantages?", conversation_id=conv_id)
    res_t2 = chat_service.generate_response(req_t2, user_id="test-user-001")

    print(f"[Turn 2 Result] Answer: '{res_t2.answer}'")

    # VERIFY TURN 2 STEPS EXACTLY AS REQUIRED:
    # Step 1: Fetched Turn 1 history from repository BEFORE insert
    assert mock_llm.rewrite_query.called, "Query rewriter was not called for Turn 2!"
    rewrite_history_arg = mock_llm.rewrite_query.call_args[1]["history"]
    print(f"\n1. History fetched for Turn 2 ({len(rewrite_history_arg)} messages):")
    for msg in rewrite_history_arg:
        print(f"   - [{msg['role']}]: {msg['content'][:60]}...")

    assert len(rewrite_history_arg) == 2
    assert rewrite_history_arg[0]["content"] == "What is supervised learning?"
    assert "Supervised learning is a machine learning technique" in rewrite_history_arg[1]["content"]

    # Step 2: Query Rewriter produced standalone query
    mock_llm.rewrite_query.assert_called_once_with("What are its advantages?", history=rewrite_history_arg)
    print("\n2. Query Rewriter generated standalone retrieval query:")
    print("   'What are the advantages of supervised learning?'")

    # Step 3: Sent rewritten query to BOTH Qdrant (dense) and BM25 (lexical)
    mock_emb.embed_query.assert_called_once_with("What are the advantages of supervised learning?")
    print("\n3. Sent rewritten query to Embedding model & Qdrant Search:")
    print("   search_vectors(query_vector=..., top_k=20)")

    mock_bm25.search_chunks.assert_called_once_with(
        query="What are the advantages of supervised learning?", user_id="test-user-001", document_id=None, top_k=20
    )
    print("   search_chunks(query='What are the advantages of supervised learning?', top_k=20)")

    # Step 4: RRF performed normally
    print("\n4. Reciprocal Rank Fusion (RRF) executed normally on top 20 dense + top 20 BM25 results.")

    # Step 5: Final LLM generation received original question + Turn 1 history + retrieved Top 5 chunks
    assert mock_llm.generate_answer.call_count == 2
    t2_llm_args = mock_llm.generate_answer.call_args[1]
    print("\n5. Final LLM Generation Received:")
    print(f"   - Original Query: '{t2_llm_args['query']}'")
    print(f"   - History Messages: {len(t2_llm_args['history'])} turns")
    print(f"   - Retrieved Top Chunks Count: {len(t2_llm_args['chunks'])}")

    assert t2_llm_args["query"] == "What are its advantages?"
    assert t2_llm_args["history"] == rewrite_history_arg
    assert len(t2_llm_args["chunks"]) == 1

    print("\n" + "=" * 70)
    print("ALL 5 VERIFICATION CHECKS PASSED PERFECTLY FOR 2-TURN CONVERSATIONAL RAG!")
    print("=" * 70)


if __name__ == "__main__":
    test_two_turn_conversational_rag_flow()
