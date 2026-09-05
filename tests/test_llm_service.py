"""Unit tests for LLMService and Gemini prompt context construction."""

import unittest
from unittest.mock import MagicMock

from app.core.config import Settings
from app.services.llm_service import LLMService


class TestLLMService(unittest.TestCase):
    """Test suite for LLMService."""

    def setUp(self) -> None:
        self.mock_genai_client = MagicMock()

    def test_build_prompt_context_bounding(self) -> None:
        """Test prompt context accumulation respects max_context_chars threshold."""
        custom_settings = Settings(max_context_chars=120)
        service = LLMService(client=self.mock_genai_client, settings=custom_settings)

        chunks = [
            {
                "text": "Chunk 1 text content for testing score ordering.",
                "source_file": "doc1.pdf",
                "page": 1,
                "score": 0.95,
            },
            {
                "text": "Chunk 2 extra long text content that should exceed character limit.",
                "source_file": "doc2.pdf",
                "page": 2,
                "score": 0.85,
            },
            {
                "text": "Chunk 3 text content.",
                "source_file": "doc3.pdf",
                "page": 3,
                "score": 0.75,
            },
        ]

        prompt = service._build_prompt("What is testing?", chunks)

        self.assertIn("Chunk 1 text content", prompt)
        self.assertIn("You are an AI Knowledge Assistant", prompt)
        self.assertIn("What is testing?", prompt)

    def test_generate_answer_success(self) -> None:
        """Test successful answer generation via mock genai Client."""
        mock_response = MagicMock()
        mock_response.text = "Retrieval-Augmented Generation is a framework."
        self.mock_genai_client.models.generate_content.return_value = mock_response

        service = LLMService(client=self.mock_genai_client)

        chunks = [
            {
                "text": "Retrieval-Augmented Generation combines search and LLM.",
                "source_file": "paper.pdf",
                "page": 1,
                "score": 0.9,
            }
        ]

        answer = service.generate_answer("What is RAG?", chunks)

        self.assertEqual(answer, "Retrieval-Augmented Generation is a framework.")
        self.mock_genai_client.models.generate_content.assert_called_once()

    def test_generate_answer_missing_client(self) -> None:
        """Test ValueError raised when GEMINI_API_KEY is not configured."""
        custom_settings = Settings(gemini_api_key=None)
        service = LLMService(client=None, settings=custom_settings)

        with self.assertRaises(ValueError) as ctx:
            service.generate_answer("What is RAG?", [{"text": "sample"}])
        self.assertIn("GEMINI_API_KEY is not configured", str(ctx.exception))

    def test_generate_answer_empty_chunks(self) -> None:
        """Test fallback text returned when chunks list is empty."""
        service = LLMService(client=self.mock_genai_client)
        answer = service.generate_answer("What is RAG?", [])
        self.assertEqual(
            answer, "I couldn't find any relevant information in your uploaded documents."
        )
        self.mock_genai_client.models.generate_content.assert_not_called()


    def test_build_prompt_preserves_input_chunk_ordering(self) -> None:
        """Test prompt context preserves input chunk order supplied by RRF without re-sorting by dense score."""
        service = LLMService(client=self.mock_genai_client)

        chunks = [
            {
                "text": "First RRF chunk (lower dense score but higher RRF rank).",
                "source_file": "docA.pdf",
                "page": 1,
                "score": 0.70,
                "rrf_score": 0.030,
            },
            {
                "text": "Second RRF chunk (higher dense score).",
                "source_file": "docB.pdf",
                "page": 2,
                "score": 0.90,
                "rrf_score": 0.025,
            },
            {
                "text": "Third RRF chunk (BM25-only match with score 0.0).",
                "source_file": "docC.pdf",
                "page": 3,
                "score": 0.0,
                "bm25_score": 15.0,
                "rrf_score": 0.020,
            },
        ]

        prompt = service._build_prompt("Test question", chunks)

        pos_first = prompt.find("First RRF chunk")
        pos_second = prompt.find("Second RRF chunk")
        pos_third = prompt.find("Third RRF chunk")

        self.assertNotEqual(pos_first, -1)
        self.assertNotEqual(pos_second, -1)
        self.assertNotEqual(pos_third, -1)

        # Assert exact input order [First, Second, Third] is maintained in prompt
        self.assertLess(pos_first, pos_second)
        self.assertLess(pos_second, pos_third)

    def test_build_prompt_five_chunks_retrieval_regression(self) -> None:
        """Test that 5 retrieved chunks (with answer in chunk #4) are all included under default context budget,

        and verify that the old 4000-character limit omitted chunk #4. Also verify RRF ordering is preserved.
        """
        # Create 5 chunks where chunks 1-3 consume >4000 characters total
        chunks = [
            {
                "text": "Chunk 1 filler content. " * 60,  # ~1440 chars
                "source_file": "doc1.pdf",
                "page": 2,
                "score": 0.90,
            },
            {
                "text": "Chunk 2 management care plan. " * 50,  # ~1500 chars
                "source_file": "doc1.pdf",
                "page": 2,
                "score": 0.85,
            },
            {
                "text": "Chunk 3 introduction details. " * 50,  # ~1500 chars
                "source_file": "doc1.pdf",
                "page": 1,
                "score": 0.80,
            },
            {
                "text": "Outcomes: After the first week of care the patient was noted as being less hyperactive and less aggressive.",
                "source_file": "doc1.pdf",
                "page": 3,
                "score": 0.75,
            },
            {
                "text": "Chunk 5 conclusion summary and follow up care.",
                "source_file": "doc1.pdf",
                "page": 4,
                "score": 0.70,
            },
        ]

        # 1. Verify old 4000-char behavior omitted chunk #4
        old_service = LLMService(client=self.mock_genai_client, settings=Settings(max_context_chars=4000))
        old_prompt = old_service._build_prompt("what was the overall observation in the experiment", chunks)
        self.assertNotIn("Outcomes: After the first week of care", old_prompt)

        # 2. Verify new default behavior includes chunk #4 and chunk #5
        service = LLMService(client=self.mock_genai_client, settings=Settings(max_context_chars=20000))
        prompt = service._build_prompt("what was the overall observation in the experiment", chunks)

        self.assertIn("Outcomes: After the first week of care", prompt)
        self.assertIn("Chunk 5 conclusion summary", prompt)

        # 3. Verify exact RRF input ordering is preserved
        pos_1 = prompt.find("Chunk 1 filler content")
        pos_2 = prompt.find("Chunk 2 management care plan")
        pos_3 = prompt.find("Chunk 3 introduction details")
        pos_4 = prompt.find("Outcomes: After the first week of care")
        pos_5 = prompt.find("Chunk 5 conclusion summary")

        self.assertNotEqual(pos_1, -1)
        self.assertNotEqual(pos_2, -1)
        self.assertNotEqual(pos_3, -1)
        self.assertNotEqual(pos_4, -1)
        self.assertNotEqual(pos_5, -1)

        self.assertLess(pos_1, pos_2)
        self.assertLess(pos_2, pos_3)
        self.assertLess(pos_3, pos_4)
        self.assertLess(pos_4, pos_5)


if __name__ == "__main__":
    unittest.main()


