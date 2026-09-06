"""LLM service module for grounded RAG answer generation using official Google GenAI SDK."""

import logging
from typing import Any, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.core.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)


class LLMService:
    """Service for generating grounded AI answers using Google Gemini API."""

    def __init__(
        self,
        client: Optional[genai.Client] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        """Initialize LLMService with configuration and optional GenAI Client.

        Args:
            client: Optional pre-configured genai.Client instance (useful for testing/mocking).
            settings: Optional Settings instance. Defaults to global application settings.
        """
        self.settings = settings or default_settings

        if client is not None:
            self.client = client
        elif self.settings.gemini_api_key:
            self.client = genai.Client(api_key=self.settings.gemini_api_key)
        else:
            self.client = None

    def rewrite_query(
        self, query: str, history: Optional[list[dict[str, Any]]] = None
    ) -> str:
        """Rewrite ambiguous follow-up query into a standalone, context-complete search query based on conversation history.

        Args:
            query: Raw user search query string.
            history: Optional list of previous chat message dicts containing 'role' and 'content'.

        Returns:
            str: Reformulated standalone search query string or original query if history is empty or rewriting fails.
        """
        if not history or not self.client:
            return query

        formatted_turns = []
        for msg in history:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = str(msg.get("content", "")).strip()
            if content:
                formatted_turns.append(f"{role}: {content}")

        if not formatted_turns:
            return query

        history_text = "\n".join(formatted_turns)

        prompt = (
            "Given the following conversation history and a follow-up user question, "
            "rephrase the follow-up question into a single, self-contained, clear search query "
            "that includes all necessary entity names and context needed for document retrieval.\n\n"
            "Do NOT answer the question. Output ONLY the rephrased standalone search query string.\n\n"
            "====================\n"
            "CONVERSATION HISTORY\n"
            "====================\n"
            f"{history_text}\n\n"
            "====================\n"
            "FOLLOW-UP QUESTION\n"
            "====================\n"
            f"{query}\n\n"
            "Standalone Search Query:"
        )

        try:
            config = types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=100,
            )
            response = self.client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=config,
            )
            rewritten = response.text.strip() if response and response.text else ""
            if rewritten.startswith('"') and rewritten.endswith('"'):
                rewritten = rewritten[1:-1].strip()
            return rewritten if rewritten else query
        except Exception as e:
            logger.warning("Query rewriting failed: %s. Falling back to original query.", e)
            return query

    def _build_prompt(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        history: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Dynamically construct grounded prompt within configured character context limits."""

        max_chars = self.settings.max_context_chars
        context_parts: list[str] = []
        current_chars = 0

        for chunk in chunks:
            text = str(chunk.get("text", "")).strip()
            if not text:
                continue

            source_file = chunk.get("source_file", "unknown")
            page = chunk.get("page", "N/A")

            chunk_block = (
                f"[Source: {source_file}, Page: {page}]\n"
                f"{text}"
            )

            if current_chars + len(chunk_block) > max_chars and context_parts:
                logger.info(
                    "Context character limit reached (%d/%d chars). Stopping context accumulation.",
                    current_chars,
                    max_chars,
                )
                break

            context_parts.append(chunk_block)
            current_chars += len(chunk_block)

        formatted_context = "\n\n---\n\n".join(context_parts)

        history_section = ""
        if history:
            formatted_turns = []
            for msg in history:
                role = "User" if msg.get("role") == "user" else "Assistant"
                content = str(msg.get("content", "")).strip()
                if content:
                    formatted_turns.append(f"{role}: {content}")
            if formatted_turns:
                history_text = "\n".join(formatted_turns)
                history_section = (
                    "====================\n"
                    "CONVERSATION HISTORY\n"
                    "====================\n"
                    f"{history_text}\n\n"
                )

        prompt = (
            "You are an AI Knowledge Assistant.\n\n"
            "Answer the user's question using ONLY the provided document context below.\n\n"
            "If the context defines, describes, or contains relevant information related to the question "
            "(including related terms, types, sets, or properties), explain it clearly using ONLY the context.\n\n"
            "You MUST NOT:\n"
            "- Use outside knowledge.\n"
            "- Invent facts.\n\n"
            "If the provided context genuinely does not contain relevant information to answer the question, "
            "reply EXACTLY with:\n"
            "\"I couldn't find that information in the uploaded documents.\"\n\n"
            f"{history_section}"
            "====================\n"
            "CONTEXT\n"
            "====================\n"
            f"{formatted_context}\n\n"
            "====================\n"
            "QUESTION\n"
            "====================\n"
            f"{query}\n\n"
            "Answer:"
        )

        return prompt

    def generate_answer(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        history: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Generate grounded answer using Gemini model via official SDK."""

        if not self.client:
            raise ValueError("GEMINI_API_KEY is not configured.")

        if not chunks:
            return "I couldn't find any relevant information in your uploaded documents."

        prompt = self._build_prompt(query, chunks, history=history)

        logger.info(
            "Sending prompt to Gemini model '%s' (prompt_length=%d chars)...",
            self.settings.gemini_model,
            len(prompt),
        )

        try:
            response = self.client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
            )

            answer = response.text.strip() if response and response.text else ""

            if not answer:
                return "I couldn't find that information in the uploaded documents."

            return answer

        except APIError as e:
            logger.error("Gemini API error during generation: %s", e)
            raise RuntimeError(f"LLM generation failed: {e.message}") from e

        except Exception as e:
            logger.error("Unexpected error during LLM generation: %s", e)
            raise RuntimeError(f"LLM generation failed: {e}") from e