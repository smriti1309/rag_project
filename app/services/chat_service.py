"""Chat service module for user-isolated semantic retrieval, BM25 lexical search, RRF rank fusion, and grounded LLM answer generation."""

import logging
import time
from typing import Any, Optional

from app.core.config import Settings, settings as default_settings
from app.schemas.chat import ChatRequest, ChatResponse, SourceCitation
from app.services.bm25_service import BM25Service
from app.services.conversation_repository import ConversationRepository
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


class ChatService:
    """Service for orchestrating Hybrid RAG (Qdrant Dense + BM25 Lexical + RRF) and grounded AI answer generation."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        qdrant_service: Optional[QdrantService] = None,
        bm25_service: Optional[BM25Service] = None,
        llm_service: Optional[LLMService] = None,
        conversation_repository: Optional[ConversationRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize ChatService with dependencies.

        Args:
            embedding_service: Optional EmbeddingService instance.
            qdrant_service: Optional QdrantService instance.
            bm25_service: Optional BM25Service instance.
            llm_service: Optional LLMService instance.
            conversation_repository: Optional ConversationRepository instance.
            settings: Optional Settings instance.
        """
        self.settings = settings or default_settings
        self.embedding_service = embedding_service or EmbeddingService(settings=self.settings)
        self.qdrant_service = qdrant_service or QdrantService(settings=self.settings)
        self.bm25_service = bm25_service or BM25Service(settings=self.settings)
        self.llm_service = llm_service or LLMService(settings=self.settings)
        self.conversation_repository = conversation_repository or ConversationRepository(
            settings=self.settings
        )

    def _reciprocal_rank_fusion(
        self,
        dense_results: list[dict[str, Any]],
        bm25_results: list[dict[str, Any]],
        rrf_k: int = 60,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Combine dense and BM25 ranked result lists using Reciprocal Rank Fusion (RRF).

        Formula: rrf_score = sum(1.0 / (rrf_k + rank)) for 1-based ranks.

        Args:
            dense_results: List of candidate chunk dicts from Qdrant vector search.
            bm25_results: List of candidate chunk dicts from BM25 lexical search.
            rrf_k: Smoothing constant for RRF (default 60).
            top_k: Maximum number of fused chunks to return (default 5).

        Returns:
            list[dict[str, Any]]: Top k candidate chunks sorted by rrf_score descending.
        """
        fused_map: dict[tuple[str, int], dict[str, Any]] = {}

        # 1. Process dense vector search results (1-based rank)
        for rank, chunk in enumerate(dense_results, start=1):
            doc_id = str(chunk.get("document_id", ""))
            chunk_id = int(chunk.get("chunk_id", 0))
            key = (doc_id, chunk_id)
            rrf_contrib = 1.0 / (rrf_k + rank)

            if key not in fused_map:
                fused_item = dict(chunk)
                fused_item["score"] = float(chunk.get("score", 0.0))  # Dense cosine score
                fused_item["rrf_score"] = rrf_contrib
                fused_map[key] = fused_item
            else:
                fused_map[key]["rrf_score"] += rrf_contrib
                if "score" not in fused_map[key] or fused_map[key]["score"] == 0.0:
                    fused_map[key]["score"] = float(chunk.get("score", 0.0))

        # 2. Process BM25 lexical search results (1-based rank)
        for rank, chunk in enumerate(bm25_results, start=1):
            doc_id = str(chunk.get("document_id", ""))
            chunk_id = int(chunk.get("chunk_id", 0))
            key = (doc_id, chunk_id)
            rrf_contrib = 1.0 / (rrf_k + rank)

            if key not in fused_map:
                fused_item = dict(chunk)
                fused_item["bm25_score"] = float(chunk.get("bm25_score", 0.0))
                fused_item["rrf_score"] = rrf_contrib
                if "score" not in fused_item:
                    fused_item["score"] = 0.0
                fused_map[key] = fused_item
            else:
                fused_map[key]["rrf_score"] += rrf_contrib
                fused_map[key]["bm25_score"] = float(chunk.get("bm25_score", 0.0))

        fused_list = list(fused_map.values())
        fused_list.sort(key=lambda x: x["rrf_score"], reverse=True)
        return fused_list[:top_k]

    def generate_response(self, request: ChatRequest, user_id: str) -> ChatResponse:
        """Process user query through Hybrid RAG: Qdrant dense search, BM25 search, RRF fusion, and LLM generation.

        Args:
            request: ChatRequest schema containing query, top_k, document_id, and optional conversation_id.
            user_id: Authenticated user ID enforcing user isolation.

        Returns:
            ChatResponse: Query, grounded answer, source citations, chunk count, and retrieval time.
        """
        logger.info(
            "Starting Hybrid RAG pipeline for user '%s' (query='%s', doc_id=%s, conv_id=%s, top_k=%d)...",
            user_id,
            request.query,
            request.document_id,
            request.conversation_id,
            request.top_k,
        )

        effective_conv_id = request.conversation_id
        if effective_conv_id:
            conv = self.conversation_repository.get_conversation(user_id, effective_conv_id)
            if not conv:
                conv = self.conversation_repository.create_conversation(
                    user_id, title=request.query[:30]
                )
                effective_conv_id = conv["id"]
        else:
            conv = self.conversation_repository.create_conversation(
                user_id, title=request.query[:30]
            )
            effective_conv_id = conv["id"]

        # Fetch previous conversation history BEFORE inserting current user message
        history: list[dict[str, Any]] = []
        try:
            raw_history = self.conversation_repository.list_conversation_messages(
                user_id, effective_conv_id
            )
            if raw_history:
                history = raw_history[-6:]  # Take latest 6 messages (3 turns)
        except Exception as e:
            logger.warning(
                "Failed to fetch conversation history for user '%s' conv '%s': %s. Continuing with empty history.",
                user_id,
                effective_conv_id,
                e,
            )

        # Persist incoming user query message
        self.conversation_repository.insert_message(
            conversation_id=effective_conv_id,
            role="user",
            content=request.query,
        )

        t0 = time.perf_counter()

        candidate_k = self.settings.hybrid_candidate_k
        final_top_k = request.top_k if request.top_k != 5 else self.settings.hybrid_top_k

        # Step 0: Perform conversational query rewriting if history exists
        standalone_query = request.query
        if history:
            try:
                rewritten = self.llm_service.rewrite_query(request.query, history=history)
                if rewritten and rewritten.strip():
                    standalone_query = rewritten.strip()
                    logger.info("Rewrote conversational query into standalone query: '%s'", standalone_query)
            except Exception as e:
                logger.warning("Query rewriter encountered error: %s. Falling back to original query.", e)

        # Step 1: Generate vector embedding for the search query
        query_vector = self.embedding_service.embed_query(standalone_query)

        # Step 2: Perform dense vector search in Qdrant (Candidate Top 20)
        dense_results = self.qdrant_service.search_vectors(
            query_vector=query_vector,
            user_id=user_id,
            document_id=request.document_id,
            top_k=candidate_k,
        )

        # Step 3: Perform BM25 lexical search (Candidate Top 20)
        bm25_results = self.bm25_service.search_chunks(
            query=standalone_query,
            user_id=user_id,
            document_id=request.document_id,
            top_k=candidate_k,
        )

        # Step 4: Perform Reciprocal Rank Fusion (RRF) - NO pre-fusion cosine thresholding
        relevant_chunks = self._reciprocal_rank_fusion(
            dense_results=dense_results,
            bm25_results=bm25_results,
            rrf_k=self.settings.rrf_k,
            top_k=final_top_k,
        )

        retrieval_time_ms = int((time.perf_counter() - t0) * 1000)

        # Safety Check: If no chunks retrieved across both dense and BM25, return fallback answer
        if not relevant_chunks:
            logger.info(
                "Skipping LLM generation: 0 candidate chunks retrieved across dense and BM25."
            )
            fallback_answer = "I couldn't find any relevant information in your uploaded documents."
            self.conversation_repository.insert_message(
                conversation_id=effective_conv_id,
                role="assistant",
                content=fallback_answer,
                citations=None,
                retrieved_chunk_count=0,
                retrieval_time_ms=retrieval_time_ms,
            )
            return ChatResponse(
                query=request.query,
                answer=fallback_answer,
                conversation_id=effective_conv_id,
                sources=[],
                retrieved_chunk_count=0,
                retrieval_time_ms=retrieval_time_ms,
            )

        # Step 5: Invoke LLMService to generate grounded answer using fused top chunks
        answer = self.llm_service.generate_answer(
            query=request.query, chunks=relevant_chunks, history=history
        )

        # Step 6: Construct source citations preserving original Qdrant cosine score and retrieved chunk text
        sources = [
            SourceCitation(
                document_id=str(c.get("document_id", "")),
                chunk_id=int(c.get("chunk_id", 0)),
                page=c.get("page"),
                source_file=c.get("source_file"),
                score=float(c.get("score", 0.0)),
                text=c.get("text"),
            )
            for c in relevant_chunks
        ]

        citations_payload = [c.model_dump() for c in sources]

        # Persist assistant response message
        self.conversation_repository.insert_message(
            conversation_id=effective_conv_id,
            role="assistant",
            content=answer,
            citations=citations_payload,
            retrieved_chunk_count=len(sources),
            retrieval_time_ms=retrieval_time_ms,
        )

        logger.info(
            "Successfully generated grounded answer for user '%s' (%d source citations, retrieval=%dms).",
            user_id,
            len(sources),
            retrieval_time_ms,
        )

        return ChatResponse(
            query=request.query,
            answer=answer,
            conversation_id=effective_conv_id,
            sources=sources,
            retrieved_chunk_count=len(sources),
            retrieval_time_ms=retrieval_time_ms,
        )

    def retrieve_chunks(self, request: ChatRequest, user_id: str) -> ChatResponse:
        """Alias for generate_response maintaining backward compatibility."""
        return self.generate_response(request, user_id=user_id)


def generate_response(request: ChatRequest, user_id: str) -> ChatResponse:
    """Public convenience function to generate RAG response using default ChatService.

    Args:
        request: ChatRequest schema instance.
        user_id: Authenticated user ID.

    Returns:
        ChatResponse: Structured response with query, answer, citations, and metadata.
    """
    service = ChatService()
    return service.generate_response(request, user_id=user_id)


def retrieve_chunks(request: ChatRequest, user_id: str) -> ChatResponse:
    """Public convenience function alias for generate_response."""
    return generate_response(request, user_id=user_id)
