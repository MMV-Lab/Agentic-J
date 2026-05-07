"""
RAG (Retrieval-Augmented Generation) System for ImageJ Agent
Hybrid Search (Dense + Sparse) with Reciprocal Rank Fusion (RRF).

Changes from original:
  - PDF chunking: Docling HybridChunker + contextualize() (no more double-chunking)
  - All file types: smart routing via load_and_chunk_file()
  - OCR: selective (do_ocr=True, only OCRs regions without text layer)
  - Accelerator: device='auto' (CUDA > MPS > CPU, no manual toggle)
  - Embeddings: OpenRouter only (cleaned up dual-key logic)
  - tiktoken tokenizer aligned to text-embedding-3-large (local, no API key)
"""

import sys
import os
import hashlib
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

script_dir = Path(__file__).resolve()
if script_dir.parent.name == 'rag':
    src_dir = script_dir.parent.parent.parent
else:
    src_dir = script_dir.parent.parent.parent.parent

if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from ..qdrant_client_singleton import get_qdrant_client
from qdrant_client import QdrantClient
from qdrant_client.http import models
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

from imagentj.rag.loaders import (
    get_docling_converter,
    get_hybrid_chunker,
    load_and_chunk_file,
)

from config.rag_config import (
    QDRANT_DATA_PATH, DOCS_COLLECTION_NAME, MISTAKES_COLLECTION_NAME,
    RECIPES_COLLECTION_NAME,
    PLUGINS_COLLECTION_NAME, INGESTION_FOLDERS, BATCH_SIZE,
    SKIP_PATTERNS, SUPPORTED_EXTENSIONS
)


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

