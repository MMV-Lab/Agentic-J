# qdrant_client_singleton.py
from qdrant_client import QdrantClient

_qdrant_client = None

def get_qdrant_client(path: str):
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(path=path)
    return _qdrant_client
