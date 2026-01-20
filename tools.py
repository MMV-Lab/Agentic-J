from langchain.tools import tool
import jpype
from ddgs import DDGS
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langchain.agents.middleware import TodoListMiddleware
from imagej_context import get_ij
from jpype import JClass
from langchain_core.documents import Document

from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from keys import gpt_key
import difflib
import RAG.loaders
from qdrant_client_singleton import get_qdrant_client
import re
import os 
import json

SCRIPTS_DIR = "saved_scripts"

def sanitize_filename(name: str) -> str:
    """Converts a script name into a valid filename."""
    # Remove invalid characters, replace spaces with underscores
    clean = re.sub(r'[<>:"/\\|?*]', '', name)
    return clean.replace(' ', '_')

@tool("save_reusable_script")
def save_reusable_script(name: str, code: str, description: str, inputs_required: str) -> str:
    """
    Saves a working script to the permanent user library folder.
    Creates two files: a .groovy file for the code and a .json file for metadata.
    
    Args:
        name: A short, descriptive title (e.g., "Nuclei Segmentation via StarDist").
        code: The complete, executable Groovy or Java code.
        description: A summary of what the script does.
        inputs_required: Instructions for the user (e.g., "Open a 2D Tiff image").
    """
    
    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)
        
    safe_name = sanitize_filename(name)
    
    # 1. Save the code file
    code_path = os.path.join(SCRIPTS_DIR, f"{safe_name}.groovy")
    with open(code_path, "w", encoding="utf-8") as f:
        f.write(code)
        
    # 2. Save the metadata file
    meta_path = os.path.join(SCRIPTS_DIR, f"{safe_name}.json")
    metadata = {
        "name": name,
        "description": description,
        "inputs": inputs_required,
        "language": "groovy",
        "script_file": f"{safe_name}.groovy"
    }
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)
        
    return f"Script saved successfully as '{safe_name}.groovy' in the '{SCRIPTS_DIR}' folder."


def init_vec_store(
    collection_name: str,
    path: str,
):
    client = get_qdrant_client(path=path)

    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=OpenAIEmbeddings(api_key=gpt_key, model="text-embedding-3-large"),
    )

    # Hybrid search
    return vectorstore

vec_store_docs = init_vec_store(
    collection_name="BioimageAnalysisDocs",
    path="./qdrant_data",
)


@tool("rag_retrieve")
def rag_retrieve_docs(query: str) -> str:
    """
    Retrieve relevant context from the document RAG.
    Input should be a precise information-seeking query.
    """

    retriever = vec_store_docs.as_retriever(
        search_type="mmr",  # or "similarity"
        search_kwargs={
            "k": 8,
            "fetch_k": 30,
        },
    )
    docs = retriever.invoke(query)

    results = []
    for d in docs:
        results.append(
            {
                "content": d.page_content,
                "source": d.metadata.get("source"),
                "page": d.metadata.get("page"),
            }
        )

    return results


vec_store_mistakes = init_vec_store(
    path="./qdrant_data",
    collection_name="codingerrors_and_solutions",
)

@tool("rag_retrieve_mistakes")
def rag_retrieve_mistakes(query: str) -> str:
    """
    Retrieve relevant context from the coding errors and solutions RAG.
    Input should be a precise information-seeking query.
    """
    retriever = vec_store_mistakes.as_retriever(
        search_type="mmr",  # or "similarity"
        search_kwargs={
            "k": 8,
            "fetch_k": 30,
        },
    )
    docs = retriever.invoke(query)

    results = []
    for d in docs:
        results.append(
            {
                "content": d.page_content,
                "source": d.metadata.get("source"),
                "page": d.metadata.get("page"),
            }
        )

    return results



