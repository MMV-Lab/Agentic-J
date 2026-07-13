from config.rag_config import (
    QDRANT_DATA_PATH, DOCS_COLLECTION_NAME, PLUGINS_COLLECTION_NAME,
)

# Lazy single-collection RAG: only the static documentation store. The agent's
# learning memory (pitfalls + recipes) is file-based in learned_memory.py.
vec_store_docs = None
_rag_initialized = False


def _try_init_vector_stores():
    """Attempt to initialize the docs vector store. Returns silently if RAG deps are unavailable."""
    global vec_store_docs, _rag_initialized
    if _rag_initialized:
        return
    _rag_initialized = True
    try:
        from ..rag.RAG import init_vector_store
        from ..qdrant_client_singleton import get_qdrant_client
        client = get_qdrant_client(path=QDRANT_DATA_PATH)
        vec_store_docs = init_vector_store(collection_name=DOCS_COLLECTION_NAME, client=client)
        print("RAG system initialized successfully.")
    except Exception as e:
        print(f"RAG system unavailable (running without RAG): {e}")
        vec_store_docs = None


def get_vec_store_docs():
    """Get the docs vector store, initializing on first access."""
    _try_init_vector_stores()
    return vec_store_docs


def is_rag_available():
    """Check if the documentation RAG is available."""
    _try_init_vector_stores()
    return vec_store_docs is not None


def is_plugin_db_available():
    """Check if the fiji_plugins collection exists in Qdrant."""
    try:
        from ..qdrant_client_singleton import get_qdrant_client
        client = get_qdrant_client(path=QDRANT_DATA_PATH)
        return client.collection_exists(collection_name=PLUGINS_COLLECTION_NAME)
    except Exception:
        return False


def reset_vector_stores_for_test(docs=None):
    """Reset the lazy-init globals; tests use this to inject an in-memory store."""
    global vec_store_docs, _rag_initialized
    vec_store_docs = docs
    _rag_initialized = True
