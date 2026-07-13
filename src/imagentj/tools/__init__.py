import os

# Tools package - re-export all tools for backward compatibility
from .file_tools import inspect_folder_tree, smart_file_reader, mkdir_copy, setup_analysis_workspace, save_markdown
from .rag_tools import rag_retrieve_docs
from .learned_memory import (
    recall, core_pitfalls, core_recipes, on_success, register_pending_lesson,
    library_add_pitfall, library_add_recipe, library_remove, library_set_core,
)
from .script_tools import run_script_safe, save_script, edit_script, copy_file, execute_script, get_script_info, load_script, get_script_history
from .imagej_tools import ask_user, load_image_ij, inspect_all_ui_windows, extract_image_metadata, capture_plugin_dialog, set_dialog_vision_llm, show_in_imagej_gui, close_imagej_windows
from .general_tools import internet_search, inspect_java_class
from .analyst_tools import run_python_code, inspect_csv_header
from .plugin_tools import search_fiji_plugins, install_fiji_plugin, check_plugin_installed
from .middleware import SafeToolLoggerMiddleware, TodoDisplayMiddleware, NarrationReminderMiddleware, PhaseGuardMiddleware
# from .vision_tools import capture_ij_window, build_compilation, analyze_image, set_vision_llm  # VLM disabled
from .state_ledger import update_state_ledger, read_state_ledger, set_ledger_metadata, get_ledger_context
from .environment_tools import check_environment
# Generic MCP host adapter — exposes configured MCP servers (e.g. napari-mcp)
# as mcp__<server>__<tool> LangChain tools, plus raw diagnostics.
from .mcp_host_tools import get_mcp_tools, mcp_list_servers, mcp_list_tools, mcp_call_tool

# Lazy accessors for vector stores (RAG is optional)
from .vector_stores import (
    get_vec_store_docs, is_rag_available, is_plugin_db_available,
)

__all__ = [
    'inspect_folder_tree', 'smart_file_reader',
    'rag_retrieve_docs', 'recall', 'core_pitfalls', 'core_recipes',
    'on_success', 'register_pending_lesson',
    'library_add_pitfall', 'library_add_recipe', 'library_remove', 'library_set_core',
    'run_script_safe', 'ask_user', 'load_image_ij', 'show_in_imagej_gui', 'inspect_all_ui_windows', 'extract_image_metadata', 'capture_plugin_dialog', 'close_imagej_windows',
    'internet_search', 'inspect_java_class',
    'search_fiji_plugins', 'install_fiji_plugin', 'check_plugin_installed',
    'SafeToolLoggerMiddleware', 'TodoDisplayMiddleware', 'NarrationReminderMiddleware', 'PhaseGuardMiddleware',
    'get_vec_store_docs', 'is_rag_available', 'is_plugin_db_available',
    'set_dialog_vision_llm',
    'run_python_code', 'inspect_csv_header', 'mkdir_copy','save_script', 'edit_script', 'copy_file', 'execute_script', 'get_script_info', 'load_script', 'get_script_history',
    'setup_analysis_workspace', 'save_markdown',
    'set_vision_llm', 'capture_ij_window', 'build_compilation', 'analyze_image',
    'update_state_ledger', 'read_state_ledger', 'set_ledger_metadata', 'get_ledger_context',
    'check_environment',
    'get_mcp_tools', 'mcp_list_servers', 'mcp_list_tools', 'mcp_call_tool',
]