import os
import sys
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))

from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.core.config import settings

load_dotenv()

user_id = "7c6751b4-90ad-47e8-b82f-d4d43b962ea6"
exact_query = "what is an entity"

chat_service = ChatService()

# 1. Exact user query received by POST /chat
chat_request = ChatRequest(query=exact_query, top_k=5)

print("==========================================================================")
print("1. EXACT USER QUERY RECEIVED BY POST /chat:")
print(f"   Query: \"{chat_request.query}\"")
print(f"   Document ID Filter: {chat_request.document_id}")
print(f"   Top K: {chat_request.top_k}")
print(f"   User ID: {user_id}")
print("==========================================================================")

# Execute RAG steps up to prompt construction
query_vector = chat_service.embedding_service.embed_query(chat_request.query)
raw_results = chat_service.qdrant_service.search_vectors(
    query_vector=query_vector,
    user_id=user_id,
    document_id=chat_request.document_id,
    top_k=chat_request.top_k,
)

min_score = settings.min_similarity_score
relevant_chunks = [c for c in raw_results if float(c.get("score", 0.0)) >= min_score]

# 2. Exact prompt sent to Gemini
exact_prompt = chat_service.llm_service._build_prompt(chat_request.query, relevant_chunks)

print("\n==========================================================================")
print("2. EXACT PROMPT SENT TO GEMINI (client.models.generate_content):")
print("--------------------------------------------------------------------------")
print(exact_prompt)
print("==========================================================================")

# 3. Exact raw Gemini response before any parsing or formatting
raw_gemini_response = chat_service.llm_service.client.models.generate_content(
    model=settings.gemini_model,
    contents=exact_prompt,
)

print("\n==========================================================================")
print("3. EXACT RAW GEMINI RESPONSE BEFORE PARSING OR FORMATTING:")
print("--------------------------------------------------------------------------")
print(f"Raw Response Object: {raw_gemini_response}")
print("\nRaw Response Text:")
print(repr(raw_gemini_response.text))
print("==========================================================================")

# 4. Exact ChatResponse returned to the frontend
chat_response = chat_service.generate_response(chat_request, user_id=user_id)

print("\n==========================================================================")
print("4. EXACT ChatResponse RETURNED TO THE FRONTEND:")
print("--------------------------------------------------------------------------")
print(json.dumps(chat_response.model_dump(), indent=2, default=str))
print("==========================================================================")
