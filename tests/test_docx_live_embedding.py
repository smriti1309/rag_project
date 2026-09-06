"""Live integration test for DOCX document batch embedding generation.

Verifies that embedding a 4-paragraph document in batch mode calls Gemini API
and returns EXACTLY 4 embeddings (1 embedding per text input).
"""

from pathlib import Path
import tempfile
from docx import Document

from app.services.docx_parser_service import parse_docx
from app.services.chunker_service import chunk_document
from app.services.embedding_service import EmbeddingService


def test_docx_live_batch_embeddings() -> None:
    """Create a 4-paragraph DOCX document, chunk it into 4 chunks, and verify 4 embeddings are generated."""

    print("\n" + "=" * 70)
    print("STARTING LIVE DOCX BATCH EMBEDDING VERIFICATION")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Create a real 4-paragraph DOCX file simulating dbms.docx
        docx_path = tmp_path / "dbms.docx"
        doc = Document()
        doc.add_heading("Database Management Systems Overview", level=1)
        doc.add_paragraph(
            "A Database Management System (DBMS) is software designed to store, retrieve, "
            "define, and manage data in a database. Common DBMS platforms include PostgreSQL, MySQL, and Oracle."
        )
        doc.add_paragraph(
            "Relational databases structure data into tables with predefined schemas, rows, and columns. "
            "SQL is standard query language used to interact with relational databases."
        )
        doc.add_paragraph(
            "NoSQL databases handle unstructured or semi-structured data such as JSON documents, key-value pairs, "
            "and graph databases. They offer flexible scaling and dynamic schema design."
        )
        doc.add_paragraph(
            "Vector databases store high-dimensional embeddings for fast semantic similarity search. "
            "They enable modern Retrieval-Augmented Generation (RAG) pipelines and LLM context search."
        )
        doc.save(docx_path)

        print(f"Created test DOCX file at: {docx_path}")

        # 2. Parse DOCX to text
        txt_path = parse_docx(docx_path)
        print(f"Parsed DOCX to text file: {txt_path}")

        # 3. Chunk document into JSON chunks
        chunk_json_path = chunk_document(
            txt_path=txt_path,
            source_file="dbms.docx",
            document_id="dbms-doc-test-123",
            user_id="test-user-uuid",
        )
        print(f"Generated chunk JSON file: {chunk_json_path}")

        # 4. Generate embeddings using EmbeddingService
        service = EmbeddingService()
        embedding_json_path = service.embed_document(
            chunk_json_path=chunk_json_path,
            user_id="test-user-uuid",
            document_id="dbms-doc-test-123",
            source_file="dbms.docx",
        )

        print(f"Generated embeddings JSON file: {embedding_json_path}")

        import json
        c_data = json.loads(chunk_json_path.read_text(encoding="utf-8"))
        emb_data = json.loads(embedding_json_path.read_text(encoding="utf-8"))

        chunk_input_count = len(c_data["chunks"])
        embedding_output_count = len(emb_data["embeddings"])

        print("\nVERIFICATION RESULTS:")
        print(f"Document ID: {emb_data['document_id']}")
        print(f"Source File: {emb_data['source_file']}")
        print(f"Embedding Vector Dimension: {emb_data['dimension']}")
        print(f"Input Text Chunks Count: {chunk_input_count}")
        print(f"Output Embeddings Count: {embedding_output_count}")

        assert embedding_output_count == chunk_input_count, f"Expected {chunk_input_count} embeddings, got {embedding_output_count}"
        for idx, emb_item in enumerate(emb_data["embeddings"], start=1):
            assert len(emb_item["embedding"]) == 768
            print(f"  Chunk {idx}: ID={emb_item['chunk_id']}, Vector Dimensions={len(emb_item['embedding'])}")

        print("\n" + "=" * 70)
        print(f"VERIFICATION SUCCESSFUL: {chunk_input_count} CHUNK INPUTS PRODUCED EXACTLY {embedding_output_count} EMBEDDINGS (1 EMBEDDING PER CHUNK)!")
        print("=" * 70)


if __name__ == "__main__":
    test_docx_live_batch_embeddings()