@tool("save_coding_experience")
def save_coding_experience(error_description: str, failed_code: str, working_code: str, class_involved: str):
    """
    Saves a successful fix to the persistent Memory RAG. 
    Use this after the debugger fixes a script to prevent the error from happening again.
    """
    # Create a structured text block for the embedding
    content = f"""
    PROBLEM: {error_description}
    FAILED CODE: {failed_code}
    WORKING SOLUTION: 
    {working_code}
    CLASS INVOLVED: {class_involved}
    """
    
    doc = Document(
        page_content=content,
        metadata={
            "type": "lesson_learned",
            "class": class_involved,
            "error_type": "MissingMethod" if "MissingMethod" in error_description else "Logic"
        }
    )
    
    # Use your existing vector_store logic to add this to a NEW collection
    # Recommended collection name: "AgentMemory"
    vec_store_mistakes.add_documents([doc])
    return "Experience saved successfully. I will remember this for future tasks."

def run_groovy_script(script: str, ij) -> str:
    """Execute Groovy scripts in ImageJ/Fiji."""

    System = jpype.JClass("java.lang.System")
    ByteArrayOutputStream = jpype.JClass("java.io.ByteArrayOutputStream")
    PrintStream = jpype.JClass("java.io.PrintStream")

    out_stream = ByteArrayOutputStream()
    err_stream = ByteArrayOutputStream()

    original_out = System.out
    original_err = System.err

    System.setOut(PrintStream(out_stream))
    System.setErr(PrintStream(err_stream))

    try:
        result = ij.py.run_script("Groovy", script)

        stdout = out_stream.toString()
        stderr = err_stream.toString()

        status = "SUCCESS"
        if stderr.strip():
            status = "WARNING"

        return (
            f"STATUS: {status}\n"
            "LANGUAGE: Groovy\n"
            "STDOUT:\n"
            f"{stdout}\n"
            "STDERR:\n"
            f"{stderr}\n"
            "RESULT:\n"
            f"{result}"
        )

    except Exception as e:
        return (
            "STATUS: ERROR\n"
            "LANGUAGE: Groovy\n"
            "STDOUT:\n\n"
            "STDERR:\n"
            f"{str(e)}\n{err_stream.toString()}\n"
            "RESULT:\nnull"
        )

    finally:
        System.setOut(original_out)
        System.setErr(original_err)



def run_java_script(script: str, ij) -> str:
    """Execute Java scripts via ImageJ ScriptService."""

    System = jpype.JClass("java.lang.System")
    ByteArrayOutputStream = jpype.JClass("java.io.ByteArrayOutputStream")
    PrintStream = jpype.JClass("java.io.PrintStream")

    out_stream = ByteArrayOutputStream()
    err_stream = ByteArrayOutputStream()

    original_out = System.out
    original_err = System.err

    System.setOut(PrintStream(out_stream))
    System.setErr(PrintStream(err_stream))

    try:
        result = ij.py.run_script("Java", script)

        stdout = out_stream.toString()
        stderr = err_stream.toString()

        status = "SUCCESS"
        if stderr.strip():
            status = "WARNING"

        return (
            f"STATUS: {status}\n"
            "LANGUAGE: Java\n"
            "STDOUT:\n"
            f"{stdout}\n"
            "STDERR:\n"
            f"{stderr}\n"
            "RESULT:\n"
            f"{result}"
        )

    except Exception as e:
        return (
            "STATUS: ERROR\n"
            "LANGUAGE: Java\n"
            "STDOUT:\n\n"
            "STDERR:\n"
            f"{str(e)}\n{err_stream.toString()}\n"
            "RESULT:\nnull"
        )

    finally:
        System.setOut(original_out)
        System.setErr(original_err)

def wrap_macro(user_macro: str) -> str:
    return f"""
setBatchMode(true);
call("ij.IJ.log", "__MACRO_START__");

{user_macro}

call("ij.IJ.log", "__MACRO_END__");
"""



