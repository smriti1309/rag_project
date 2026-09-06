"""Embedding service module for generating vector embeddings using Google Gemini API."""

import json
from pathlib import Path
import time
from typing import Optional

from google import genai
from google.genai import types

from app.core.config import Settings, settings as default_settings
from app.schemas.chunk import ChunkDocument
from app.schemas.embedding import ChunkEmbedding, EmbeddingDocument


class EmbeddingService:
    """Service for generating vector embeddings for text document chunks using Google Gemini API."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initialize EmbeddingService with configuration and Google GenAI client.

        Args:
            settings: Optional custom Settings instance. Defaults to application settings.

        Raises:
            ValueError: If settings validation fails or GenAI client initialization fails.
        """
        self.settings = settings or default_settings
        self._validate_settings()

        try:
            self.client = genai.Client(api_key=self.settings.gemini_api_key)
        except Exception as e:
            raise ValueError(
                f"Failed to initialize Google GenAI Client: {e}"
            ) from e

    def _validate_settings(self) -> None:
        """Validate embedding configuration parameters.

        Raises:
            ValueError: If embedding settings parameters are invalid.
        """
        if not self.settings.embedding_model or not isinstance(self.settings.embedding_model, str):
            raise ValueError("embedding_model must be a non-empty string.")
        if self.settings.embedding_batch_size <= 0:
            raise ValueError(
                f"embedding_batch_size must be greater than 0, got {self.settings.embedding_batch_size}"
            )

    def _load_chunk_document(self, chunk_json_path: Path) -> ChunkDocument:
        """Verify existence of, load, and validate chunk JSON document.

        Args:
            chunk_json_path: Path to input chunk JSON file.

        Returns:
            ChunkDocument: Validated ChunkDocument schema object.

        Raises:
            FileNotFoundError: If input file is missing.
            ValueError: If JSON is invalid, schema validation fails, or chunk list is empty.
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
                f"Pydantic validation failed for ChunkDocument in {chunk_json_path}: {e}"
            ) from e

        if not chunk_doc.chunks:
            raise ValueError(f"Chunk document contains no chunks: {chunk_json_path}")

        return chunk_doc

    def _extract_texts(self, chunk_doc: ChunkDocument) -> list[str]:
        """Extract text content from every chunk in a ChunkDocument.

        Args:
            chunk_doc: Input ChunkDocument schema object.

        Returns:
            list[str]: List of chunk text strings.
        """
        return [chunk.text for chunk in chunk_doc.chunks]

    def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate 768D vector embeddings for a list of text strings using Gemini API in batches.

        Args:
            texts: List of text strings to embed.

        Returns:
            list[list[float]]: Nested list of 768D float embedding vectors in exact input order.

        Raises:
            ValueError: If texts list is empty.
            RuntimeError: If embedding encoding fails or batch response count mismatches.
        """
        if not texts:
            raise ValueError("No text found for embedding generation.")

        batch_size = self.settings.embedding_batch_size
        embeddings: list[list[float]] = []

        try:
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i : i + batch_size]
                for attempt in range(1, 6):
                    try:
                        response = self.client.models.embed_content(
                            model=self.settings.embedding_model,
                            contents=[[text] for text in batch_texts],
                            config=types.EmbedContentConfig(
                                output_dimensionality=768,
                                task_type="RETRIEVAL_DOCUMENT",
                            ),
                        )
                        if not response or not hasattr(response, "embeddings") or not response.embeddings:
                            raise ValueError(f"Batch embedding returned no embeddings for batch of size {len(batch_texts)}.")
                        if len(response.embeddings) != len(batch_texts):
                            raise ValueError(
                                f"Batch embedding count mismatch: expected {len(batch_texts)}, got {len(response.embeddings)}"
                            )
                        for emb in response.embeddings:
                            embeddings.append(emb.values)
                        break
                    except Exception as err:
                        if ("429" in str(err) or "RESOURCE_EXHAUSTED" in str(err)) and attempt < 5:
                            time.sleep(attempt * 3)
                        else:
                            raise err
            return embeddings
        except Exception as e:
            raise RuntimeError(f"Gemini document embedding generation failed: {e}") from e

    def embed_query(self, query: str) -> list[float]:
        """Generate 768D vector embedding for a single text query string using Gemini API.

        Args:
            query: The user query text string to embed.

        Returns:
            list[float]: 768D vector embedding representation for the query.

        Raises:
            ValueError: If query is empty or whitespace.
            RuntimeError: If embedding API call fails.
        """
        if not query or not query.strip():
            raise ValueError("Query string cannot be empty.")

        try:
            response = self.client.models.embed_content(
                model=self.settings.embedding_model,
                contents=query,
                config=types.EmbedContentConfig(
                    output_dimensionality=768,
                    task_type="RETRIEVAL_QUERY",
                ),
            )
            return response.embeddings[0].values
        except Exception as e:
            raise RuntimeError(f"Gemini query embedding generation failed: {e}") from e

    def _create_embedding_document(
        self,
        chunk_doc: ChunkDocument,
        embeddings: list[list[float]],
        user_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_file: Optional[str] = None,
    ) -> EmbeddingDocument:
        """Associate chunks with their generated embeddings into an EmbeddingDocument.

        Args:
            chunk_doc: Original ChunkDocument schema object.
            embeddings: List of embedding vectors matching chunk order.
            user_id: Optional authenticated user ID.
            document_id: Optional document identifier (UUID).
            source_file: Optional original uploaded filename.

        Returns:
            EmbeddingDocument: Constructed EmbeddingDocument schema object.

        Raises:
            ValueError: If chunk count and embedding count do not match.
        """
        if len(chunk_doc.chunks) != len(embeddings):
            raise ValueError("Embedding count does not match chunk count.")

        chunk_embeddings = [
            ChunkEmbedding(
                chunk_id=chunk.chunk_id,
                page=chunk.page,
                text=chunk.text,
                embedding=emb,
            )
            for chunk, emb in zip(chunk_doc.chunks, embeddings)
        ]

        dimension = len(embeddings[0]) if embeddings else 0

        effective_user_id = user_id or getattr(chunk_doc, "user_id", None)
        effective_doc_id = document_id or chunk_doc.document_id
        effective_source_file = source_file or getattr(chunk_doc, "source_file", None)

        return EmbeddingDocument(
            document_id=effective_doc_id,
            user_id=effective_user_id,
            source_file=effective_source_file,
            model=self.settings.embedding_model,
            dimension=dimension,
            embeddings=chunk_embeddings,
        )

    def _save_embeddings(self, embedding_doc: EmbeddingDocument) -> Path:
        """Save EmbeddingDocument model as a JSON file in the configured embedding_directory.

        Args:
            embedding_doc: EmbeddingDocument schema object to serialize.

        Returns:
            Path: Path to the generated embeddings JSON output file.

        Raises:
            OSError: If output directory creation or file writing fails.
        """
        try:
            output_dir = self.settings.embedding_directory
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise OSError(f"Failed to create output directory '{self.settings.embedding_directory}': {e}") from e

        output_path = output_dir / f"{embedding_doc.document_id}.embeddings.json"

        try:
            output_path.write_text(embedding_doc.model_dump_json(indent=2), encoding="utf-8")
        except Exception as e:
            raise OSError(f"Failed to save embeddings to file '{output_path}': {e}") from e

        return output_path

    def embed_document(
        self,
        chunk_json_path: Path,
        user_id: Optional[str] = None,
        document_id: Optional[str] = None,
        source_file: Optional[str] = None,
    ) -> Path:
        """Process a chunk JSON file into embeddings and save output.

        Args:
            chunk_json_path: Path to input chunk JSON file.
            user_id: Optional authenticated user ID.
            document_id: Optional document identifier (UUID).
            source_file: Optional original uploaded filename.

        Returns:
            Path: Path to generated output embeddings JSON file.

        Raises:
            FileNotFoundError: If input file is missing.
            ValueError: If JSON/chunk validation fails.
            RuntimeError: If embedding generation fails.
            OSError: If file output fails.
        """
        chunk_doc = self._load_chunk_document(chunk_json_path)
        texts = self._extract_texts(chunk_doc)
        embeddings = self._generate_embeddings(texts)
        embedding_doc = self._create_embedding_document(
            chunk_doc,
            embeddings,
            user_id=user_id,
            document_id=document_id,
            source_file=source_file,
        )
        return self._save_embeddings(embedding_doc)


def embed_document(
    chunk_json_path: Path,
    user_id: Optional[str] = None,
    document_id: Optional[str] = None,
    source_file: Optional[str] = None,
) -> Path:
    """Public convenience function to embed a document using default application settings.

    Args:
        chunk_json_path: Path to input chunk JSON file.
        user_id: Optional authenticated user ID.
        document_id: Optional document identifier (UUID).
        source_file: Optional original uploaded filename.

    Returns:
        Path: Path to output embeddings JSON file.
    """
    service = EmbeddingService()
    return service.embed_document(
        chunk_json_path, user_id=user_id, document_id=document_id, source_file=source_file
    )
