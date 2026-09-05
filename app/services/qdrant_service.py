"""Qdrant service module for indexing document embeddings into Qdrant vector database."""

import json
import logging
from pathlib import Path
from typing import Any, Optional
import uuid

from qdrant_client import QdrantClient, models

from app.core.config import Settings, settings as default_settings
from app.schemas.embedding import EmbeddingDocument

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for indexing document vector embeddings into Qdrant vector database."""

    def __init__(
        self,
        client: Optional[QdrantClient] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize QdrantService with configuration and Qdrant client instance.

        Args:
            client: Optional pre-configured QdrantClient instance (useful for testing/mocking).
            settings: Optional Settings instance. Defaults to global application settings.

        Raises:
            ValueError: If settings parameters are invalid.
            RuntimeError: If Qdrant client initialization fails.
        """
        self.settings = settings or default_settings
        self._validate_settings()

        if client is not None:
            self.client = client
        else:
            try:
                self.client = QdrantClient(
                    url=self.settings.qdrant_url,
                    api_key=self.settings.qdrant_api_key,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to connect to Qdrant server at '{self.settings.qdrant_url}': {e}"
                ) from e

    def _validate_settings(self) -> None:
        """Validate Qdrant configuration parameters.

        Raises:
            ValueError: If any Qdrant settings parameter is invalid.
        """
        if not self.settings.qdrant_url or not isinstance(self.settings.qdrant_url, str):
            raise ValueError("qdrant_url must be a non-empty string.")
        if not self.settings.qdrant_collection_name or not isinstance(
            self.settings.qdrant_collection_name, str
        ):
            raise ValueError("qdrant_collection_name must be a non-empty string.")
        if self.settings.qdrant_batch_size <= 0:
            raise ValueError(
                f"qdrant_batch_size must be greater than 0, got {self.settings.qdrant_batch_size}"
            )

    def _load_embedding_document(self, embedding_json_path: Path) -> EmbeddingDocument:
        """Read, parse, and validate an embedding JSON document.

        Args:
            embedding_json_path: Path to the embedding JSON file.

        Returns:
            EmbeddingDocument: Validated EmbeddingDocument schema object.

        Raises:
            FileNotFoundError: If input file does not exist.
            ValueError: If JSON is invalid, schema validation fails, or embedding list is empty.
        """
        if not embedding_json_path.exists() or not embedding_json_path.is_file():
            raise FileNotFoundError(f"Embedding JSON file does not exist: {embedding_json_path}")

        logger.info("Loading embedding document from %s...", embedding_json_path)

        try:
            with open(embedding_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ValueError(f"Invalid JSON format in file {embedding_json_path}: {e}") from e

        try:
            embedding_doc = EmbeddingDocument.model_validate(data)
        except Exception as e:
            raise ValueError(
                f"Pydantic validation failed for EmbeddingDocument in {embedding_json_path}: {e}"
            ) from e

        if not embedding_doc.embeddings:
            raise ValueError(f"Embedding document contains no embeddings: {embedding_json_path}")

        logger.info(
            "Loaded embedding document '%s' with %d embeddings.",
            embedding_doc.document_id,
            len(embedding_doc.embeddings),
        )
        return embedding_doc

    def _ensure_collection_exists(self, vector_size: int = 768) -> None:
        """Ensure the target Qdrant collection exists and matches vector specifications.

        If the collection does not exist, it is created with the given vector dimension
        (default 768 for Gemini Embedding 2) and Cosine distance. If it already exists,
        its vector size and distance metric are validated.

        Args:
            vector_size: Vector dimension expected for the collection. Defaults to 768.

        Raises:
            ValueError: If existing collection vector dimension or distance metric mismatches.
            RuntimeError: If collection check or creation fails.
        """
        collection_name = self.settings.qdrant_collection_name

        try:
            exists = self.client.collection_exists(collection_name=collection_name)
        except Exception as e:
            raise RuntimeError(
                f"Failed to check Qdrant collection existence for '{collection_name}': {e}"
            ) from e

        if not exists:
            logger.info(
                "Collection '%s' does not exist. Creating new collection (size=%d, distance=Cosine)...",
                collection_name,
                vector_size,
            )
            try:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info("Successfully created Qdrant collection '%s'.", collection_name)
                try:
                    self.client.create_payload_index(
                        collection_name=collection_name,
                        field_name="user_id",
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )
                    self.client.create_payload_index(
                        collection_name=collection_name,
                        field_name="document_id",
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )
                except Exception as idx_err:
                    logger.warning("Could not create payload indexes on collection: %s", idx_err)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to create Qdrant collection '{collection_name}': {e}"
                ) from e
        else:
            logger.info(
                "Existing collection detected: '%s'. Validating parameters...", collection_name
            )
            try:
                info = self.client.get_collection(collection_name=collection_name)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to retrieve information for collection '{collection_name}': {e}"
                ) from e

            vectors_config = info.config.params.vectors
            existing_size: Optional[int] = None
            existing_distance: Optional[models.Distance] = None

            if isinstance(vectors_config, models.VectorParams):
                existing_size = vectors_config.size
                existing_distance = vectors_config.distance
            elif hasattr(vectors_config, "size"):
                existing_size = getattr(vectors_config, "size", None)
                existing_distance = getattr(vectors_config, "distance", None)

            if existing_size is not None and existing_size != vector_size:
                raise ValueError(
                    f"Collection '{collection_name}' vector dimension ({existing_size}) "
                    f"does not match document dimension ({vector_size})."
                )

            if existing_distance is not None and existing_distance != models.Distance.COSINE:
                raise ValueError(
                    f"Collection '{collection_name}' distance metric ({existing_distance}) "
                    f"does not match expected Cosine distance metric ({models.Distance.COSINE})."
                )

            logger.info(
                "Collection '%s' validation successful (dimension=%d, metric=Cosine).",
                collection_name,
                vector_size,
            )

    def _create_points(self, embedding_doc: EmbeddingDocument) -> list[models.PointStruct]:
        """Convert chunk embeddings into Qdrant PointStruct points with future-proof payload metadata.

        Args:
            embedding_doc: Input EmbeddingDocument schema object.

        Returns:
            list[models.PointStruct]: List of constructed Qdrant points.
        """
        points: list[models.PointStruct] = []

        for chunk_emb in embedding_doc.embeddings:
            payload: dict[str, Any] = {
                "user_id": embedding_doc.user_id,
                "document_id": embedding_doc.document_id,
                "chunk_id": chunk_emb.chunk_id,
                "page": chunk_emb.page,
                "text": chunk_emb.text,
                "source_file": embedding_doc.source_file,
                "model": embedding_doc.model,
            }

            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{embedding_doc.document_id}_{chunk_emb.chunk_id}"))

            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=chunk_emb.embedding,
                    payload=payload,
                )
            )

        logger.info(
            "Created %d Qdrant points for document '%s'.",
            len(points),
            embedding_doc.document_id,
        )
        return points

    def _batch_upsert(self, points: list[models.PointStruct]) -> None:
        """Upsert points into Qdrant in configurable batches.

        Args:
            points: List of Qdrant PointStruct objects to index.

        Raises:
            RuntimeError: If batch upsert request fails.
        """
        collection_name = self.settings.qdrant_collection_name
        batch_size = self.settings.qdrant_batch_size
        total_points = len(points)
        total_batches = (total_points + batch_size - 1) // batch_size

        logger.info(
            "Starting batch indexing of %d vectors into collection '%s' (batch_size=%d, total_batches=%d)...",
            total_points,
            collection_name,
            batch_size,
            total_batches,
        )

        for batch_num, i in enumerate(range(0, total_points, batch_size), start=1):
            batch = points[i : i + batch_size]
            logger.info(
                "Upserting batch %d/%d (%d points) into collection '%s'...",
                batch_num,
                total_batches,
                len(batch),
                collection_name,
            )
            try:
                self.client.upsert(
                    collection_name=collection_name,
                    points=batch,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to upsert batch {batch_num}/{total_batches} into collection '{collection_name}': {e}"
                ) from e

        logger.info(
            "Successfully indexed %d total vectors across %d batch(es) into collection '%s'.",
            total_points,
            total_batches,
            collection_name,
        )

    def index_document(self, embedding_json_path: Path) -> None:
        """Orchestrate loading, collection validation/creation, point generation, and batch indexing.

        Args:
            embedding_json_path: Path to the embedding JSON document.

        Raises:
            FileNotFoundError: If input file is missing.
            ValueError: If JSON/schema validation fails or collection settings mismatch.
            RuntimeError: If Qdrant communication or batch upsert fails.
        """
        embedding_doc = self._load_embedding_document(embedding_json_path)
        self._ensure_collection_exists(vector_size=embedding_doc.dimension)
        points = self._create_points(embedding_doc)
        self._batch_upsert(points)
        logger.info(
            "Completed indexing document '%s' successfully.",
            embedding_doc.document_id,
        )

    def search_vectors(
        self,
        query_vector: list[float],
        user_id: str,
        document_id: Optional[str] = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search Qdrant collection for vectors matching query, filtered by user_id and optional document_id.

        Args:
            query_vector: Dense embedding vector of the search query.
            user_id: Authenticated owner user ID for user isolation.
            document_id: Optional document ID filter.
            top_k: Maximum number of nearest results to return.

        Returns:
            list[dict[str, Any]]: List of payload dicts augmented with similarity 'score'.
        """
        collection_name = self.settings.qdrant_collection_name

        try:
            if not self.client.collection_exists(collection_name):
                logger.info("Collection '%s' does not exist in Qdrant.", collection_name)
                return []
        except Exception as e:
            logger.warning("Failed to check Qdrant collection existence: %s", e)
            return []

        must_conditions = [
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )
        ]

        if document_id:
            must_conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                )
            )

        query_filter = models.Filter(must=must_conditions)

        try:
            if hasattr(self.client, "search"):
                search_results = self.client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                )
            else:
                res = self.client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                )
                search_results = res.points
        except Exception as e:
            logger.error("Failed to execute search query in Qdrant: %s", e)
            raise RuntimeError(f"Qdrant vector search failed: {e}") from e

        results: list[dict[str, Any]] = []
        for point in search_results:
            payload = dict(point.payload or {})
            payload["score"] = float(point.score)
            results.append(payload)

        return results