def run_imagej_macro(macro: str, ij) -> str:
    try:
        ij.IJ.log("\\Clear")

        wrapped = wrap_macro(macro)

        print("Running wrapped macro:", wrapped)

        ij.IJ.runMacro(wrapped)

        log = ij.IJ.getLog() or ""

        if "__MACRO_START__" in log and "__MACRO_END__" not in log:
            status = "ERROR"
            stderr = "Macro aborted during execution"
        elif "Error:" in log or "ERROR:" in log:
            status = "WARNING"
            stderr = log
        else:
            status = "SUCCESS"
            stderr = ""

        return (
            f"STATUS: {status}\n"
            "LANGUAGE: Macro\n"
            "STDOUT:\n"
            f"{log}\n"
            "STDERR:\n"
            f"{stderr}\n"
            "RESULT:\nnull"
        )

    except Exception as e:
        return (
            "STATUS: ERROR\n"
            "LANGUAGE: Macro\n"
            "STDOUT:\n\n"
            "STDERR:\n"
            f"{str(e)}\n"
            "RESULT:\nnull"
        )



@tool
def run_script_safe(language: str, code: str, max_retries: int = 3) -> str:
    """
    Unified safe execution tool for the supervisor.

    This tool executes ImageJ/Fiji scripts safely in the GUI, handling:

      - Window snapshot & automatic cleanup on failure
      - Retry handling (up to `max_retries`)
      - Only shows images after successful execution

    Supported languages (determined automatically from the `language` argument):
      - "groovy"  : Groovy scripts
      - "java"    : Java scripts
     

    Usage notes for the supervisor:
      - The coder and debugger agents only generate or repair code; they
        never execute scripts.
      - This tool MUST be used to execute all ImageJ/Fiji scripts from
        generated code.
      - On execution failure, new windows created by the script will
        automatically be closed before retrying.
      - Only successful execution leaves windows visible for the user.

    Parameters:
      language (str) : "groovy", "java"
      code (str)     : The script code to execute
      max_retries (int, optional) : Number of times to retry on failure

    Returns:
      str : Output log from script execution, including any error messages.
    """
    ij = get_ij()
    
    WindowManager = JClass("ij.WindowManager")
    
    # Map language to the original execution tool
    tool_map = {
        "groovy": run_groovy_script,
        "java": run_java_script,
    }
    
    if language.lower() not in tool_map:
        raise ValueError(f"Unsupported language: {language}")

    exec_tool = tool_map[language.lower()]
    last_output = ""
    
    
        # Snapshot open windows
    windows_before = set(WindowManager.getImageTitles())
    
    # Run the script
    try:
        output = exec_tool(code, ij)
    except Exception as e:
        output = f"Exception during execution: {e}"
    
    last_output = output
    
    # Snapshot new windows
    windows_after = set(WindowManager.getImageTitles())
    new_windows = windows_after - windows_before
    
    # Determine failure
    failed = any(k in output.lower() for k in ["error", "exception", "failed"])
    
    if failed:
        # Close windows created during failed attempt
        for title in new_windows:
            imp = WindowManager.getImage(title)
            if imp:
                imp.changes = False
                imp.close()
       
            print("Execution failed")
            return output
    else:
        # Success: leave windows visible
        return output

    return last_output



@tool
def ask_user(prompt: str) -> str:
    """
    Ask the user a question and return their input.
    Always ask in a way that a biologists without programming experience can understand.
    """
    return input(f"🖐 USER INPUT REQUIRED: {prompt}\n> ")



# --- Tool 3: Load Image ---

@tool
def load_image_ij(path: str)  -> object:
    """Load an image from a given path using ImageJ.
    
    Args:
        path (str): The file path to the image.
        
    Returns:
        []."""
    
    global image

    ij = get_ij()

    image = ij.io().open(path)
    return "Loaded image from " + path


