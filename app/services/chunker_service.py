"""Chunker service module for semantic text document chunking."""

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Optional

from app.core.config import Settings, settings as default_settings
from app.schemas.chunk import Chunk, ChunkDocument
from app.services.embedding_service import EmbeddingService


@dataclass
class ParagraphUnit:
    """Internal data structure representing an atomic text unit for chunking."""

    start_char: int
    end_char: int
    text: str
    page: Optional[int]
    word_count: int


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class ChunkerService:
    """Service for splitting plain text documents into semantic JSON chunks."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize ChunkerService with optional embedding service and settings.

        Args:
            embedding_service: Optional EmbeddingService instance for semantic boundary detection.
            settings: Settings instance. Defaults to application global settings.
        """
        self.settings = settings or default_settings
        self.embedding_service = embedding_service
        if self.embedding_service is None and getattr(self.settings, "gemini_api_key", None):
            try:
                self.embedding_service = EmbeddingService(settings=self.settings)
            except Exception:
                self.embedding_service = None

        self._validate_settings()

    def _validate_settings(self) -> None:
        """Validate chunking configuration parameters.

        Raises:
            ValueError: If chunk configuration settings are invalid.
        """
        max_words = getattr(
            self.settings, "semantic_chunk_max_words", self.settings.chunk_max_words
        )
        min_words = getattr(self.settings, "semantic_chunk_min_words", 50)
        threshold = getattr(self.settings, "semantic_similarity_threshold", 0.75)

        if max_words <= 0:
            raise ValueError(
                f"semantic_chunk_max_words must be greater than 0, got {max_words}"
            )
        if min_words <= 0:
            raise ValueError(
                f"semantic_chunk_min_words must be greater than 0, got {min_words}"
            )
        if min_words > max_words:
            min_words = max_words
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(
                f"semantic_similarity_threshold must be between 0.0 and 1.0, got {threshold}"
            )
        if self.settings.chunk_overlap < 0:
            raise ValueError(
                f"chunk_overlap must be non-negative, got {self.settings.chunk_overlap}"
            )
        target_words = getattr(self.settings, "semantic_candidate_group_target_words", 150)
        if target_words <= 0:
            raise ValueError(
                f"semantic_candidate_group_target_words must be greater than 0, got {target_words}"
            )

    def _read_document(self, txt_path: Path) -> str:
        """Read and validate the contents of a text file."""
        if not txt_path.exists() or not txt_path.is_file():
            raise FileNotFoundError(f"Document file does not exist: {txt_path}")

        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            raise ValueError(f"Document is empty: {txt_path}")

        return content

    def _split_paragraphs(self, text: str) -> list[ParagraphUnit]:
        """Split document text into paragraph units while parsing page markers."""
        paragraph_units: list[ParagraphUnit] = []
        current_page: Optional[int] = None

        block_pattern = re.compile(r"[^\r\n]+(?:\r?\n[^\r\n]+)*")
        page_marker_pattern = re.compile(r"^\s*=====\s*PAGE\s*(\d+)\s*=====\s*$")

        for match in block_pattern.finditer(text):
            raw_start = match.start()
            raw_end = match.end()
            block_text = match.group(0)

            lines = block_text.splitlines()
            if lines:
                marker_match = page_marker_pattern.match(lines[0])
                if marker_match:
                    current_page = int(marker_match.group(1))
                    if len(lines) == 1:
                        continue
                    header_len = len(lines[0])
                    if len(block_text) > header_len and block_text[header_len] in ("\r", "\n"):
                        if (
                            block_text[header_len] == "\r"
                            and len(block_text) > header_len + 1
                            and block_text[header_len + 1] == "\n"
                        ):
                            header_len += 2
                        else:
                            header_len += 1

                    raw_start += header_len
                    block_text = text[raw_start:raw_end]

            p_text = block_text.strip()
            if not p_text:
                continue

            l_strip = len(block_text) - len(block_text.lstrip())
            t_strip = len(block_text) - len(block_text.rstrip())
            p_start = raw_start + l_strip
            p_end = raw_end - t_strip
            actual_text = text[p_start:p_end]

            words = len(actual_text.split())
            paragraph_units.append(
                ParagraphUnit(
                    start_char=p_start,
                    end_char=p_end,
                    text=actual_text,
                    page=current_page,
                    word_count=words,
                )
            )

        return paragraph_units

    def _split_large_paragraph(
        self, paragraph: ParagraphUnit, full_text: str
    ) -> list[ParagraphUnit]:
        """Split an oversized paragraph into smaller units using sentence and word boundaries."""
        max_words = getattr(
            self.settings, "semantic_chunk_max_words", self.settings.chunk_max_words
        )
        if paragraph.word_count <= max_words:
            return [paragraph]

        atomic_units: list[ParagraphUnit] = []
        p_text = paragraph.text
        p_start = paragraph.start_char

        sentence_pattern = re.compile(r"\S.*?(?:[.!?](?=\s|$)|$)", re.DOTALL)

        for s_match in sentence_pattern.finditer(p_text):
            s_start = p_start + s_match.start()
            s_end = p_start + s_match.end()
            s_text = full_text[s_start:s_end]
            s_words = len(s_text.split())

            if not s_text.strip():
                continue

            if s_words <= max_words:
                atomic_units.append(
                    ParagraphUnit(
                        start_char=s_start,
                        end_char=s_end,
                        text=s_text,
                        page=paragraph.page,
                        word_count=s_words,
                    )
                )
            else:
                word_pattern = re.compile(r"\S+")
                words_matches = list(word_pattern.finditer(s_text))

                for i in range(0, len(words_matches), max_words):
                    group = words_matches[i : i + max_words]
                    w_start = s_start + group[0].start()
                    w_end = s_start + group[-1].end()
                    w_text = full_text[w_start:w_end]
                    w_words = len(w_text.split())

                    atomic_units.append(
                        ParagraphUnit(
                            start_char=w_start,
                            end_char=w_end,
                            text=w_text,
                            page=paragraph.page,
                            word_count=w_words,
                        )
                    )

        grouped_units: list[ParagraphUnit] = []
        curr_sub_units: list[ParagraphUnit] = []
        curr_sub_words = 0

        for unit in atomic_units:
            if curr_sub_units and (curr_sub_words + unit.word_count > max_words):
                g_start = curr_sub_units[0].start_char
                g_end = curr_sub_units[-1].end_char
                g_text = full_text[g_start:g_end]
                grouped_units.append(
                    ParagraphUnit(
                        start_char=g_start,
                        end_char=g_end,
                        text=g_text,
                        page=paragraph.page,
                        word_count=len(g_text.split()),
                    )
                )
                curr_sub_units = []
                curr_sub_words = 0

            curr_sub_units.append(unit)
            curr_sub_words += unit.word_count

        if curr_sub_units:
            g_start = curr_sub_units[0].start_char
            g_end = curr_sub_units[-1].end_char
            g_text = full_text[g_start:g_end]
            grouped_units.append(
                ParagraphUnit(
                    start_char=g_start,
                    end_char=g_end,
                    text=g_text,
                    page=paragraph.page,
                    word_count=len(g_text.split()),
                )
            )

        return grouped_units

    def _get_paragraph_embeddings(self, units: list[ParagraphUnit]) -> Optional[list[list[float]]]:
        """Generate 768D vector embeddings for candidate paragraph units using embedding service.

        Args:
            units: List of candidate ParagraphUnit objects.

        Returns:
            Optional[list[list[float]]]: List of 768D embedding vectors matching input units order,
                or None if embedding service is unavailable/unconfigured.
        """
        if not self.embedding_service or not units:
            return None

        texts = [u.text for u in units]
        try:
            return self.embedding_service._generate_embeddings(texts)
        except Exception:
            return None

    def _make_chunk(
        self, chunk_id: int, units: list[ParagraphUnit], full_text: str
    ) -> Chunk:
        """Construct a Chunk schema model from a list of ParagraphUnits."""
        c_start = units[0].start_char
        c_end = units[-1].end_char
        c_text = full_text[c_start:c_end]
        return Chunk(
            chunk_id=chunk_id,
            page=units[0].page,
            start_char=c_start,
            end_char=c_end,
            text=c_text,
        )

    def _build_semantic_chunks(
        self,
        units: list[ParagraphUnit],
        full_text: str,
        unit_embeddings: Optional[list[list[float]]] = None,
    ) -> list[Chunk]:
        """Build semantic chunks enforcing MAX SIZE > SEMANTIC BOUNDARY > MIN SIZE priority hierarchy."""
        if not units:
            return []

        max_words = getattr(
            self.settings, "semantic_chunk_max_words", self.settings.chunk_max_words
        )
        min_words = getattr(self.settings, "semantic_chunk_min_words", 50)
        threshold = getattr(self.settings, "semantic_similarity_threshold", 0.75)

        chunks: list[Chunk] = []
        current_units: list[ParagraphUnit] = []
        current_words = 0

        for i, unit in enumerate(units):
            if not current_units:
                current_units.append(unit)
                current_words = unit.word_count
                continue

            prev_unit = current_units[-1]

            sim: Optional[float] = None
            if (
                unit_embeddings
                and i < len(unit_embeddings)
                and (i - 1) < len(unit_embeddings)
            ):
                sim = cosine_similarity(unit_embeddings[i - 1], unit_embeddings[i])

            # 1. HARD MAX SIZE RULE (HIGHEST PRIORITY)
            if current_words + unit.word_count > max_words:
                chunks.append(self._make_chunk(len(chunks) + 1, current_units, full_text))
                current_units = [unit]
                current_words = unit.word_count

            # 2. SEMANTIC BOUNDARY RULE
            elif sim is not None and sim < threshold:
                if current_words >= min_words:
                    chunks.append(self._make_chunk(len(chunks) + 1, current_units, full_text))
                    current_units = [unit]
                    current_words = unit.word_count
                else:
                    # Soft preference: current_words < min_words -> Merge unit to prevent micro-chunks
                    current_units.append(unit)
                    current_words += unit.word_count

            # 3. DEFAULT MERGE (Same topic & within max size bounds)
            else:
                current_units.append(unit)
                current_words += unit.word_count

        if current_units:
            chunks.append(self._make_chunk(len(chunks) + 1, current_units, full_text))

        return chunks

    def _save_chunks(self, chunk_doc: ChunkDocument) -> Path:
        """Save ChunkDocument model as a JSON file in the configured chunk_directory."""
        output_dir = self.settings.chunk_directory
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{chunk_doc.document_id}.json"
        output_path.write_text(chunk_doc.model_dump_json(indent=2), encoding="utf-8")

        return output_path

    def _group_candidate_units(
        self, units: list[ParagraphUnit], full_text: str
    ) -> list[ParagraphUnit]:
        """Pre-group consecutive short paragraph units into candidate units targeting target_words.

        Args:
            units: List of atomic ParagraphUnit objects.
            full_text: Complete document text.

        Returns:
            list[ParagraphUnit]: List of candidate ParagraphUnit objects.
        """
        if not units:
            return []

        target_words = getattr(
            self.settings, "semantic_candidate_group_target_words", 150
        )
        max_words = getattr(
            self.settings, "semantic_chunk_max_words", self.settings.chunk_max_words
        )
        target = min(target_words, max_words)

        candidate_units: list[ParagraphUnit] = []
        current_group: list[ParagraphUnit] = []
        current_words = 0

        for unit in units:
            if current_group and (current_words + unit.word_count > target):
                g_start = current_group[0].start_char
                g_end = current_group[-1].end_char
                g_text = full_text[g_start:g_end]
                candidate_units.append(
                    ParagraphUnit(
                        start_char=g_start,
                        end_char=g_end,
                        text=g_text,
                        page=current_group[0].page,
                        word_count=len(g_text.split()),
                    )
                )
                current_group = []
                current_words = 0

            current_group.append(unit)
            current_words += unit.word_count

        if current_group:
            g_start = current_group[0].start_char
            g_end = current_group[-1].end_char
            g_text = full_text[g_start:g_end]
            candidate_units.append(
                ParagraphUnit(
                    start_char=g_start,
                    end_char=g_end,
                    text=g_text,
                    page=current_group[0].page,
                    word_count=len(g_text.split()),
                )
            )

        return candidate_units

    def chunk_document(
        self,
        txt_path: Path,
        source_file: Optional[str] = None,
        document_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Path:
        """Process a text document into semantic JSON chunks and save output."""
        full_text = self._read_document(txt_path)
        paragraphs = self._split_paragraphs(full_text)

        processed_units: list[ParagraphUnit] = []
        for p in paragraphs:
            split_units = self._split_large_paragraph(p, full_text)
            processed_units.extend(split_units)

        candidate_units = self._group_candidate_units(processed_units, full_text)
        unit_embeddings = self._get_paragraph_embeddings(candidate_units)
        chunks = self._build_semantic_chunks(candidate_units, full_text, unit_embeddings)

        doc_id = document_id or txt_path.stem

        chunk_doc = ChunkDocument(
            document_id=doc_id,
            user_id=user_id,
            source_file=source_file,
            chunks=chunks,
        )

        return self._save_chunks(chunk_doc)


def chunk_document(
    txt_path: Path,
    source_file: Optional[str] = None,
    document_id: Optional[str] = None,
    user_id: Optional[str] = None,
    embedding_service: Optional[EmbeddingService] = None,
) -> Path:
    """Public convenience function to chunk a document using default application settings."""
    service = ChunkerService(embedding_service=embedding_service)
    return service.chunk_document(
        txt_path, source_file=source_file, document_id=document_id, user_id=user_id
    )
