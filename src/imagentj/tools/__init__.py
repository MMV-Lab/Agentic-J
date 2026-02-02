import os

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "../../scripts/saved_scripts")

# Tools package - re-export all tools for backward compatibility
from .file_tools import inspect_folder_tree, save_reusable_script, smart_file_reader
from .rag_tools import rag_retrieve_docs, rag_retrieve_mistakes, save_coding_experience
from .script_tools import run_script_safe
from .imagej_tools import ask_user, load_image_ij, inspect_all_ui_windows
from .general_tools import internet_search, inspect_java_class
from .analyst_tools import run_python_code, inspect_csv_header
from .middleware import SafeToolLoggerMiddleware, TodoDisplayMiddleware

# Import vector stores from vector_stores module
from .vector_stores import vec_store_docs, vec_store_mistakes

__all__ = [
    'inspect_folder_tree', 'save_reusable_script', 'smart_file_reader',
    'rag_retrieve_docs', 'rag_retrieve_mistakes', 'save_coding_experience',
    'run_script_safe', 'ask_user', 'load_image_ij', 'inspect_all_ui_windows',
    'internet_search', 'inspect_java_class',
    'SafeToolLoggerMiddleware', 'TodoDisplayMiddleware',
    'vec_store_docs', 'vec_store_mistakes', 'run_python_code', 'inspect_csv_header'
]