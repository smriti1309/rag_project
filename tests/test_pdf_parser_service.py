from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz

from app.core.config import settings
from app.services.pdf_parser_service import parse_pdf


def create_sample_pdf(file_path: Path, pages_content: list[str]) -> Path:
    """Helper function to create a test PDF with given page contents."""
    doc = fitz.open()
    for content in pages_content:
        page = doc.new_page()
        if content:
            page.insert_text((50, 50), content)
    doc.save(file_path)
    doc.close()
    return file_path


class TestPDFParserService(unittest.TestCase):
    """Test suite for PDF Parser Service."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        self.processed_dir = self.tmp_path / "processed"

        # Patch settings.processed_directory for isolated testing
        self.patcher = patch.object(settings, "processed_directory", self.processed_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_parse_pdf_valid(self):
        """Test successful parsing of a valid multi-page PDF document."""
        upload_dir = self.tmp_path / "uploads"
        upload_dir.mkdir()

        pdf_file = upload_dir / "abc123.pdf"
        create_sample_pdf(
            pdf_file, ["Hello world from page 1.", "Welcome to page 2."]
        )

        result_path = parse_pdf(pdf_file)

        self.assertEqual(result_path, self.processed_dir / "abc123.txt")
        self.assertTrue(result_path.exists())

        content = result_path.read_text(encoding="utf-8")
        self.assertIn("===== PAGE 1 =====", content)
        self.assertIn("Hello world from page 1.", content)
        self.assertIn("===== PAGE 2 =====", content)
        self.assertIn("Welcome to page 2.", content)

    def test_parse_pdf_file_not_found(self):
        """Test that FileNotFoundError is raised when input PDF file does not exist."""
        non_existent = self.tmp_path / "non_existent.pdf"
        with self.assertRaises(FileNotFoundError):
            parse_pdf(non_existent)

    def test_parse_pdf_no_extractable_text(self):
        """Test that ValueError is raised when PDF contains no extractable text."""
        upload_dir = self.tmp_path / "uploads"
        upload_dir.mkdir()

        pdf_file = upload_dir / "empty.pdf"
        create_sample_pdf(pdf_file, ["", "   "])

        with self.assertRaises(ValueError):
            parse_pdf(pdf_file)

    def test_parse_pdf_corrupt_file_propagates_exception(self):
        """Test that unexpected parsing errors (e.g. corrupt PDF file) propagate."""
        corrupt_file = self.tmp_path / "corrupt.pdf"
        corrupt_file.write_bytes(b"This is not a valid PDF content.")

        with self.assertRaises(Exception):
            parse_pdf(corrupt_file)


if __name__ == "__main__":
    unittest.main()
