import jpype
from langchain.tools import tool
from imagentj.imagej_context import get_ij
from jpype import JClass
import os
import json
from .analyst_tools import run_python_code
import datetime
import shutil
from typing import Optional
from filelock import FileLock


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


def run_script_safe(language: str, code: str, max_retries: int = 3) -> str:
    """
    Unified safe execution tool for the supervisor.

    This tool executes ImageJ/Fiji scripts safely in the GUI, handling:

      - Window snapshot & automatic cleanup on failure
      - Retry handling (up to `max_retries`)
      - Only shows images after successful execution

    Only supports groovy


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



@tool("save_script")  
def save_script(directory: str, filename: str, content: str, description: str, error_context: Optional[str] = None) -> str:
    """
    Saves a script, archives previous versions, and maintains a versioned history in script_dictionary.json.
    
    Args:
        directory: Path to the directory where the script should be saved must look like this:
        Correct:   /app/data/[project_name]/scripts/imagej/
        WRONG:     /app/data/[project_name]/scripts/
        WRONG:     /app/data/[project_name]/
        filename: Name of the script (must be .py or .groovy).
        content: The new source code.
        description: A short and precise summary of what the script does for the supervisor. Maximize information and minimze tokens.
                     Should include key details about the script's functionality, inputs, outputs, and any important parameters or usage notes.
                     This description will be stored in the script_dictionary.json for reference.
        error_context: (Optional) If this is a fix, provide the error message/reason why the 
                       previous version was archived.
    """
    allowed_extensions = ('.py', '.groovy')
    if not filename.lower().endswith(allowed_extensions):
        return f"Error: Only {allowed_extensions} files are permitted."

    try:
        os.makedirs(directory, exist_ok=True)
        dict_path = os.path.join(directory, "script_dictionary.json")
        lock_path = os.path.join(directory, "script_dictionary.lock")
        full_path = os.path.join(directory, filename)
        
        lock = FileLock(lock_path, timeout=30)
        with lock:
            # Load existing dictionary
            data = {}
            if os.path.exists(dict_path):
                with open(dict_path, 'r') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {}

            # 1. Archive the existing file and its metadata
            if os.path.exists(full_path):
                archive_dir = os.path.join(directory, "archive")
                os.makedirs(archive_dir, exist_ok=True)
                
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                archived_filename = f"{timestamp}_{filename}"
                archived_path = os.path.join(archive_dir, archived_filename)
                
                # Move the actual file
                shutil.move(full_path, archived_path)
                
                # Update Metadata History
                if filename in data:
                    old_entry = data[filename]
                    history_entry = {
                        "archived_at": timestamp,
                        "archived_path": archived_path,
                        "description": old_entry.get("description"),
                        "version": old_entry.get("version", 1),
                        "failure_reason": error_context if error_context else "Updated by user/agent"
                    }
                    
                    # Ensure a history list exists for this filename
                    if "history" not in old_entry:
                        old_entry["history"] = []
                    
                    old_entry["history"].append(history_entry)
                    current_version = old_entry.get("version", 1) + 1
                else:
                    current_version = 2
            else:
                current_version = 1

            # 2. Save the NEW file
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 3. Update the Dictionary with the new active entry
            data[filename] = {
                "full_path": full_path,
                "language": "Python" if filename.endswith('.py') else "Groovy",
                "description": description,
                "version": current_version,
                "last_modified": datetime.datetime.now().isoformat(),
                "history": data.get(filename, {}).get("history", [])
            }

            with open(dict_path, 'w') as f:
                json.dump(data, f, indent=4)

            return f"Successfully saved version {current_version} of {filename}. Previous version archived."

    except Exception as e:
        return f"Error in save_script: {str(e)}"
    


@tool("execute_script")   
def execute_script(directory: str, filename: str) -> str:
    """
    Triggers the execution of a saved Python or Groovy script within the project environment.
    
    WHEN TO USE:
    - Use this ONLY after you have verified the script's description via 'get_script_info'.
    - Use this to run a sequence of tasks (e.g., first run the Groovy segmentation, then the Python analysis).
    
    BEHAVIOR:
    - For .groovy: Automatically handles ImageJ/Fiji window management, snapshots open images, 
      and cleans up (closes) new windows if a crash occurs to prevent GUI clutter.
    - For .py: Automatically sets the working directory, pre-imports scientific libraries (pandas, 
      numpy, seaborn), and configures high-resolution plotting.

    INPUTS:
    - directory: The directory where the script is located. This will also become the 
      working directory for Python execution.
    - filename: The name of the file to execute. Must end in .py or .groovy.

    OUTPUT:
    - Returns the full STDOUT and STDERR of the execution. 
    - On SUCCESS: Provides confirmation logs.
    - On FAILURE: Provides a detailed traceback. Pass this traceback to the Debugger agent 
      if a fix is required.
    """
    full_path = os.path.join(directory, filename)
    
    if not os.path.exists(full_path):
        return f"Error: File {full_path} not found."

    with open(full_path, 'r', encoding='utf-8') as f:
        code_content = f.read()

    # Route based on extension
    if filename.endswith('.py'):
        # Calls your existing run_python_code function
        return run_python_code(code_content, directory)
    
    elif filename.endswith('.groovy'):
        # Calls your existing run_script_safe function
        return run_script_safe(language="groovy", code=code_content)

    return f"Error: File extension of {filename} is not supported for execution."

@tool("get_script_info")
def get_script_info(directory: str, filename: str) -> str:
    """
    Retrieves the metadata and functional description for a specific script from the project dictionary.
    
    WHEN TO USE:
    - Use this immediately AFTER the Coder/Architect subagent claims to have saved a script.
    - Use this to VERIFY that the script's logic (e.g., threshold methods, file paths, specific algorithms) 
      matches your original instructions before you attempt to execute it.
    - Use this if you have forgotten what a specific file in the directory does.

    INPUTS:
    - directory: The project root or output folder where 'script_dictionary.json' resides.
    - filename: The exact name of the script (e.g., 'segment_cells.groovy').

    OUTPUT:
    - Returns a formatted string containing the Language and the Coder's detailed description.
    - If the script is not in the dictionary, it returns an error; use this to catch if the 
      subagent failed to log its work.
    """
    dict_path = os.path.join(directory, "script_dictionary.json")
    if not os.path.exists(dict_path):
        return "Error: script_dictionary.json missing. The subagent may not have saved the script correctly."
    
    with open(dict_path, 'r') as f:
        data = json.load(f)
    
    info = data.get(filename)
    if not info:
        return f"Error: {filename} not found in the project dictionary."
    
    return f"FILE: {filename}\nLANGUAGE: {info['language']}\nPURPOSE: {info['description']}"



@tool("load_script")
def load_script(directory: str, filename: str) -> str:
    """
    Reads the content of a saved Python or Groovy script from the disk.

    WHEN TO USE:
    - CODER: Use this to review existing code before writing a complementary script.
    - DEBUGGER: Use this to retrieve the code that caused an error or traceback.

    CONSTRAINTS:
    - Only .py and .groovy files can be read.
    - Do not use this tool to 'verify' a script for the Supervisor (use get_script_info instead).
    """
    allowed_extensions = ('.py', '.groovy')
    if not filename.lower().endswith(allowed_extensions):
        return f"Error: Only {allowed_extensions} files can be loaded."

    full_path = os.path.join(directory, filename)

    if not os.path.exists(full_path):
        return f"Error: File {full_path} not found in {directory}."

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"--- START OF FILE: {filename} ---\n{content}\n--- END OF FILE ---"
    except Exception as e:
        return f"Error reading file: {str(e)}"
    


@tool("get_script_history")
def get_script_history(directory: str, filename: str) -> str:
    """
    Retrieves the version history and past failure reasons for a specific script.
    
    WHEN TO USE:
    - DEBUGGER: Use this to see what went wrong in previous versions so you don't 
      attempt the same failed fix twice.
    - CODER: Use this to understand the evolution of the script and why certain 
      logic was changed.

    OUTPUT:
    - Returns a list of all archived versions, including timestamps, paths to 
      the old files, and the 'failure_reason' logged during those iterations.
    """
    dict_path = os.path.join(directory, "script_dictionary.json")
    if not os.path.exists(dict_path):
        return "Script dictionary does not exist yet. No history available. Start coding to create the first entry!"

    with open(dict_path, 'r') as f:
        data = json.load(f)

    script_data = data.get(filename)
    if not script_data:
        return f"No history found for {filename}."

    history = script_data.get("history", [])
    if not history:
        return f"No previous history found for {filename}. This is version 1. Start coding to create the first entry!"

    # Format the history for the agent
    report = [f"History for {filename} (Current Version: {script_data.get('version')})"]
    for entry in history:
        report.append(
            f"--- Version {entry['version']} ---\n"
            f"Archived at: {entry['archived_at']}\n"
            f"Archive Path: {entry['archived_path']}\n"
            f"Reason for archiving: {entry['failure_reason']}\n"
        )
    
    return "\n".join(report)