openrouter_key = os.getenv("OPEN_ROUTER_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

# ---------------------------------------------------------------------------
# Hybrid Search Configuration
# ---------------------------------------------------------------------------

SPARSE_MODEL_NAME = "Qdrant/bm25"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


# ---------------------------------------------------------------------------
# File Hashing & Deduplication
# ---------------------------------------------------------------------------

def get_file_hash(file_path: str) -> str:
    """Generate a SHA-256 hash for a file's content."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def is_document_ingested(file_hash: str, client, collection_name: str) -> bool:
    """Check if any points in the collection share this file_hash."""
    result = client.count(
        collection_name=collection_name,
        count_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.file_hash",
                    match=models.MatchValue(value=file_hash),
                ),
            ]
        ),
    )
    return result.count > 0


# ---------------------------------------------------------------------------
# Embedding Models
# ---------------------------------------------------------------------------

def get_embeddings_models():
    """
    Returns the initialized dense and sparse embedding models.
    """
    if openrouter_key:
        dense_embeddings = OpenAIEmbeddings(
            model="openai/text-embedding-3-large",
            api_key=openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
        )
    elif openai_key and not openrouter_key:
        dense_embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            api_key=openai_key,
        )
    else:
        raise ValueError("No API key found. Set OPEN_ROUTER_API_KEY or OPENAI_API_KEY.")

    sparse_embeddings = FastEmbedSparse(model_name=SPARSE_MODEL_NAME)
    return dense_embeddings, sparse_embeddings

# ---------------------------------------------------------------------------
# Vector Store Initialization
# ---------------------------------------------------------------------------

def init_vector_store(collection_name: str, client: QdrantClient = None,
                      dense_embeddings=None, sparse_embeddings=None):
    """
    Initialize a Qdrant vector store with HYBRID configuration (Dense + Sparse).

    Both `client` and the embedding models can be injected; this is required for
    tests that run against an in-memory Qdrant client with stub embeddings.
    """
    if client is None:
        client = get_qdrant_client(path=QDRANT_DATA_PATH)

    if dense_embeddings is None or sparse_embeddings is None:
        d_default, s_default = get_embeddings_models()
        dense_embeddings = dense_embeddings or d_default
        sparse_embeddings = sparse_embeddings or s_default

    if not client.collection_exists(collection_name=collection_name):
        print(f"Creating new Hybrid Qdrant collection: {collection_name}")

        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=3072,  # text-embedding-3-large
                    distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=True,
                    )
                )
            },
        )
    else:
        print(f"Collection '{collection_name}' exists. Using existing configuration.")

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=dense_embeddings,
        sparse_embedding=sparse_embeddings,
        vector_name=DENSE_VECTOR_NAME,
        sparse_vector_name=SPARSE_VECTOR_NAME,
        retrieval_mode=RetrievalMode.HYBRID,
    )

    return vector_store


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def apply_rrf(ranked_lists, k: int = 60):
    """
    Reciprocal Rank Fusion across multiple ranked result lists.

    Each input list is treated as an independent ranking; a document at position
    `r` in any list contributes 1/(k + r) to its fused score, and contributions
    from multiple lists are summed. This is the canonical RRF formula
    (Cormack, Clarke, Buettcher 2009).

    Args:
        ranked_lists: Either an iterable of ranked lists (one per query), OR a
                      single flat list (treated as a single ranking — legacy
                      behaviour, kept for callers that pre-flatten). The input
                      type is auto-detected: if every element is itself a list
                      or tuple, multi-list mode is used.
        k: RRF constant. 60 is the standard.

    Returns:
        Documents (Qdrant ScoredPoint) sorted by descending fused score, each
        carrying a `.score` attribute set to the fused RRF score.
    """
    # Auto-detect: list-of-lists vs flat list
    if ranked_lists and all(isinstance(rl, (list, tuple)) for rl in ranked_lists):
        lists = list(ranked_lists)
    else:
        lists = [list(ranked_lists)]

    fused_scores = {}
    payloads = {}

    for ranked in lists:
        for rank, point in enumerate(ranked):
            doc_id = point.id
            fused_scores[doc_id] = fused_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in payloads:
                payloads[doc_id] = point

    sorted_ids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)
    out = []
    for doc_id in sorted_ids:
        p = payloads[doc_id]
        # Overwrite the per-query similarity score with the fused RRF score so
        # downstream consumers (threshold filters, formatters) see the right value.
        try:
            p.score = fused_scores[doc_id]
        except AttributeError:
            pass  # immutable result types — caller will re-pull score via dict
        out.append(p)
    return out


def hybrid_search_with_rrf(
    query_text: str,
    collection_name: str = DOCS_COLLECTION_NAME,
    limit: int = 5,
    k: int = 60,
    query_filter=None,
    client=None,
    dense_emb=None,
    sparse_emb=None,
):
    """
    Perform a Hybrid Search using Reciprocal Rank Fusion (RRF).

    Uses Qdrant's native RRF fusion, which prefetches results from both
    dense and sparse indices and fuses them server-side.

    Args:
        query_text:      The user's search query
        collection_name: Target collection
        limit:           Number of final results to return
        k:               RRF constant (kept for signature compatibility; the
                         server-side Qdrant RRF uses its own constant)
        query_filter:    Optional `qdrant_client.http.models.Filter` applied to
                         BOTH the dense and sparse prefetches. Use this to
                         restrict mistake retrieval by language/error_type.
        client:          Optional injected Qdrant client (for tests).
        dense_emb:       Optional injected dense embeddings (for tests).
        sparse_emb:      Optional injected sparse embeddings (for tests).

    Returns:
        List of ScoredPoint with server-side RRF scores.
    """
    if client is None:
        client = get_qdrant_client(path=QDRANT_DATA_PATH)
    if dense_emb is None or sparse_emb is None:
        d_default, s_default = get_embeddings_models()
        dense_emb = dense_emb or d_default
        sparse_emb = sparse_emb or s_default

    # Generate vectors for the query
    dense_vector = dense_emb.embed_query(query_text)
    sparse_vector = sparse_emb.embed_query(query_text)

    # Convert LangChain sparse format to Qdrant native format
    qdrant_sparse_vector = models.SparseVector(
        indices=sparse_vector.indices,
        values=sparse_vector.values
    )

    print(f"Executing RRF Hybrid Search for: '{query_text}'")

    results = client.query_points(
        collection_name=collection_name,
        prefetch=[
            models.Prefetch(
                query=dense_vector,
                using=DENSE_VECTOR_NAME,
                limit=limit,
                filter=query_filter,
            ),
            models.Prefetch(
                query=qdrant_sparse_vector,
                using=SPARSE_VECTOR_NAME,
                limit=limit,
                filter=query_filter,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        query_filter=query_filter,
        limit=limit,
    )

    return results.points


# ---------------------------------------------------------------------------
# Document Ingestion
# ---------------------------------------------------------------------------

def load_folder_recursively(
    folders: list = None,
    vector_store=None,
    collection_name: str = DOCS_COLLECTION_NAME,
):
    """
    Recursively load and process documents from configured folders.

    Uses load_and_chunk_file() which automatically routes each file
    to its optimal chunking strategy:

      .pdf         → Docling layout-aware + HybridChunker + contextualize()
      .md          → Docling heading-aware + HybridChunker + contextualize()
      .txt         → Docling paragraph-aware + HybridChunker
      .py          → Python AST: splits by function/class boundaries
      .java/.groovy → Regex structural split at method/class boundaries
      .ipynb       → Cell-aware markdown → Docling + HybridChunker
      .js/.ts      → Language-aware RecursiveCharacterTextSplitter
    """
    if folders is None:
        folders = INGESTION_FOLDERS

    if vector_store is None:
        vector_store = init_vector_store(collection_name)

    if not folders:
        print("No ingestion folders configured.")
        return

    # Reuse across all files — stateless, safe to share
    converter = get_docling_converter()
    chunker = get_hybrid_chunker()

    all_chunks = []

    for folder_path in folders:
        print(f"Processing folder: {folder_path}")
        if not os.path.exists(folder_path):
            continue

        for root, _, files in os.walk(folder_path):
            if any(skip_pattern in root for skip_pattern in SKIP_PATTERNS):
                continue

            for file in files:
                file_path = os.path.join(root, file)
                file_hash = get_file_hash(file_path)

                # Check if already in DB
                if is_document_ingested(file_hash, vector_store.client, collection_name):
                    print(f"  Skipping (already ingested): {file}")
                    continue

                ext = Path(file).suffix.lower()

                # Check supported extensions
                supported = any(
                    ext in SUPPORTED_EXTENSIONS[category]
                    for category in SUPPORTED_EXTENSIONS
                )
                if not supported:
                    continue

                try:
                    print(f"  Processing: {file_path}")

                    # Single call routes to the best chunking strategy
                    final_splits = load_and_chunk_file(
                        file_path=file_path,
                        converter=converter,
                        chunker=chunker,
                    )

                    if final_splits:
                        for chunk in final_splits:
                            chunk.metadata["file_hash"] = file_hash
                        all_chunks.extend(final_splits)

                    # Batch Upload
                    if len(all_chunks) >= BATCH_SIZE:
                        print(f"  Uploading batch of {len(all_chunks)} chunks (Dense + Sparse)...")
                        vector_store.add_documents(all_chunks)
                        all_chunks = []

                except Exception as e:
                    print(f"  Error processing {file_path}: {e}")

    if all_chunks:
        print(f"Uploading final batch of {len(all_chunks)} chunks...")
        vector_store.add_documents(all_chunks)

    print("Document ingestion completed!")


# ---------------------------------------------------------------------------
# System Initialization
# ---------------------------------------------------------------------------

def initialize_rag_system():
    """Initialize all Qdrant collections for the RAG system."""
    print("Initializing Hybrid RAG system...")
    client = get_qdrant_client(path=QDRANT_DATA_PATH)

    docs_store = init_vector_store(DOCS_COLLECTION_NAME, client=client)
    print(f"✓ Initialized Hybrid docs collection: {DOCS_COLLECTION_NAME}")

    mistakes_store = init_vector_store(MISTAKES_COLLECTION_NAME, client=client)
    print(f"✓ Initialized Hybrid experience collection: {MISTAKES_COLLECTION_NAME}")

    recipes_store = init_vector_store(RECIPES_COLLECTION_NAME, client=client)
    print(f"✓ Initialized Hybrid recipes collection: {RECIPES_COLLECTION_NAME}")

    return docs_store, mistakes_store, recipes_store


def ingest_documents():
    """Run document ingestion on configured folders."""
    print("Starting Hybrid document ingestion...")
    if not INGESTION_FOLDERS:
        print("❌ No ingestion folders configured!")
        return

    docs_store = init_vector_store(DOCS_COLLECTION_NAME)
    load_folder_recursively(INGESTION_FOLDERS, docs_store, DOCS_COLLECTION_NAME)
    print("✅ Document ingestion completed!")


# ---------------------------------------------------------------------------
# Plugin Ingestion
# ---------------------------------------------------------------------------

def ingest_plugins(rebuild: bool = True):
    """Ingest curated Fiji plugin records from plugin_registry.json into Qdrant.

    Args:
        rebuild: If True, drop and recreate the collection to remove stale data.
                 If False, only update existing entries (may leave orphaned records).
    """
    registry_path = Path(__file__).resolve().parent / "plugin_registry.json"
    if not registry_path.exists():
        print(f"Plugin registry not found at {registry_path}")
        return

    with open(registry_path, "r", encoding="utf-8") as f:
        plugins = json.load(f)

    print(f"Loaded {len(plugins)} plugins from registry.")

    client = get_qdrant_client(path=QDRANT_DATA_PATH)

    # Drop and recreate collection for clean state
    if rebuild and client.collection_exists(collection_name=PLUGINS_COLLECTION_NAME):
        print(f"Dropping existing '{PLUGINS_COLLECTION_NAME}' collection to rebuild...")
        client.delete_collection(collection_name=PLUGINS_COLLECTION_NAME)

    vector_store = init_vector_store(PLUGINS_COLLECTION_NAME)

    # Build documents — embed all semantic fields for better retrieval
    docs = []
    for plugin in plugins:
        use_cases = ', '.join(plugin.get('typical_use_cases', []))
        page_content = (
            f"{plugin['name']}: {plugin['description']} "
            f"Category: {plugin['category']}. "
            f"Tags: {', '.join(plugin['tags'])}. "
            f"Input: {plugin.get('input_data', '')}. "
            f"Output: {plugin.get('output_data', '')}. "
            f"Use when: {plugin.get('use_when', '')}. "
            f"Do not use when: {plugin.get('do_not_use_when', '')}. "
            f"Typical use cases: {use_cases}."
        )
        doc = Document(
            page_content=page_content,
            metadata=plugin,
        )
        docs.append(doc)

    # Batch upsert
    vector_store.add_documents(docs)
    print(f"Ingested {len(docs)} plugin records into '{PLUGINS_COLLECTION_NAME}' collection.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("RAG System Setup (Hybrid + RRF)")
    print("===============================")

    # 1. Initialize
    initialize_rag_system()

    # 2. Ingest documents
    ingest_documents()

    # 3. Ingest plugin registry (uncomment to run)
    # ingest_plugins()
