"""Unit tests for Chat RAG Hybrid Generation Service and API endpoint."""

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.schemas.chat import ChatRequest, ChatResponse, SourceCitation
from app.services.chat_service import ChatService


class TestChatService(unittest.TestCase):
    """Test suite for ChatService hybrid retrieval, RRF fusion, and /chat API endpoint."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        self.mock_embedding_service = MagicMock()
        self.mock_qdrant_service = MagicMock()
        self.mock_bm25_service = MagicMock()
        self.mock_llm_service = MagicMock()
        self.user_id = "user-test-12345"

    def test_generate_response_success(self) -> None:
        """Test successful end-to-end RAG answer generation using hybrid search."""
        self.mock_embedding_service.embed_query.return_value = [0.1, 0.2, 0.3]
        self.mock_qdrant_service.search_vectors.return_value = [
            {
                "document_id": "doc-abc-123",
                "chunk_id": 7,
                "page": 4,
                "source_file": "paper.pdf",
                "text": "Retrieval-Augmented Generation combines...",
                "score": 0.93,
            }
        ]
        self.mock_bm25_service.search_chunks.return_value = [
            {
                "document_id": "doc-abc-123",
                "chunk_id": 7,
                "page": 4,
                "source_file": "paper.pdf",
                "text": "Retrieval-Augmented Generation combines...",
                "bm25_score": 5.2,
            }
        ]
        self.mock_llm_service.generate_answer.return_value = (
            "RAG is a framework combining vector search with LLMs."
        )

        service = ChatService(
            embedding_service=self.mock_embedding_service,
            qdrant_service=self.mock_qdrant_service,
            bm25_service=self.mock_bm25_service,
            llm_service=self.mock_llm_service,
        )

        request = ChatRequest(query="What is RAG?", top_k=3)
        response = service.generate_response(request, user_id=self.user_id)

        self.assertIsInstance(response, ChatResponse)
        self.assertEqual(response.query, "What is RAG?")
        self.assertEqual(
            response.answer, "RAG is a framework combining vector search with LLMs."
        )
        self.assertEqual(len(response.sources), 1)
        self.assertEqual(response.retrieved_chunk_count, 1)

        source = response.sources[0]
        self.assertIsInstance(source, SourceCitation)
        self.assertEqual(source.document_id, "doc-abc-123")
        self.assertEqual(source.chunk_id, 7)
        self.assertEqual(source.page, 4)
        self.assertEqual(source.source_file, "paper.pdf")
        self.assertEqual(source.score, 0.93)
        self.assertEqual(source.text, "Retrieval-Augmented Generation combines...")

        self.mock_llm_service.generate_answer.assert_called_once()

    def test_rrf_rank_fusion_logic(self) -> None:
        """Test Reciprocal Rank Fusion combines ranks accurately and merges identical chunks."""
        dense_candidates = [
            {
                "document_id": "doc-1",
                "chunk_id": 101,
                "text": "Dense rank 1 text",
                "score": 0.85,
            },
            {
                "document_id": "doc-1",
                "chunk_id": 102,
                "text": "Dense rank 2 text",
                "score": 0.40,
            },
        ]
        bm25_candidates = [
            {
                "document_id": "doc-1",
                "chunk_id": 102,  # Present in both (Dense rank 2, BM25 rank 1)
                "text": "Dense rank 2 text",
                "bm25_score": 12.4,
            },
            {
                "document_id": "doc-2",
                "chunk_id": 201,  # BM25-only (BM25 rank 2)
                "text": "BM25 rank 2 text",
                "bm25_score": 9.1,
            },
        ]

        service = ChatService(
            embedding_service=self.mock_embedding_service,
            qdrant_service=self.mock_qdrant_service,
            bm25_service=self.mock_bm25_service,
            llm_service=self.mock_llm_service,
        )

        fused = service._reciprocal_rank_fusion(
            dense_results=dense_candidates,
            bm25_results=bm25_candidates,
            rrf_k=60,
            top_k=5,
        )

        self.assertEqual(len(fused), 3)

        # Chunk (doc-1, 102) gets contributions from Dense rank 2 (1/62) and BM25 rank 1 (1/61)
        expected_score_102 = (1.0 / 62.0) + (1.0 / 61.0)
        self.assertEqual(fused[0]["document_id"], "doc-1")
        self.assertEqual(fused[0]["chunk_id"], 102)
        self.assertAlmostEqual(fused[0]["rrf_score"], expected_score_102, places=6)
        self.assertEqual(fused[0]["score"], 0.40)
        self.assertEqual(fused[0]["bm25_score"], 12.4)

        # Chunk (doc-1, 101) gets Dense rank 1 (1/61)
        expected_score_101 = 1.0 / 61.0
        self.assertEqual(fused[1]["document_id"], "doc-1")
        self.assertEqual(fused[1]["chunk_id"], 101)
        self.assertAlmostEqual(fused[1]["rrf_score"], expected_score_101, places=6)

        # Chunk (doc-2, 201) gets BM25 rank 2 (1/62)
        expected_score_201 = 1.0 / 62.0
        self.assertEqual(fused[2]["document_id"], "doc-2")
        self.assertEqual(fused[2]["chunk_id"], 201)
        self.assertAlmostEqual(fused[2]["rrf_score"], expected_score_201, places=6)

    def test_dense_cosine_threshold_not_applied_before_fusion(self) -> None:
        """Test dense candidates with scores below min_similarity_score are retained and fused."""
        custom_settings = Settings(min_similarity_score=0.65)

        # Qdrant returns candidate with score 0.35 (below 0.65)
        self.mock_embedding_service.embed_query.return_value = [0.1, 0.2]
        self.mock_qdrant_service.search_vectors.return_value = [
            {
                "document_id": "doc-low",
                "chunk_id": 1,
                "text": "Low vector score text...",
                "score": 0.35,
            }
        ]
        # BM25 returns strong lexical match for the same chunk
        self.mock_bm25_service.search_chunks.return_value = [
            {
                "document_id": "doc-low",
                "chunk_id": 1,
                "text": "Low vector score text...",
                "bm25_score": 15.0,
            }
        ]
        self.mock_llm_service.generate_answer.return_value = "Grounded answer from fused context."

        service = ChatService(
            embedding_service=self.mock_embedding_service,
            qdrant_service=self.mock_qdrant_service,
            bm25_service=self.mock_bm25_service,
            llm_service=self.mock_llm_service,
            settings=custom_settings,
        )

        request = ChatRequest(query="Low score query", top_k=5)
        response = service.generate_response(request, user_id=self.user_id)

        # LLM MUST be called because candidate was retained and fused despite low cosine score
        self.assertEqual(response.answer, "Grounded answer from fused context.")
        self.assertEqual(len(response.sources), 1)
        self.assertEqual(response.sources[0].document_id, "doc-low")
        self.assertEqual(response.sources[0].score, 0.35)
        self.mock_llm_service.generate_answer.assert_called_once()

    def test_generate_response_zero_chunks_fallback(self) -> None:
        """Test zero chunks across both dense and BM25 returns fallback response safely."""
        self.mock_embedding_service.embed_query.return_value = [0.1, 0.2]
        self.mock_qdrant_service.search_vectors.return_value = []
        self.mock_bm25_service.search_chunks.return_value = []

        service = ChatService(
            embedding_service=self.mock_embedding_service,
            qdrant_service=self.mock_qdrant_service,
            bm25_service=self.mock_bm25_service,
            llm_service=self.mock_llm_service,
        )

        request = ChatRequest(query="Missing context query", top_k=5)
        response = service.generate_response(request, user_id=self.user_id)

        self.assertEqual(
            response.answer,
            "I couldn't find any relevant information in your uploaded documents.",
        )
        self.assertEqual(len(response.sources), 0)
        self.assertEqual(response.retrieved_chunk_count, 0)
        self.mock_llm_service.generate_answer.assert_not_called()

    @patch("app.api.chat.generate_response")
    def test_post_chat_api_endpoint_success(self, mock_generate: MagicMock) -> None:
        """Test POST /chat API endpoint returns expected ChatResponse payload structure."""
        mock_generate.return_value = ChatResponse(
            query="What is RAG?",
            answer="RAG is Retrieval Augmented Generation.",
            sources=[
                SourceCitation(
                    document_id="doc-123",
                    chunk_id=1,
                    page=1,
                    source_file="test.pdf",
                    score=0.95,
                )
            ],
            retrieved_chunk_count=1,
            retrieval_time_ms=12,
        )

        response = self.client.post(
            "/chat",
            json={"query": "What is RAG?"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["query"], "What is RAG?")
        self.assertEqual(data["answer"], "RAG is Retrieval Augmented Generation.")
        self.assertEqual(len(data["sources"]), 1)
        self.assertEqual(data["sources"][0]["document_id"], "doc-123")
        self.assertEqual(data["sources"][0]["score"], 0.95)
        self.assertEqual(data["retrieved_chunk_count"], 1)

    def test_post_chat_api_endpoint_validation_error(self) -> None:
        """Test POST /chat returns 422 for missing query."""
        response = self.client.post("/chat", json={})
        self.assertEqual(response.status_code, 422)

    def test_source_citation_includes_retrieved_text_and_preserves_rrf_order(self) -> None:
        """Test that generate_response populates text on SourceCitation and maintains exact RRF order."""
        self.mock_embedding_service.embed_query.return_value = [0.1, 0.2]
        self.mock_qdrant_service.search_vectors.return_value = [
            {
                "document_id": "doc-A",
                "chunk_id": 1,
                "page": 2,
                "source_file": "docA.pdf",
                "text": "Chunk text from Document A page 2",
                "score": 0.88,
            },
            {
                "document_id": "doc-B",
                "chunk_id": 5,
                "page": 7,
                "source_file": "docB.pdf",
                "text": "Chunk text from Document B page 7",
                "score": 0.75,
            },
        ]
        self.mock_bm25_service.search_chunks.return_value = []
        self.mock_llm_service.generate_answer.return_value = "Answer grounded in doc A and B."

        service = ChatService(
            embedding_service=self.mock_embedding_service,
            qdrant_service=self.mock_qdrant_service,
            bm25_service=self.mock_bm25_service,
            llm_service=self.mock_llm_service,
        )

        request = ChatRequest(query="Multi doc query", top_k=2)
        response = service.generate_response(request, user_id=self.user_id)

        self.assertEqual(len(response.sources), 2)
        # Verify RRF order preserved (doc-A first, doc-B second)
        self.assertEqual(response.sources[0].document_id, "doc-A")
        self.assertEqual(response.sources[0].text, "Chunk text from Document A page 2")

        self.assertEqual(response.sources[1].document_id, "doc-B")
        self.assertEqual(response.sources[1].text, "Chunk text from Document B page 7")


if __name__ == "__main__":
    unittest.main()
