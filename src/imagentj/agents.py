import os
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from .prompts import imagej_coder_prompt, imagej_debugger_prompt, supervisor_prompt, python_analyst_prompt, qa_reporter_prompt
from .tools import internet_search, inspect_all_ui_windows, run_script_safe, rag_retrieve_docs, inspect_java_class, save_coding_experience, rag_retrieve_mistakes, save_reusable_script, inspect_folder_tree, smart_file_reader, run_python_code, inspect_csv_header, extract_image_metadata, search_fiji_plugins, install_fiji_plugin, check_plugin_installed, mkdir_copy, save_script, execute_script, get_script_info
from .tools import load_script, get_script_history, setup_analysis_workspace, save_markdown
from imagentj.tracker import UsageMetrics, MetricsSignalBridge, UsageTrackerCallback
from langchain.agents.middleware import SummarizationMiddleware, ContextEditingMiddleware, ClearToolUsesEdit

shared_metrics = UsageMetrics()
shared_bridge = MetricsSignalBridge()
shared_tracker = UsageTrackerCallback(shared_metrics, shared_bridge)

open_router_key = os.getenv("OPEN_ROUTER_API_KEY")

# Supervisor uses SqliteSaver so chat history survives container restarts.
# Falls back to MemorySaver if the package is not installed.
_CHATS_DIR = os.environ.get("CHAT_DATA_PATH", "/app/data/chats")
os.makedirs(_CHATS_DIR, exist_ok=True)
try:
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    _db_path = os.path.join(_CHATS_DIR, "checkpoints.db")
    _conn = sqlite3.connect(_db_path, check_same_thread=False)
    checkpointer_supervisor = SqliteSaver(_conn)
    print(f"[agents] Using SqliteSaver at {_db_path}")
except ImportError:
    checkpointer_supervisor = MemorySaver()
    print("[agents] WARNING: langgraph-checkpoint-sqlite not installed — using MemorySaver (history lost on restart)")

checkpointer_imagej_coder = MemorySaver()
checkpointer_imagej_debugger = MemorySaver()
checkpointer_python_analyst = MemorySaver()
checkpointer_qa_reporter = MemorySaver() 

list_apis = """
moonshotai/kimi-k2.5
google/gemini-3-flash-preview
anthropic/claude-opus-4.6
deepseek/deepseek-v3.2
openai/gpt-5.2
openai/gpt-5.3-codex
anthropic/claude-haiku-4.5
google/gemini-2.5-pro
google/gemini-3.1-flash-lite-preview
openai/gpt-5-nano
anthropic/claude-opus-4.6
anthropic/claude-sonnet-4.6
anthropic/claude-haiku-4.5
google/gemini-3-pro-preview
"""

open_models = """
qwen/qwen3-235b-a22b-2507
moonshotai/kimi-k2.5
z-ai/glm-5
deepseek/deepseek-v3.2
mistralai/mistral-small-3.2-24b-instruct
"""

# Supervisor: strongest model — orchestrates the full pipeline
llm_supervisor = ChatOpenAI(
    model = "google/gemini-3-pro-preview",
    verbose=True,
    api_key=open_router_key,
    base_url= "https://openrouter.ai/api/v1",
    temperature=0.,
    reasoning_effort="low",
    callbacks=[shared_tracker],
)

# Coders/Debugger: mid-tier — code generation needs reliable reasoning
llm_worker = ChatOpenAI(
    model = "google/gemini-3-pro-preview",
    verbose=True,
    api_key=open_router_key,
    base_url= "https://openrouter.ai/api/v1",
    temperature=0.,
    reasoning_effort="low",
    callbacks=[shared_tracker],
)

# Analyst: mid-tier for stats; fast for simple CSV inspection
llm_analyst = ChatOpenAI(
    model = "google/gemini-3.1-flash-lite-preview",
    verbose=True,
    api_key=open_router_key,
    base_url= "https://openrouter.ai/api/v1",
    temperature=0.,
    reasoning_effort="low",
    callbacks=[shared_tracker],
)

# Nano: genuinely small for trivial routing/validation tasks
llm_nano = ChatOpenAI(
    model = "anthropic/claude-haiku-4.5",
    verbose=True,
    api_key=open_router_key,
    base_url= "https://openrouter.ai/api/v1",
    temperature=0.,
    reasoning_effort="low",
    callbacks=[shared_tracker],
)



imagej_coder = {
    "name": "imagej_coder",

    "description": """Generates production-ready ImageJ/Fiji code (Groovy) and manages its integration into the project repository. 
                    The agent is responsible for writing scripts via 'save_script' (including detailed functional documentation for the Supervisor), 
                    reviewing existing project code with 'load_script', and consulting 'get_script_history' to avoid repeating failures. 
                    It must ALWAYS report the absolute path of the saved script as its final output.""",

    "system_prompt": imagej_coder_prompt,
    "middleware":[ContextEditingMiddleware(
                 edits=[
                ClearToolUsesEdit(
                    trigger=50000,
                    keep=10,
                    clear_tool_inputs=False,
                    exclude_tools=[],
                    placeholder="[cleared]",
                ),],)],
    "tools": [internet_search, inspect_java_class, save_script, load_script, get_script_history],
    "model":llm_worker,
    "checkpointer":checkpointer_imagej_coder,
}



