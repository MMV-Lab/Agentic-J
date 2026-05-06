import re

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage, SystemMessage, AIMessage
from langgraph.types import Command
from langchain.agents.middleware import TodoListMiddleware


class NarrationReminderMiddleware(AgentMiddleware):
    # Keeps the narration rule in the most-recent position on every turn so it
    # doesn't drift out of attention as tool history grows. Not persisted to state.
    REMINDER = (
        """Reminder: before this turn's tool call(s), emit ONE short 
        biologist-friendly sentence describing your intent. If a tool just 
        returned, briefly acknowledge what came back in the same sentence 
        (combine result + next intent — don't add a separate after-message)."""
    )

    def wrap_model_call(self, request, handler):
        request.messages = list(request.messages) + [SystemMessage(content=self.REMINDER)]
        return handler(request)


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


class PhaseGuardMiddleware(AgentMiddleware):
    """
    Guardrail that nudges the supervisor when it appears to be operating in a
    pipeline phase without having read the matching phase skill file.

    Design choices:
      - Does NOT inject phase content. The supervisor must read the file
        itself via smart_file_reader. The middleware only adds a one-line
        reminder when a gap is detected.
      - Phase detection: scans recent messages for the most-recent signal —
        update_state_ledger(phase=...) tool call, or read_state_ledger output
        containing a "CURRENT PHASE: <X>" line. If neither is found, the
        guard is silent (no false positives early in a session).
      - "File was read" detection: scans recent messages for any
        smart_file_reader call/result naming the matching phase filename.
      - Lookback is bounded so the guard stays fast as conversation grows.
    """

    PHASES_DIR = "/app/skills/workflow/supervisor_pipeline_phases"

    PHASE_FILES = {
        "1":  "phase_1_gathering.md",
        "2":  "phase_2_planning.md",
        "3":  "phase_3_setup.md",
        "4a": "phase_4a_io_check.md",
        "4b": "phase_4b_processing.md",
        "4c": "phase_4c_statistics.md",
        "4d": "phase_4d_plotting.md",
        "5":  "phase_5_summarization.md",
        "6":  "phase_6_documentation.md",
        "7":  "phase_7_qa.md",
    }

    LOOKBACK = 30

    _PHASE_RE = re.compile(r"CURRENT PHASE:\s*([0-9a-z]+)", re.IGNORECASE)

    def wrap_model_call(self, request, handler):
        msgs = list(request.messages)
        active_phase = self._detect_phase(msgs)
        if not active_phase:
            return handler(request)

        phase_file = self.PHASE_FILES.get(active_phase)
        if not phase_file:
            # Unknown phase identifier — be silent rather than cry wolf.
            return handler(request)

        if self._has_read_phase_file(msgs, phase_file):
            return handler(request)

        reminder = SystemMessage(content=(
            f"[PHASE GUARD] You appear to be operating in Phase {active_phase} "
            f"without having read its rules in this conversation. Call "
            f"smart_file_reader('{self.PHASES_DIR}/{phase_file}') BEFORE "
            f"continuing with phase work. (This guard does not deliver the "
            f"rules itself; read the file yourself.)"
        ))
        request.messages = msgs + [reminder]
        return handler(request)

    def _detect_phase(self, msgs):
        """Most recent ledger phase signal wins. Skips '[not set]' sentinels."""
        for msg in reversed(msgs[-self.LOOKBACK:]):
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    if tc.get("name") == "update_state_ledger":
                        p = tc.get("args", {}).get("phase")
                        if p:
                            return str(p).strip()
            if isinstance(msg, ToolMessage) and msg.content:
                m = self._PHASE_RE.search(str(msg.content))
                if m and not m.group(1).startswith("not"):
                    return m.group(1).strip()
        return None

    def _has_read_phase_file(self, msgs, phase_filename):
        """True if smart_file_reader was called/returned for the phase file."""
        for msg in reversed(msgs[-self.LOOKBACK:]):
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    if tc.get("name") == "smart_file_reader":
                        path = str(tc.get("args", {}).get("path", ""))
                        if phase_filename in path:
                            return True
            if isinstance(msg, ToolMessage) and msg.content:
                if phase_filename in str(msg.content):
                    return True
        return False


class TodoDisplayMiddleware(TodoListMiddleware):
    def on_end(self, input, output, **kwargs):
        todos = getattr(self, "todos", [])
        if todos:
            formatted = "\n🧠 **Agent Plan / To-Do List:**\n" + "\n".join(
                [f"{i+1}. {t if isinstance(t, str) else t.get('task', str(t))}" for i, t in enumerate(todos)]
            )
            output["content"] += "\n\n" + formatted
        return output