@tool
def inspect_all_ui_windows():
    """
    Inspected everything visible in the ImageJ UI:
    1. Image Windows (Metadata & Stats)
    2. Results Tables (Row/Column counts)
    3. The Log window and ROI Manager
    """
    ij = get_ij()
    
    # Correct way to import Java classes in PyImageJ
    from scyjava import jimport
    WindowManager = jimport('ij.WindowManager')
    ResultsTable = jimport('ij.measure.ResultsTable')
    RoiManager = jimport('ij.plugin.frame.RoiManager')
    Frame = jimport('java.awt.Frame')

    all_inspections = {
        "images": [],
        "tables_and_text": []
    }

    # --- 1. Inspect Image Windows ---
    image_ids = WindowManager.getIDList()
    if image_ids:
        for img_id in image_ids:
            imp = WindowManager.getImage(img_id)
            try:
                # Convert ImagePlus to Dataset for stats
                dataset = ij.py.to_dataset(imp)
                
                min_val = ij.op().stats().min(dataset).getRealDouble()
                max_val = ij.op().stats().max(dataset).getRealDouble()
                
                all_inspections["images"].append({
                    "title": imp.getTitle(),
                    "dimensions": f"{imp.getWidth()}x{imp.getHeight()}x{imp.getNSlices()}",
                    "stats": {"min": min_val, "max": max_val},
                    "bit_depth": imp.getBitDepth()
                })
            except Exception as e:
                all_inspections["images"].append({"title": imp.getTitle(), "error": str(e)})

    # --- 2. Inspect Non-Image Windows ---
    all_frames = Frame.getFrames()
    for frame in all_frames:
        if frame.isVisible():
            title = frame.getTitle()
            
            if title == "Results":
                rt = ResultsTable.getResultsTable()
                all_inspections["tables_and_text"].append({
                    "type": "Results Table",
                    "rows": rt.size(),
                    "columns": rt.getLastColumn() + 1
                })
            elif title == "ROI Manager":
                rm = RoiManager.getInstance()
                all_inspections["tables_and_text"].append({
                    "type": "ROI Manager",
                    "roi_count": rm.getCount() if rm else 0
                })
            elif title == "Log":
                all_inspections["tables_and_text"].append({
                    "type": "Log Window",
                    "status": "Visible"
                })

    return str(all_inspections)



@tool
def internet_search(query: str, max_results: int = 5):
    """Run a web search"""
    ddgs = DDGS()
    results = ddgs.text(query=query, max_results=max_results)
    return results

