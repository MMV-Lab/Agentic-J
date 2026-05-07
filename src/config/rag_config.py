import os
from pathlib import Path

# Get the directory where this project is located
# This ensures it works whether you are in Docker or on the host
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Use an environment variable if it exists, otherwise use a local project folder
#QDRANT_DATA_PATH = "/mnt/eternus/users/Lukas/ImagentJ/Agent/Imagent_J/qdrant_data"

QDRANT_DATA_PATH = "/app/qdrant_data"

# Create the directory automatically if it's local
if not os.path.exists(QDRANT_DATA_PATH) and not QDRANT_DATA_PATH.startswith("/app"):
    os.makedirs(QDRANT_DATA_PATH, exist_ok=True)

# Collection Names
DOCS_COLLECTION_NAME = "BioimageAnalysisDocs"
MISTAKES_COLLECTION_NAME = "codingerrors_and_solutions"
RECIPES_COLLECTION_NAME = "code_recipes"
PLUGINS_COLLECTION_NAME = "fiji_plugins"  # Added as it was in your import error

# Retrieval thresholds — fused RRF scores below this are considered "no real match".
# RRF scores from a fusion of N queries with k=60 typically land in [1/61, N/60] ~= [0.016, N*0.017].
# A single doc with rank-0 in two of three queries scores ~0.033. We treat anything
# under MIN_RECIPE_SCORE / MIN_MISTAKE_SCORE as too weak to surface.
MIN_MISTAKE_SCORE = 0.020
MIN_RECIPE_SCORE = 0.020

# Pre-save dedup similarity threshold (cosine, dense). Above this we consider the
# candidate a near-duplicate and increment times_seen on the existing point.
DEDUP_SIMILARITY_THRESHOLD = 0.92

# Document Ingestion Settings
# In your docker-compose, you mapped ${IMAGE_DATA_DIR:-./data} to /data
# So we point the system to /data inside the container.
INGESTION_FOLDERS = [
    "/app/data/knowledge_database",  # This is the path inside the container
]
    # "/mnt/eternus/users/Lukas/ImagentJ/Agent/Imagent_J/data/knowledge_database",
# Embedding Model Settings
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSION = 1024

# Hybrid Search Settings
ENABLE_HYBRID_SEARCH = True
# Note: Ensure these models are accessible or downloaded during build
SPARSE_MODEL = "naver/splade-cocondenser-ensembledistil"
SPARSE_DIMENSION = 30522 

# Chunking Settings
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
SMALL_CHUNK_SIZE = 512 
LARGE_CHUNK_SIZE = 2000 

# Advanced Retrieval Settings
TOP_K_DENSE = 20
TOP_K_SPARSE = 20
TOP_K_HYBRID = 10
HYBRID_FUSION_WEIGHT = 0.7

# Query Expansion Settings
ENABLE_QUERY_EXPANSION = True
EXPANSION_TERMS = 3

# Batch Processing
BATCH_SIZE = 50

# File Processing Settings
SKIP_PATTERNS = [
    ".ipynb_checkpoints",
    "__pycache__",
    ".git",
    "node_modules",
    ".DS_Store"
]

# Supported file types
SUPPORTED_EXTENSIONS = {
    'documents': ['.pdf', '.md', '.txt'],
    'code': ['.py', '.js', '.java', '.groovy'],
    'notebooks': ['.ipynb']
}

# Content Type Chunking Strategy
CONTENT_CHUNKING_STRATEGY = {
    'code': {'chunk_size': SMALL_CHUNK_SIZE, 'overlap': 100, 'strategy': 'code_aware'},
    'documents': {'chunk_size': LARGE_CHUNK_SIZE, 'overlap': 300, 'strategy': 'semantic'},
    'notebooks': {'chunk_size': CHUNK_SIZE, 'overlap': 200, 'strategy': 'cell_based'},
    'default': {'chunk_size': CHUNK_SIZE, 'overlap': CHUNK_OVERLAP, 'strategy': 'recursive'}
}