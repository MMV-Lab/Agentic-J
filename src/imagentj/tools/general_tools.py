import jpype
import difflib
from langchain.tools import tool
from ddgs import DDGS
from imagentj.imagej_context import get_ij


@tool
def get_imagej_log(last_lines: int = 100) -> str:
    """
    Read all visible text/error windows from the running Fiji instance.

    USE THIS TOOL when:
    - The user reports an error, something "not working", unexpected results, or nothing happening.
    - The word 'error', 'failed', 'exception', 'crash', 'nothing happened', or 'not working'
      appears in the user's message.
    - inspect_all_ui_windows reveals a window named 'Log' or 'Exception' is open.

    Scans ALL visible Fiji frames (Log window, Exception pop-ups, Script Editor console, etc.)
    by reading their TextPanel content directly — more reliable than IJ.getLog() which only
    captures IJ.log() calls and misses exception dialogs.
    """
    try:
        from scyjava import jimport
        Frame     = jimport("java.awt.Frame")
        TextWindow = jimport("ij.text.TextWindow")
    except Exception as e:
        return f"ERROR: Could not import Java classes: {e}"

    error_keywords = ("exception", "error", "warning", "failed", "caused by", "at ij.", "at net.")
    sections = []

    try:
        frames = Frame.getFrames()
    except Exception as e:
        return f"ERROR: Could not list Fiji frames: {e}"

    for frame in frames:
        try:
            if not frame.isVisible():
                continue
            title = str(frame.getTitle())

            # Only read TextWindow instances (Log, Exception, Console, etc.)
            if not isinstance(frame, TextWindow):
                continue

            panel = frame.getTextPanel()
            text = str(panel.getText()) if panel is not None else ""

            if not text.strip():
                continue

            lines = text.splitlines()
            tail = lines[-last_lines:]

            annotated = []
            for line in tail:
                if any(kw in line.lower() for kw in error_keywords):
                    annotated.append(f"⚠️  {line}")
                else:
                    annotated.append(f"   {line}")

            sections.append(
                f"=== Window: '{title}' ({len(lines)} lines total, showing last {len(tail)}) ===\n"
                + "\n".join(annotated)
            )

        except Exception:
            continue

    if not sections:
        return (
            "No visible TextWindow content found in Fiji. "
            "The error may only exist in the script execution output (STDERR) "
            "already returned by execute_script."
        )

    return "\n\n".join(sections)


@tool
def internet_search(query: str, max_results: int = 5):
    """Run an optional web search without aborting the analysis on network failure.

    Search backends are external and can be unavailable, rate limited, or time out.
    Those conditions are evidence gaps, not fatal errors in an image-analysis run,
    so expose them to the agent as a soft ``ERROR:`` result instead of allowing an
    exception to escape through the LangChain tool boundary.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return "ERROR: Internet search skipped because the query was empty."

    try:
        limit = max(1, min(int(max_results), 10))
    except (TypeError, ValueError):
        limit = 5

    try:
        results = DDGS().text(query=clean_query, max_results=limit)
        return results or []
    except Exception as exc:
        # Do not include a traceback: the supervisor only needs a concise signal
        # that it should proceed from local evidence or report the missing source.
        return f"ERROR: Internet search unavailable ({type(exc).__name__}: {exc})"


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
        If no exact match is found, it provides fuzzy 'Did you mean?' suggestions.
    """

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
