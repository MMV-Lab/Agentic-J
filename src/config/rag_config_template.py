# RAG (Retrieval-Augmented Generation) Configuration
# This file configures the vector databases and document ingestion settings

# Vector Database Settings
QDRANT_DATA_PATH = "path/to/qdrant/data"

# Collection Names
DOCS_COLLECTION_NAME = "BioimageAnalysisDocs"
MISTAKES_COLLECTION_NAME = "codingerrors_and_solutions"

# Document Ingestion Settings
# Folders to scan for documents to add to the RAG system
# The system will recursively scan these folders for PDFs, notebooks, code files, etc.
INGESTION_FOLDERS = [
    "path\to\bioimage_analysis_docs",
]

# Embedding Model Settings
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSION = 3072  # Dimension for text-embedding-3-large

# Hybrid Search Settings
ENABLE_HYBRID_SEARCH = True
SPARSE_MODEL = "naver/splade-cocondenser-ensembledistil"  # For keyword search
SPARSE_DIMENSION = 30522  # BM25/sparse vector dimension

# Chunking Settings - Enhanced for hybrid chunking
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
SMALL_CHUNK_SIZE = 512  # For code and technical content
LARGE_CHUNK_SIZE = 2000  # For narrative content

# Advanced Retrieval Settings
TOP_K_DENSE = 20  # Number of dense results to retrieve
TOP_K_SPARSE = 20  # Number of sparse results to retrieve
TOP_K_HYBRID = 10  # Final results after fusion
HYBRID_FUSION_WEIGHT = 0.7  # Weight for dense vs sparse (0.0 = pure sparse, 1.0 = pure dense)

# Query Expansion Settings
ENABLE_QUERY_EXPANSION = True
EXPANSION_TERMS = 3  # Number of expansion terms to generate

# Batch Processing
BATCH_SIZE = 50  # Number of chunks to process at once

# File Processing Settings
# Files/folders to skip during ingestion
SKIP_PATTERNS = [
    ".ipynb_checkpoints",
    "__pycache__",
    ".git",
    "node_modules",
    ".DS_Store"
]

# Supported file types for ingestion
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