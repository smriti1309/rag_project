"""BM25 service module for persistent lexical document chunk indexing and search."""

import json
import logging
from pathlib import Path
import re
from typing import Any, Optional

from rank_bm25 import BM25Okapi

from app.core.config import Settings, settings as default_settings
from app.schemas.chunk import ChunkDocument

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Tokenize input text string into lowercase word tokens."""
    if not text:
        return []
    return re.findall(r"\w+", text.lower())


class BM25Service:
    """Service for indexing and searching document chunks using BM25 lexical relevance."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initialize BM25Service with application settings.

        Args:
            settings: Optional custom Settings instance. Defaults to global settings.
        """
        self.settings = settings or default_settings

    def index_document(self, chunk_json_path: Path) -> Path:
        """Read a ChunkDocument JSON artifact and generate a persistent BM25 JSON artifact.

        Args:
            chunk_json_path: Path to input ChunkDocument JSON file.

        Returns:
            Path: Path to the created BM25 JSON artifact file.

        Raises:
            FileNotFoundError: If input chunk JSON file is missing.
            ValueError: If input file contains invalid JSON or no chunks.
            OSError: If directory creation or file saving fails.
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
            raise ValueError(f"Schema validation failed for ChunkDocument in {chunk_json_path}: {e}") from e

        if not chunk_doc.chunks:
            raise ValueError(f"Chunk document contains no chunks: {chunk_json_path}")

        bm25_chunks: list[dict[str, Any]] = []
        for chunk in chunk_doc.chunks:
            bm25_chunks.append(
                {
                    "document_id": chunk_doc.document_id,
                    "user_id": chunk_doc.user_id,
                    "chunk_id": chunk.chunk_id,
                    "page": chunk.page,
                    "source_file": chunk_doc.source_file,
                    "text": chunk.text,
                    "tokens": _tokenize(chunk.text),
                }
            )

        bm25_doc = {
            "document_id": chunk_doc.document_id,
            "user_id": chunk_doc.user_id,
            "source_file": chunk_doc.source_file,
            "chunk_count": len(bm25_chunks),
            "chunks": bm25_chunks,
        }

        output_dir = self.settings.bm25_directory
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{chunk_doc.document_id}.bm25.json"

        try:
            output_path.write_text(json.dumps(bm25_doc, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            raise OSError(f"Failed to save BM25 artifact to '{output_path}': {e}") from e

        logger.info("Successfully indexed BM25 artifact for document '%s' (%d chunks).", chunk_doc.document_id, len(bm25_chunks))
        return output_path

    def _ensure_artifacts_synced(self) -> None:
        """Scan chunk_directory and ensure corresponding BM25 artifacts exist."""
        chunk_dir = self.settings.chunk_directory
        bm25_dir = self.settings.bm25_directory
        if not chunk_dir.exists():
            return

        bm25_dir.mkdir(parents=True, exist_ok=True)

        for chunk_file in chunk_dir.glob("*.json"):
            doc_id = chunk_file.stem
            bm25_file = bm25_dir / f"{doc_id}.bm25.json"
            if not bm25_file.exists():
                try:
                    logger.info("Rebuilding missing BM25 artifact for document '%s'...", doc_id)
                    self.index_document(chunk_file)
                except Exception as e:
                    logger.warning("Failed to auto-rebuild BM25 artifact for '%s': %s", doc_id, e)

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
            list[dict[str, Any]]: List of matching chunk dictionaries containing document_id,
                chunk_id, page, source_file, text, and bm25_score sorted by score descending.
        """
        if not query or not query.strip():
            return []

        if not user_id or not user_id.strip():
            return []

        self._ensure_artifacts_synced()

        bm25_dir = self.settings.bm25_directory
        if not bm25_dir.exists():
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        eligible_chunks: list[dict[str, Any]] = []

        for bm25_file in bm25_dir.glob("*.bm25.json"):
            try:
                with open(bm25_file, "r", encoding="utf-8") as f:
                    doc_data = json.load(f)
            except Exception as e:
                logger.warning("Failed to load BM25 artifact '%s': %s", bm25_file, e)
                continue

            # Fail-safe check at document level
            doc_user_id = doc_data.get("user_id")
            if doc_user_id != user_id:
                continue

            doc_id = doc_data.get("document_id")
            if document_id is not None and doc_id != document_id:
                continue

            for chunk in doc_data.get("chunks", []):
                # Fail-safe check at individual chunk metadata level
                chunk_user_id = chunk.get("user_id", doc_user_id)
                chunk_doc_id = chunk.get("document_id", doc_id)

                if chunk_user_id != user_id:
                    continue
                if document_id is not None and chunk_doc_id != document_id:
                    continue

                eligible_chunks.append(chunk)

        if not eligible_chunks:
            return []

        corpus_tokens = [c.get("tokens", []) for c in eligible_chunks]
        bm25 = BM25Okapi(corpus_tokens)
        scores = bm25.get_scores(query_tokens)

        scored_results: list[dict[str, Any]] = []
        for chunk, score in zip(eligible_chunks, scores):
            chunk_tokens_set = set(chunk.get("tokens", []))
            matched_count = sum(1 for t in query_tokens if t in chunk_tokens_set)
            if matched_count == 0:
                continue

            score_val = float(score)
            if score_val <= 0.0:
                score_val = float(matched_count * 0.1)

            scored_results.append(
                {
                    "document_id": chunk["document_id"],
                    "chunk_id": int(chunk["chunk_id"]),
                    "page": chunk.get("page"),
                    "source_file": chunk.get("source_file"),
                    "text": chunk["text"],
                    "bm25_score": score_val,
                }
            )

        scored_results.sort(key=lambda x: x["bm25_score"], reverse=True)
        return scored_results[:top_k]
