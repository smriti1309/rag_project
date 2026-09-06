"""BM25 service module for persistent lexical document chunk indexing and search using Supabase DB + in-memory caching."""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Optional

from rank_bm25 import BM25Okapi

from app.core.config import Settings, settings as default_settings
from app.schemas.chunk import ChunkDocument
from app.services.document_repository import DocumentRepository

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Tokenize input text string into lowercase word tokens."""
    if not text:
        return []
    return re.findall(r"\w+", text.lower())


@dataclass
class UserBM25Cache:
    """In-memory cache entry for a user's BM25 index."""

    watermark: tuple[Optional[str], int]
    bm25: BM25Okapi
    chunks: list[dict[str, Any]]
    chunk_tokens: list[list[str]]
    last_accessed: float


class BM25Service:
    """Service for indexing and searching document chunks using persistent Supabase DB and in-memory BM25Okapi cache."""

    _user_caches: dict[str, UserBM25Cache] = {}
    MAX_CACHE_ENTRIES: int = 200
    CACHE_TTL_SECONDS: float = 1800.0  # 30 minutes

    def __init__(
        self,
        document_repository: Optional[DocumentRepository] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize BM25Service.

        Args:
            document_repository: Optional DocumentRepository instance.
            settings: Optional custom Settings instance.
        """
        self.settings = settings or default_settings
        self.document_repository = document_repository or DocumentRepository(
            settings=self.settings
        )

    def invalidate_user_cache(self, user_id: str) -> None:
        """Purge the in-memory BM25 cache entry for user_id."""
        if user_id in BM25Service._user_caches:
            del BM25Service._user_caches[user_id]
            logger.debug("Invalidated BM25 in-memory cache for user '%s'.", user_id)

    def _evict_lru_caches_if_needed(self) -> None:
        """Evict oldest or expired cache entries to bound memory usage."""
        now = time.time()
        # Evict expired entries
        expired_keys = [
            uid
            for uid, entry in BM25Service._user_caches.items()
            if now - entry.last_accessed > self.CACHE_TTL_SECONDS
        ]
        for uid in expired_keys:
            del BM25Service._user_caches[uid]

        # Evict LRU entries if still over max capacity
        if len(BM25Service._user_caches) >= self.MAX_CACHE_ENTRIES:
            sorted_entries = sorted(
                BM25Service._user_caches.items(), key=lambda item: item[1].last_accessed
            )
            to_remove = len(BM25Service._user_caches) - self.MAX_CACHE_ENTRIES + 1
            for uid, _ in sorted_entries[:to_remove]:
                del BM25Service._user_caches[uid]

    def _get_or_build_user_cache(self, user_id: str) -> Optional[UserBM25Cache]:
        """Fetch user's in-memory BM25 index, validating watermark against PostgreSQL.

        Args:
            user_id: Authenticated user ID.

        Returns:
            UserBM25Cache or None: Cache entry containing BM25Okapi instance and chunks.
        """
        now = time.time()
        current_watermark = self.document_repository.get_user_watermark(user_id)

        cached_entry = BM25Service._user_caches.get(user_id)
        if cached_entry:
            if cached_entry.watermark == current_watermark:
                cached_entry.last_accessed = now
                return cached_entry
            else:
                logger.info(
                    "BM25 watermark changed for user '%s' (old=%s, new=%s). Rebuilding index...",
                    user_id,
                    cached_entry.watermark,
                    current_watermark,
                )

        # Build index from database chunks
        chunks = self.document_repository.get_user_chunks(user_id)
        if not chunks:
            self.invalidate_user_cache(user_id)
            return None

        chunk_tokens = [_tokenize(c.get("text", "")) for c in chunks]
        bm25 = BM25Okapi(chunk_tokens)

        self._evict_lru_caches_if_needed()
        new_entry = UserBM25Cache(
            watermark=current_watermark,
            bm25=bm25,
            chunks=chunks,
            chunk_tokens=chunk_tokens,
            last_accessed=now,
        )
        BM25Service._user_caches[user_id] = new_entry
        logger.info(
            "Built new in-memory BM25 index for user '%s' (%d chunks, watermark=%s).",
            user_id,
            len(chunks),
            current_watermark,
        )
        return new_entry

    def index_chunks(
        self,
        document_id: str,
        user_id: str,
        source_file: str,
        chunks: list[dict[str, Any]],
    ) -> bool:
        """Persist chunk text records into Supabase PostgreSQL and invalidate in-memory cache.

        Args:
            document_id: Document UUID.
            user_id: Authenticated user ID.
            source_file: Original filename.
            chunks: List of chunk dictionaries containing chunk_id, page, text, etc.

        Returns:
            bool: True if chunks were persisted successfully.
        """
        if not chunks:
            return True

        chunks_payload: list[dict[str, Any]] = []
        for c in chunks:
            chunk_id = int(c.get("chunk_id", 0))
            page = c.get("page")
            text = c.get("text", "")
            chunks_payload.append(
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "chunk_id": chunk_id,
                    "page": page,
                    "source_file": source_file,
                    "text": text,
                }
            )

        success = self.document_repository.insert_document_chunks(chunks_payload)
        self.invalidate_user_cache(user_id)
        logger.info(
            "Persisted %d chunks for document '%s' and invalidated BM25 cache for user '%s'.",
            len(chunks_payload),
            document_id,
            user_id,
        )
        return success

    def index_document(self, chunk_json_path: Path) -> Path:
        """Read a ChunkDocument JSON file, persist chunks into Supabase DB, and invalidate cache.

        Args:
            chunk_json_path: Path to ChunkDocument JSON artifact.

        Returns:
            Path: Input chunk_json_path for backward compatibility.
        """
        if not chunk_json_path.exists() or not chunk_json_path.is_file():
            raise FileNotFoundError(f"Chunk JSON file does not exist: {chunk_json_path}")

        try:
            with open(chunk_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ValueError(f"Invalid JSON format in file {chunk_json_path}: {e}") from e

        try:
            chunk_doc = ChunkDocument.model_validate(data)
        except Exception as e:
            raise ValueError(
                f"Schema validation failed for ChunkDocument in {chunk_json_path}: {e}"
            ) from e

        if not chunk_doc.chunks:
            raise ValueError(f"Chunk document contains no chunks: {chunk_json_path}")

        raw_chunks = [c.model_dump() for c in chunk_doc.chunks]
        self.index_chunks(
            document_id=chunk_doc.document_id,
            user_id=chunk_doc.user_id,
            source_file=chunk_doc.source_file,
            chunks=raw_chunks,
        )
        return chunk_json_path

    def search_chunks(
        self,
        query: str,
        user_id: str,
        document_id: Optional[str] = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Search BM25 lexical index for candidate chunks matching query with fail-safe user isolation.

        Args:
            query: User search query text string.
            user_id: Authenticated user ID enforcing user isolation.
            document_id: Optional document ID filter.
            top_k: Maximum number of relevant chunks to return. Defaults to 20.

        Returns:
            list[dict[str, Any]]: Candidate chunk dictionaries containing document_id,
                chunk_id, page, source_file, text, and bm25_score sorted by score descending.
        """
        if not query or not query.strip():
            return []

        if not user_id or not user_id.strip():
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        cache_entry = self._get_or_build_user_cache(user_id)
        if not cache_entry:
            return []

        # Calculate BM25 scores across user's cached index
        scores = cache_entry.bm25.get_scores(query_tokens)

        scored_results: list[dict[str, Any]] = []
        query_token_set = set(query_tokens)

        for chunk, tokens, score in zip(
            cache_entry.chunks, cache_entry.chunk_tokens, scores
        ):
            chunk_doc_id = str(chunk.get("document_id", ""))
            if document_id is not None and chunk_doc_id != document_id:
                continue

            chunk_token_set = set(tokens)
            matched_count = len(query_token_set.intersection(chunk_token_set))
            if matched_count == 0:
                continue

            score_val = float(score)
            if score_val <= 0.0:
                score_val = float(matched_count * 0.1)

            scored_results.append(
                {
                    "document_id": chunk_doc_id,
                    "chunk_id": int(chunk.get("chunk_id", 0)),
                    "page": chunk.get("page"),
                    "source_file": chunk.get("source_file"),
                    "text": chunk.get("text", ""),
                    "bm25_score": score_val,
                }
            )

        scored_results.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored_results[:top_k]
