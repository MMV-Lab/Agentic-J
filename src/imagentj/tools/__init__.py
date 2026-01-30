import os

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "../../scripts/saved_scripts")

# Tools package - re-export all tools for backward compatibility
from .file_tools import inspect_folder_tree, save_reusable_script, smart_file_reader
from .rag_tools import rag_retrieve_docs, rag_retrieve_mistakes, save_coding_experience
from .script_tools import run_script_safe
from .imagej_tools import ask_user, load_image_ij, inspect_all_ui_windows, extract_image_metadata
from .general_tools import internet_search, inspect_java_class
from .middleware import SafeToolLoggerMiddleware, TodoDisplayMiddleware

# Lazy accessors for vector stores (RAG is optional)
from .vector_stores import get_vec_store_docs, get_vec_store_mistakes, is_rag_available

__all__ = [
    'inspect_folder_tree', 'save_reusable_script', 'smart_file_reader',
    'rag_retrieve_docs', 'rag_retrieve_mistakes', 'save_coding_experience',
    'run_script_safe', 'ask_user', 'load_image_ij', 'inspect_all_ui_windows', 'extract_image_metadata',
    'internet_search', 'inspect_java_class',
    'SafeToolLoggerMiddleware', 'TodoDisplayMiddleware',
    'get_vec_store_docs', 'get_vec_store_mistakes', 'is_rag_available'
]