"""PDF parser service module for extracting text from PDF documents."""

from pathlib import Path

import fitz  # PyMuPDF

from app.core.config import settings


def parse_pdf(pdf_path: Path) -> Path:
    """Parse text content from a PDF file and save it as a plain text file.

    Extracts text page by page with page separators and writes the combined output
    to a text file in the processed directory using the same stem as the input PDF.

    Args:
        pdf_path: Path to the input PDF file.

    Returns:
        Path: Path to the generated .txt file in the processed directory.

    Raises:
        FileNotFoundError: If the pdf_path does not exist or is not a file.
        ValueError: If the PDF contains no extractable text across all pages.
        Exception: Propagates any unexpected PyMuPDF or file system errors.
    """
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

    target_dir = settings.processed_directory
    extracted_pages: list[str] = []

    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                extracted_pages.append(f"===== PAGE {page_num} =====\n{text}")

    if not extracted_pages:
        raise ValueError(f"PDF file contains no extractable text: {pdf_path}")

    combined_text = "\n\n".join(extracted_pages)

    target_dir.mkdir(parents=True, exist_ok=True)
    output_file_path = target_dir / f"{pdf_path.stem}.txt"
    output_file_path.write_text(combined_text, encoding="utf-8")

    return output_file_path
