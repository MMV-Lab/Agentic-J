from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from prompts import imagej_coder_prompt, imagej_debugger_prompt, supervisor_prompt
from tools import internet_search, inspect_all_ui_windows, run_script_safe, rag_retrieve_docs, inspect_java_class, save_coding_experience, rag_retrieve_mistakes, save_reusable_script, inspect_folder_tree
from keys import gpt_key


checkpointer = MemorySaver()

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

    "description": """Generates production-ready ImageJ/Fiji code (Groovy, Java, or ImageJ Macro) to fulfill user-requested image analysis and automation tasks.
                    Selects the appropriate scripting language based on task requirements, enforces GUI-mode and ImageJ API constraints, hardcodes all parameters, and produces executable code suitable for automated execution.
                    Outputs code only, with explicit error handling and observable results.""",

    "system_prompt": imagej_coder_prompt,
    "middleware":[],
    "tools": [internet_search, inspect_java_class],
    "model":llm_gpt5_nano,
    "checkpointer":checkpointer,
}



imagej_debugger = {
    "name": "imagej_debugger",
    "description": """"Diagnoses and repairs ImageJ/Fiji scripts (Groovy, Java, or ImageJ Macro) that fail during execution.
                        Preserves the original language and intent, applies minimal corrective changes to resolve errors, and ensures compliance with ImageJ scripting constraints and execution requirements.
                        Outputs only the corrected, executable code without explanation.
                        ALWAYS provide the faulty code along with the error message to aid debugging.""",


    "system_prompt": imagej_debugger_prompt,
    "tools": [internet_search, inspect_java_class, rag_retrieve_mistakes],
    "model":llm_gpt5_nano,
    "middleware":[],
    "checkpointer":checkpointer,
}   




def init_agent():

    supervisor = create_deep_agent(
    name="ImageJ_Supervisor",
    tools = [internet_search, inspect_all_ui_windows, run_script_safe, rag_retrieve_docs, save_coding_experience, rag_retrieve_mistakes, save_reusable_script, inspect_folder_tree],
    system_prompt=supervisor_prompt,
    subagents=[imagej_coder, imagej_debugger],
    middleware=[],
    model=llm_gpt5,
    debug=False,
    checkpointer=checkpointer,
)
    return supervisor, checkpointer