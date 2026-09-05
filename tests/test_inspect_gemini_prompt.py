import os
import sys

sys.path.insert(0, os.path.abspath("."))

from app.core.config import settings
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.llm_service import LLMService

user_id = '7c6751b4-90ad-47e8-b82f-d4d43b962ea6'
sample_query = "What is discussed in this document?"

chat_service = ChatService()

# 1. Step 1 & 2: Embedding & Qdrant retrieval
query_vector = chat_service.embedding_service.embed_query(sample_query)
raw_results = chat_service.qdrant_service.search_vectors(
    query_vector=query_vector,
    user_id=user_id,
    top_k=5
)

min_score = settings.min_similarity_score
relevant_chunks = [c for c in raw_results if float(c.get("score", 0.0)) >= min_score]

print("==========================================================================")
print("                   RAG RETRIEVAL TO GEMINI INSPECTION                     ")
print("==========================================================================")
print(f"Query: '{sample_query}'")
print(f"Raw Qdrant Results Count: {len(raw_results)}")
print(f"Min Score Threshold: {min_score}")
print(f"Relevant Chunks Count (after score threshold): {len(relevant_chunks)}")

print("\n--- RETRIEVED CHUNK TEXTS BEFORE GEMINI CALL ---")
for idx, chunk in enumerate(relevant_chunks, start=1):
    print(f"\n[Chunk {idx}] (score: {chunk.get('score'):.4f}, source: {chunk.get('source_file')}, page: {chunk.get('page')})")
    print(f"Text Snippet:\n{chunk.get('text')[:300]}...")

# 2. Build Prompt
llm_service = chat_service.llm_service
prompt = llm_service._build_prompt(sample_query, relevant_chunks)

print("\n--- FIRST 500 CHARACTERS OF FINAL PROMPT ---")
print(prompt[:500])

print("\n--- FULL EXACT PROMPT SENT TO GEMINI ---")
print(prompt)

# 3. Call Gemini API
print("\n--- CALLING GEMINI API WITH PROMPT ---")
try:
    gemini_raw_response = llm_service.client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
    )
    answer_text = gemini_raw_response.text.strip() if gemini_raw_response and gemini_raw_response.text else ""
    print(f"\nGemini Model Output Text:\n\"{answer_text}\"")
except Exception as e:
    print("Gemini API Error:", e)

print("==========================================================================")
