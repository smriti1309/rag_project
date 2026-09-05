import os
import sys
import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))

from app.core.config import settings
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService
from app.services.document_repository import DocumentRepository
from qdrant_client import models

load_dotenv()

print("==========================================================================")
print("              INVESTIGATING RETRIEVAL PIPELINE STEP-BY-STEP               ")
print("==========================================================================")

# 1. Supabase Documents Check
db_url = os.getenv("DATABASE_URL")
conn = psycopg2.connect(db_url)
cur = conn.cursor()
cur.execute("SELECT id, user_id, filename, status, chunk_count, uploaded_at FROM public.documents ORDER BY uploaded_at DESC LIMIT 10;")
rows = cur.fetchall()
cur.close()
conn.close()

print(f"\n--- Supabase public.documents Records ({len(rows)} found) ---")
for r in rows:
    print(f"Doc ID: {r[0]} | User ID: {r[1]} | File: {r[2]} | Status: {r[3]} | Chunk Count: {r[4]} | Uploaded: {r[5]}")

# Pick the latest document or 56-chunk document if present
target_doc = None
for r in rows:
    if r[4] == 56 or r[3] == 'indexed':
        target_doc = r
        break

if not target_doc and rows:
    target_doc = rows[0]

target_doc_id = target_doc[0] if target_doc else None
target_user_id = target_doc[1] if target_doc else None

print(f"\nTarget Document Selected for Verification: ID={target_doc_id}, UserID={target_user_id}, Filename={target_doc[2] if target_doc else None}")

# 2. Qdrant Collection & Points Check
q_service = QdrantService()
collection_name = settings.qdrant_collection_name
print(f"\n--- Qdrant Collection Verification ---")
print(f"Collection Name: {collection_name}")

collection_exists = q_service.client.collection_exists(collection_name)
print(f"Collection Exists: {collection_exists}")

if collection_exists:
    coll_info = q_service.client.get_collection(collection_name)
    vectors_count = coll_info.points_count
    print(f"Total Points/Vectors in Qdrant Collection '{collection_name}': {vectors_count}")
    
    # Check count of points specifically matching target_doc_id
    if target_doc_id:
        doc_count_res = q_service.client.count(
            collection_name=collection_name,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=target_doc_id)
                    )
                ]
            )
        )
        print(f"Vectors in Qdrant specifically matching document_id='{target_doc_id}': {doc_count_res.count}")
    
    # 3. Dump One Stored Payload
    print(f"\n--- Dumping One Stored Payload from Qdrant ---")
    scroll_res = q_service.client.scroll(
        collection_name=collection_name,
        limit=1,
        with_payload=True,
        with_vectors=True
    )
    points = scroll_res[0]
    if points:
        pt = points[0]
        payload = pt.payload or {}
        vec = pt.vector
        if isinstance(vec, list):
            vec_dim = len(vec)
        elif isinstance(vec, dict):
            vec_dim = len(list(vec.values())[0]) if vec else 0
        else:
            vec_dim = "unknown"
            
        print(f"Point ID: {pt.id}")
        print(f"Vector Dimension in Qdrant: {vec_dim}")
        print(f"Stored Payload Fields:")
        print(f"  - user_id: {payload.get('user_id')} (type: {type(payload.get('user_id'))})")
        print(f"  - document_id: {payload.get('document_id')} (type: {type(payload.get('document_id'))})")
        print(f"  - chunk_id: {payload.get('chunk_id')} (type: {type(payload.get('chunk_id'))})")
        print(f"  - page: {payload.get('page')} (type: {type(payload.get('page'))})")
        print(f"  - source_file: {payload.get('source_file')}")
        print(f"  - model: {payload.get('model')}")
        text_snippet = str(payload.get('text', ''))
        print(f"  - text (first 100 chars): {text_snippet[:100]}...")

# 4. Trace POST /chat Retrieval Flow
print(f"\n--- Tracing POST /chat Retrieval Pipeline ---")
sample_query = "What is discussed in this document?"
print(f"Sample Query: '{sample_query}'")

emb_service = EmbeddingService()
print(f"Embedding Service Configured Model: '{emb_service.settings.embedding_model}'")

query_vector = emb_service.embed_query(sample_query)
print(f"Generated Query Embedding Vector Length: {len(query_vector)}")

# Filter applied during POST /chat
user_id_for_chat = target_user_id or "7c6751b4-90ad-47e8-b82f-d4d43b962ea6"
applied_filter = models.Filter(
    must=[
        models.FieldCondition(
            key="user_id",
            match=models.MatchValue(value=user_id_for_chat),
        )
    ]
)
print(f"Applied Qdrant Filter: user_id='{user_id_for_chat}'")

# Execute Search in Qdrant WITHOUT user_id filter first (to see raw scores across all points)
print(f"\n1. Qdrant Search Results UNFILTERED (top 5):")
try:
    unfiltered_res = q_service.client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=5,
    ).points
    for idx, p in enumerate(unfiltered_res, start=1):
        p_payload = p.payload or {}
        print(f"  [{idx}] Score: {p.score:.4f} | doc_id: {p_payload.get('document_id')} | user_id: {p_payload.get('user_id')} | file: {p_payload.get('source_file')}")
except Exception as e:
    print(f"  Error during unfiltered search: {e}")

# Execute Search in Qdrant WITH applied user_id filter
print(f"\n2. Qdrant Search Results WITH user_id filter='{user_id_for_chat}' (top 5):")
try:
    filtered_res = q_service.client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=applied_filter,
        limit=5,
    ).points
    print(f"  Points returned with filter: {len(filtered_res)}")
    for idx, p in enumerate(filtered_res, start=1):
        p_payload = p.payload or {}
        print(f"  [{idx}] Score: {p.score:.4f} | doc_id: {p_payload.get('document_id')} | user_id: {p_payload.get('user_id')} | file: {p_payload.get('source_file')}")
except Exception as e:
    print(f"  Error during filtered search: {e}")

# Check minimum similarity score threshold
min_threshold = settings.min_similarity_score
print(f"\nMinimum Similarity Score Threshold in Settings: {min_threshold}")
if filtered_res:
    top_score = max([p.score for p in filtered_res])
    relevant_count = sum(1 for p in filtered_res if p.score >= min_threshold)
    print(f"Top Similarity Score: {top_score:.4f}")
    print(f"Count of Chunks meeting >= {min_threshold}: {relevant_count}")
    if relevant_count == 0:
        print(f"==> EXPLANATION: All {len(filtered_res)} retrieved chunks had similarity scores ({top_score:.4f}) below threshold ({min_threshold}), so chat_service filtered them out and returned retrieved_chunk_count = 0!")
else:
    print("==> EXPLANATION: Qdrant returned 0 points matching the filter!")

print("\n==========================================================================")
