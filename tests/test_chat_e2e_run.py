import os
import sys
import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))

from app.schemas.chat import ChatRequest
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService
from app.services.chat_service import generate_response

load_dotenv()

test_user_id = '7c6751b4-90ad-47e8-b82f-d4d43b962ea6'
query_str = 'Retrieval-Augmented Generation (RAG) Architecture Verification Document Supabase Cloudflare R2 Qdrant Gemini'

print(f'Testing query: "{query_str}"', flush=True)

emb_service = EmbeddingService()
q_service = QdrantService()

query_vec = emb_service.embed_query(query_str)
raw_res = q_service.search_vectors(query_vector=query_vec, user_id=test_user_id, top_k=5)

print(f'Raw Qdrant results count: {len(raw_res)}', flush=True)
for r in raw_res:
    print('  Point:', r.get('source_file'), 'Score:', r.get('score'), 'Text snippet:', r.get('text')[:60], flush=True)

chat_req = ChatRequest(query=query_str, top_k=5)
chat_res = generate_response(chat_req, user_id=test_user_id)

print('\n=== CHAT RESPONSE VERIFICATION ===', flush=True)
print('Query:', chat_res.query, flush=True)
print('Grounded Gemini Answer:\n', chat_res.answer, flush=True)
print(f'\nRetrieved Chunks Count: {chat_res.retrieved_chunk_count}', flush=True)
print(f'Retrieval Time: {chat_res.retrieval_time_ms} ms', flush=True)
