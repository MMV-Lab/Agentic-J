import os

# Tools package - re-export all tools for backward compatibility
from .file_tools import inspect_folder_tree, smart_file_reader, mkdir_copy, setup_analysis_workspace, save_markdown
from .rag_tools import rag_retrieve_docs
from .concepts import recall_concepts
from .learned_memory import (
    recall, core_pitfalls, core_recipes, on_success, register_pending_lesson,
    library_add_pitfall, library_add_recipe, library_remove, library_set_core,
)
from .script_tools import run_script_safe, save_script, edit_script, copy_file, execute_script, get_script_info, load_script, get_script_history
from .imagej_tools import ask_user, load_image_ij, inspect_all_ui_windows, extract_image_metadata, capture_plugin_dialog, estimate_cellpose_diameter_manual, estimate_cellpose_diameter_auto, merge_cellpose_diameter_runs, set_dialog_vision_llm, show_in_imagej_gui, close_imagej_windows
from .general_tools import internet_search, inspect_java_class
from .analyst_tools import run_python_code, inspect_csv_header, summarize_deliverables
from .plugin_tools import search_fiji_plugins, install_fiji_plugin, check_plugin_installed
from .middleware import (
    SafeToolLoggerMiddleware,
    TodoDisplayMiddleware,
    NarrationReminderMiddleware,
    PhaseGuardMiddleware,
    ToolOutputLimitMiddleware,
    VisionOptionMiddleware,
    BioRefusalRetryMiddleware,
    ModeMiddleware, ModeSpec, AgentModeState,
)
# Rebase note (2026-08-03): the educator branch had commented this block out with
# "# VLM disabled". Keeping it ACTIVE — the VLM-as-judge work landed on main after
# the branch was cut, and disabling it here would silently revert that.
from .vision_tools import (
    capture_ij_window,
    capture_image_file_via_fiji,
    prepare_image_source_for_vlm,
    build_mask_overlay,
    build_compilation,
    analyze_image,
    set_vision_llm,
)
from .tutor_tools import (
    list_curriculum, load_chapter, load_track, show_figure, list_sample_images,
    list_practicals, reveal_solution, update_course_progress, set_course_plan, set_mode,
)
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
    'rag_retrieve_docs', 'recall_concepts', 'recall', 'core_pitfalls', 'core_recipes',
    'on_success', 'register_pending_lesson',
    'library_add_pitfall', 'library_add_recipe', 'library_remove', 'library_set_core',
    'run_script_safe', 'ask_user', 'load_image_ij', 'show_in_imagej_gui', 'inspect_all_ui_windows', 'extract_image_metadata', 'capture_plugin_dialog', 'estimate_cellpose_diameter_manual', 'estimate_cellpose_diameter_auto', 'merge_cellpose_diameter_runs', 'close_imagej_windows',
    'internet_search', 'inspect_java_class',
    'search_fiji_plugins', 'install_fiji_plugin', 'check_plugin_installed',
    'SafeToolLoggerMiddleware', 'TodoDisplayMiddleware', 'NarrationReminderMiddleware', 'PhaseGuardMiddleware', 'ToolOutputLimitMiddleware', 'VisionOptionMiddleware',
    'ModeMiddleware', 'ModeSpec', 'AgentModeState',
    'list_curriculum', 'load_chapter', 'load_track', 'show_figure', 'list_sample_images',
    'list_practicals', 'reveal_solution', 'update_course_progress', 'set_course_plan', 'set_mode',
    # get_vec_store_mistakes / get_vec_store_recipes were exported by the educator
    # branch but no longer exist on main (only get_vec_store_docs remains), so they
    # are dropped here rather than carried forward as broken exports.
    'get_vec_store_docs', 'is_rag_available', 'is_plugin_db_available',
    'set_dialog_vision_llm',
    'run_python_code', 'inspect_csv_header', 'summarize_deliverables', 'mkdir_copy','save_script', 'edit_script', 'copy_file', 'execute_script', 'get_script_info', 'load_script', 'get_script_history',
    'setup_analysis_workspace', 'save_markdown',
    'set_vision_llm', 'capture_ij_window', 'capture_image_file_via_fiji',
    'prepare_image_source_for_vlm', 'build_mask_overlay', 'build_compilation', 'analyze_image',
    'update_state_ledger', 'read_state_ledger', 'set_ledger_metadata', 'get_ledger_context',
    'check_environment',
    'get_mcp_tools', 'mcp_list_servers', 'mcp_list_tools', 'mcp_call_tool',
]
