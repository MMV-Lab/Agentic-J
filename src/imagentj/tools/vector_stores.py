from ..rag.RAG import init_vector_store
from config.rag_config import QDRANT_DATA_PATH, DOCS_COLLECTION_NAME, MISTAKES_COLLECTION_NAME
from ..qdrant_client_singleton import get_qdrant_client

# Initialize vector stores
vec_store_docs = init_vector_store(
    collection_name=DOCS_COLLECTION_NAME,
    client=get_qdrant_client(path=QDRANT_DATA_PATH)
)

vec_store_mistakes = init_vector_store(
    collection_name=MISTAKES_COLLECTION_NAME,
    client=get_qdrant_client(path=QDRANT_DATA_PATH),
)