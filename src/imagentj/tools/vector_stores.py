from config.rag_config import (
    QDRANT_DATA_PATH, DOCS_COLLECTION_NAME, MISTAKES_COLLECTION_NAME,
    RECIPES_COLLECTION_NAME, PLUGINS_COLLECTION_NAME,
)

# Initialize vector stores lazily - RAG is optional
vec_store_docs = None
vec_store_mistakes = None
vec_store_recipes = None
_rag_initialized = False

def _try_init_vector_stores():
    """Attempt to initialize vector stores. Returns silently if RAG dependencies are unavailable."""
    global vec_store_docs, vec_store_mistakes, vec_store_recipes, _rag_initialized
    if _rag_initialized:
        return
    _rag_initialized = True
    try:
        from ..rag.RAG import init_vector_store
        from ..qdrant_client_singleton import get_qdrant_client
        client = get_qdrant_client(path=QDRANT_DATA_PATH)
        vec_store_docs = init_vector_store(
            collection_name=DOCS_COLLECTION_NAME,
            client=client,
        )
        vec_store_mistakes = init_vector_store(
            collection_name=MISTAKES_COLLECTION_NAME,
            client=client,
        )
        vec_store_recipes = init_vector_store(
            collection_name=RECIPES_COLLECTION_NAME,
            client=client,
        )
        print("RAG system initialized successfully.")
    except Exception as e:
        print(f"RAG system unavailable (running without RAG): {e}")
        vec_store_docs = None
        vec_store_mistakes = None
        vec_store_recipes = None

def get_vec_store_docs():
    """Get the docs vector store, initializing on first access."""
    _try_init_vector_stores()
    return vec_store_docs

def get_vec_store_mistakes():
    """Get the mistakes vector store, initializing on first access."""
    _try_init_vector_stores()
    return vec_store_mistakes

def get_vec_store_recipes():
    """Get the recipes vector store, initializing on first access."""
    _try_init_vector_stores()
    return vec_store_recipes

def is_rag_available():
    """Check if the RAG system is available."""
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


def reset_vector_stores_for_test(docs=None, mistakes=None, recipes=None):
    """Reset the lazy-init globals; tests use this to inject in-memory stores."""
    global vec_store_docs, vec_store_mistakes, vec_store_recipes, _rag_initialized
    vec_store_docs = docs
    vec_store_mistakes = mistakes
    vec_store_recipes = recipes
    _rag_initialized = True