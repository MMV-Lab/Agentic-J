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

from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from keys import gpt_key

def build_retriever(
    collection_name: str,
    path: str,
):
    client = QdrantClient(path=path)

    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=OpenAIEmbeddings(api_key=gpt_key, model="text-embedding-3-large"),
    )

    # Hybrid search
    return vectorstore.as_retriever(
        search_type="mmr",  # or "similarity"
        search_kwargs={
            "k": 8,
            "fetch_k": 30,
        },
    )

retriever = build_retriever(
    collection_name="BioimageAnalysisDocs",
    path="./qdrant_data",
)

@tool("rag_retrieve")
def rag_retrieve(query: str) -> str:
    """
    Retrieve relevant context from the document RAG.
    Input should be a precise information-seeking query.
    """
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


import numpy as np


@tool
def inspect_active_image():
    """
    Examines the active image using Java-side operations for metadata and statistics.
    This avoids heavy memory copying and NumPy conversion errors.
    
    Returns:
        A dictionary string containing dimensions, calibration, and basic intensity stats.
    """
    ij = get_ij()

    dataset = ij.py.active_dataset()
    if dataset is None:
        return "No image is currently open in the GUI."

    try:
        # --- 1. Metadata (Same as before) ---
        name = str(dataset.getName())
        
        dims_map = {}
        calibration = {}
        
        for i in range(dataset.numDimensions()):
            axis = dataset.axis(i)
            label = str(axis.type().getLabel())
            size = int(dataset.dimension(i))
            scale = float(axis.averageScale(0, 1))
            
            dims_map[label] = size
            if label in ['X', 'Y', 'Z']:
                calibration[label] = scale
                
        units = str(dataset.axis(0).unit()) if dataset.axis(0).unit() else "pixels"

        # --- 2. Statistics via ImageJ Ops (The Fix) ---
        # Instead of moving pixels to Python, we ask Java to do the math.
        # This is much faster and safer for large images.
        
        try:
            # We use the 'stats' namespace from ImageJ Ops
            # Note: The result is a Java Object, so we call .getRealDouble() 
            # to get a clean Python float immediately.
            min_val = ij.op().stats().min(dataset).getRealDouble()
            max_val = ij.op().stats().max(dataset).getRealDouble()
            mean_val = ij.op().stats().mean(dataset).getRealDouble()
            
            # Determine Pixel Type string
            pixel_type = str(dataset.getType().getClass().getSimpleName())

            stats = {
                "min": min_val,
                "max": max_val,
                "mean": mean_val,
                "pixel_type": pixel_type
            }
        except Exception as op_error:
            # Fallback if Ops fails (e.g. very old Fiji version)
            stats = f"Could not compute stats: {str(op_error)}"

        # --- 3. Construct Payload ---
        info_payload = {
            "filename": name,
            "structure": dims_map,
            "calibration": {
                "scales": calibration,
                "units": units
            },
            "statistics": stats,
            "is_3d": 'Z' in dims_map,
            "is_time_series": 'Time' in dims_map
        }

        return str(info_payload)

    except Exception as e:
        return f"Error inspecting image: {str(e)}"



@tool
def internet_search(query: str, max_results: int = 5):
    """Run a web search"""
    ddgs = DDGS()
    results = ddgs.text(query=query, max_results=max_results)
    return results



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