imagej_debugger = {
    "name": "imagej_debugger",
    "description": """Diagnoses and repairs ImageJ/Fiji scripts (Groovy) that fail during execution. 
                    It uses 'load_script' to retrieve the faulty code and 'get_script_history' to avoid 
                    repeating unsuccessful fixes. It applies surgical corrections, preservation of intent, 
                    and ensures compliance with ImageJ constraints. The agent commits the fix via 
                    'save_script', providing the 'error_context' to update the versioned history, 
                    and reports the absolute path of the repaired script.""",

    "system_prompt": imagej_debugger_prompt,
    "tools": [internet_search, inspect_java_class, rag_retrieve_mistakes, save_script, load_script, get_script_history, get_script_info],
    "model":llm_worker,
    "middleware":[ContextEditingMiddleware(
                 edits=[
                ClearToolUsesEdit(
                    trigger=50000,
                    keep=10,
                    clear_tool_inputs=False,
                    exclude_tools=[],
                    placeholder="[cleared]",
                ),],)],
    "checkpointer":checkpointer_imagej_debugger,
}   


python_data_analyst = {
    "name": "python_data_analyst",
    "description": """Expert in biological statistics and publication-quality plotting. 
                    Uses Pandas, Scipy, and Seaborn to analyze ImageJ CSV outputs. 
                    Manages Python scripts via 'save_script', 'load_script', and 'get_script_history' 
                    to maintain a modular, versioned analysis pipeline. Performs 
                    rigorous hypothesis testing (Stage 1) and generates 300 DPI plots (Stage 2) 
                    while documenting statistical assumptions in the project dictionary.""",
    "system_prompt": python_analyst_prompt,
    "tools": [inspect_csv_header, save_script, load_script, get_script_history, load_script, get_script_info],
    "model": llm_worker, 
    "middleware": [],
    "checkpointer": checkpointer_python_analyst,
}


qa_reporter = {
    "name": "qa_reporter",

    "description": """Automatically audits a completed project folder and generates two files:
                    (1) QA_Checklist_Report.md — pass/fail audit against image-analysis publication 
                    standards (Minimal / Recommended / Ideal levels).
                    (2) Workflow_Documentation.md — a pre-filled documentation template inferred 
                    from the project's scripts, CSVs, and figures.
                    
                    WHEN TO CALL: At the end of every project, after all scripts have run 
                    successfully and results are saved.
                    
                    INPUT REQUIRED: The absolute path to the project root folder 
                    (e.g., /app/data/project_name/).
                    
                    OUTPUT: Absolute paths to QA_Checklist_Report.md and 
                    Workflow_Documentation.md saved inside the project folder.""",

    "system_prompt": qa_reporter_prompt,
    "middleware": [],
    "tools": [
        inspect_folder_tree,   # discovers project structure
        smart_file_reader,     # reads scripts, CSVs, logs
        get_script_info,       # reads script documentation from dictionary
        save_markdown,           # writes the two output markdown files
        inspect_csv_header,
        load_script,
    ],
    "model": llm_nano,
    "checkpointer": checkpointer_qa_reporter,
}




def init_agent():

    fs_backend = FilesystemBackend(
    root_dir="/app/data/", 
    virtual_mode= False  # False = access real files, True = virtual sandbox
   )

    supervisor = create_deep_agent(
    name="ImageJ_Supervisor",
    tools = [internet_search, inspect_all_ui_windows, rag_retrieve_docs, save_coding_experience, rag_retrieve_mistakes, save_reusable_script, inspect_folder_tree, smart_file_reader, extract_image_metadata, search_fiji_plugins, install_fiji_plugin, check_plugin_installed, mkdir_copy, inspect_csv_header, execute_script, get_script_info, setup_analysis_workspace, save_markdown],
    system_prompt=supervisor_prompt,
    subagents=[imagej_coder, imagej_debugger, python_data_analyst], #, qa_reporter],
    middleware=[SummarizationMiddleware(
                model=llm_nano,
                trigger=("tokens", 50000),
                keep=("messages", 20),
                ),
                ContextEditingMiddleware(
                 edits=[
                ClearToolUsesEdit(
                    trigger=50000,
                    keep=10,
                    clear_tool_inputs=False,
                    exclude_tools=[],
                    placeholder="[cleared]",
                ),],)
                ],
    model=llm_supervisor,
    debug=False,
    backend=fs_backend,
    checkpointer=checkpointer_supervisor,
    skills = ["/app/skills/"],
)
    return supervisor, checkpointer_supervisor, shared_metrics, shared_bridge, shared_tracker