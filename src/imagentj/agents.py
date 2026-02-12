import os
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from .prompts import imagej_coder_prompt, imagej_debugger_prompt, supervisor_prompt, python_analyst_prompt
from .tools import internet_search, inspect_all_ui_windows, run_script_safe, rag_retrieve_docs, inspect_java_class, save_coding_experience, rag_retrieve_mistakes, save_reusable_script, inspect_folder_tree, smart_file_reader, run_python_code, inspect_csv_header, extract_image_metadata, search_fiji_plugins, install_fiji_plugin, check_plugin_installed
gpt_key = os.getenv("OPENAI_API_KEY")

checkpointer_supervisor = MemorySaver()
checkpointer_imagej_coder = MemorySaver()
checkpointer_imagej_debugger = MemorySaver()
checkpointer_python_analyst = MemorySaver()

llm_gpt5 = ChatOpenAI(
    model = "gpt-5.2",
    verbose=True,
    api_key=gpt_key,
    temperature=0.,
    reasoning_effort="low",
)

llm_gpt5_nano = ChatOpenAI(
    model = "gpt-5.2",
    verbose=True,
    api_key=gpt_key,
    temperature=0.,
    reasoning_effort="low",
)

imagej_coder = {
    "name": "imagej_coder",

    "description": """Generates production-ready ImageJ/Fiji code (Groovy) to fulfill user-requested image analysis and automation tasks.
                    Selects the appropriate scripting language based on task requirements, enforces GUI-mode and ImageJ API constraints, hardcodes all parameters, and produces executable code suitable for automated execution.
                    Outputs code only, with explicit error handling and observable results.""",

    "system_prompt": imagej_coder_prompt,
    "middleware":[],
    "tools": [internet_search, inspect_java_class],
    "model":llm_gpt5_nano,
    "checkpointer":checkpointer_imagej_coder,
}



imagej_debugger = {
    "name": "imagej_debugger",
    "description": """"Diagnoses and repairs ImageJ/Fiji scripts (Groovy) that fail during execution.
                        Preserves the original language and intent, applies minimal corrective changes to resolve errors, and ensures compliance with ImageJ scripting constraints and execution requirements.
                        Outputs only the corrected, executable code without explanation.
                        ALWAYS provide the faulty code along with the error message to aid debugging.""",


    "system_prompt": imagej_debugger_prompt,
    "tools": [internet_search, inspect_java_class, rag_retrieve_mistakes],
    "model":llm_gpt5_nano,
    "middleware":[],
    "checkpointer":checkpointer_imagej_debugger,
}   


python_data_analyst = {
    "name": "python_data_analyst",
    "description": """Expert in biological statistics and publication-quality plotting. 
                    Uses Pandas, Scipy, and Seaborn to analyze ImageJ CSV outputs. 
                    Performs hypothesis testing and generates 300 DPI plots. Only produces Python code as output.""",
    "system_prompt": python_analyst_prompt, # From the previous response
    "tools": [inspect_csv_header],
    "model": llm_gpt5, # Use the stronger model for stats
    "middleware": [],
    "checkpointer": checkpointer_python_analyst,
}



def init_agent():

    supervisor = create_deep_agent(
    name="ImageJ_Supervisor",
    tools = [internet_search, inspect_all_ui_windows, run_script_safe, rag_retrieve_docs, save_coding_experience, rag_retrieve_mistakes, save_reusable_script, inspect_folder_tree, smart_file_reader, run_python_code, extract_image_metadata, search_fiji_plugins, install_fiji_plugin, check_plugin_installed],
    system_prompt=supervisor_prompt,
    subagents=[imagej_coder, imagej_debugger, python_data_analyst],
    middleware=[],
    model=llm_gpt5,
    debug=False,
    checkpointer=checkpointer_supervisor,
)
    return supervisor, checkpointer_supervisor