@tool
def inspect_java_class(class_name: str, keyword: str = "") -> str:
    """
    CRITICAL TOOL for verifying ImageJ/Java API methods and fields. 
    USE THIS BEFORE WRITING CODE if you are unsure of a method name or signature.
    USE THIS TO REPAIR 'MissingMethod' or 'AttributeError' by searching for the correct spelling.

    Args:
        class_name: The Java class to inspect. You can use simple names like 'ImagePlus', 
                    'IJ', or 'RoiManager'. The tool automatically searches common ImageJ packages.
        keyword: Optional. A string to filter the results. Use this to find specific 
                 functionality (e.g., 'threshold', 'scale', 'stat').

    Returns:
        A list of real, executable Java method signatures and constants. 
        If no exact match is found, it provides fuzzy 'Did you mean?' suggestions."""
    
    
    
    ij = get_ij()
    clean_name = class_name.strip()
    
    # 1. Get the correct ClassLoader from the active ImageJ instance
    # This is the 'Source of Truth' for where ij.plugin lives
    ij_loader = ij.getClass().getClassLoader()
    
    # 2. Force the current thread to use this loader
    # This fixes the 'works in Notebook but not in tools.py' issue
    Thread = jpype.JClass("java.lang.Thread")
    Thread.currentThread().setContextClassLoader(ij_loader)

    search_packages = [
        "", "ij.", "ij.process.", "ij.gui.", "ij.measure.", 
        "ij.plugin.", "ij.plugin.frame.", "ij.io.", "ij.macro.",
        "net.imagej.", "net.imglib2."
    ]
    
    JClass = None
    resolved_name = None

    for pkg in search_packages:
        full_path = pkg + clean_name
        try:
            # Try loading via the ClassLoader we just forced
            java_class_obj = jpype.java.lang.Class.forName(full_path, True, ij_loader)
            JClass = jpype.JClass(java_class_obj)
            resolved_name = full_path
            break
        except:
            continue

    if JClass is None:
        return f"ERROR: Could not resolve class '{class_name}'. Verify the class is in the Fiji jars folder."

    try:
        java_class_obj = JClass.class_
        search_term = keyword.lower()
        
        all_methods = java_class_obj.getMethods()
        all_fields = java_class_obj.getFields()
        
        # 1. Collect everything for fuzzy matching
        all_method_names = [str(m.getName()) for m in all_methods]
        all_field_names = [str(f.getName()) for f in all_fields]

        # 2. Filter logic
        found_methods = []
        for m in all_methods:
            name = str(m.getName())
            if search_term and search_term not in name.lower(): continue
            ret = str(m.getReturnType().getSimpleName())
            params = ", ".join([str(p.getSimpleName()) for p in m.getParameterTypes()])
            found_methods.append(f"{ret} {name}({params})")

        found_fields = []
        for f in all_fields:
            f_name = str(f.getName())
            if search_term and search_term not in f_name.lower(): continue
            f_type = str(f.getType().getSimpleName())
            found_fields.append(f"{f_type} {f_name}")

        # 3. Build Output
        output = [f"--- INSPECTION OF: {resolved_name} ---"]
        if search_term:
            output.append(f"FILTERED BY KEYWORD: '{search_term}'")
        
        # Method Section with Suggestions
        output.append("\n✅ METHODS:")
        if found_methods:
            output.extend(sorted(list(set(found_methods))))
        elif search_term:
            suggestions = difflib.get_close_matches(search_term, all_method_names, n=5, cutoff=0.4)
            msg = f"(No methods found matching '{search_term}')"
            if suggestions:
                msg += f"\n💡 Did you mean: {', '.join(suggestions)}?"
            output.append(msg)
        else:
            output.append("(No public methods found)")

        # Field Section with Suggestions
        output.append("\nℹ️ FIELDS / CONSTANTS:")
        if found_fields:
            output.extend(sorted(list(set(found_fields))))
        elif search_term:
            suggestions = difflib.get_close_matches(search_term, all_field_names, n=5, cutoff=0.4)
            msg = f"(No fields found matching '{search_term}')"
            if suggestions:
                msg += f"\n💡 Did you mean: {', '.join(suggestions)}?"
            output.append(msg)
        else:
            output.append("(No public fields found)")

        return "\n".join(output)[:8000]

    except Exception as e:
        return f"ERROR: Reflection failed for {resolved_name}: {str(e)}"




class SafeToolLoggerMiddleware(AgentMiddleware):
     def wrap_tool_call(self, request: ToolCallRequest, handler): 
        print(f"[TOOL LOG] Calling tool: {request.tool_call['name']}") 
        try: 
            result = handler(request) 
        except Exception as e: 
            print(f"[TOOL ERROR] {request.tool_call['name']} raised: {e}") 
            return ToolMessage( content=f"Tool {request.tool_call['name']} failed with error: {str(e)}", tool_call_id=request.tool_call["id"] )
     # Handle LangGraph control commands 
        if isinstance(result, Command): 
            print(f"[TOOL LOG] Tool {request.tool_call['name']} returned a Command: {result}") 
            return result # Handle standard ToolMessage
        if isinstance(result, ToolMessage):
             print(f"[TOOL LOG] Tool {request.tool_call['name']} returned ToolMessage") 
             return result # Handle None or raw values print(f"[TOOL LOG] Tool {request.tool_call['name']} returned raw result: {repr(result)}") 
        if result is None: 
            result = "None (no output)" 
            return ToolMessage( content=str(result), tool_call_id=request.tool_call["id"] )
        

class TodoDisplayMiddleware(TodoListMiddleware):
    def on_end(self, input, output, **kwargs):
        todos = getattr(self, "todos", [])
        if todos:
            formatted = "\n🧠 **Agent Plan / To-Do List:**\n" + "\n".join(
                [f"{i+1}. {t if isinstance(t, str) else t.get('task', str(t))}" for i, t in enumerate(todos)]
            )
            output["content"] += "\n\n" + formatted
        return output