import os
import json
import uuid
from datetime import datetime

CHATS_DIR = os.environ.get("CHAT_DATA_PATH", "/app/data/chats")
INDEX_FILE = os.path.join(CHATS_DIR, "index.json")


def _extract_text(content) -> str:
    """Extract plain text from a message content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


class ChatHistoryManager:
    def __init__(self):
        os.makedirs(CHATS_DIR, exist_ok=True)
        self._index = self._load_index()

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------

    def _load_index(self) -> dict:
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_index(self):
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(self._index, f, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_thread(self) -> str:
        """Generate a new thread ID and register it in the index."""
        thread_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        self._index[thread_id] = {
            "title": "New Chat",
            "created_at": now,
            "last_updated": now,
        }
        self._save_index()
        return thread_id

    def list_threads(self) -> list[tuple[str, dict]]:
        """Return [(thread_id, metadata), ...] sorted newest-first."""
        return sorted(
            self._index.items(),
            key=lambda x: x[1].get("last_updated", ""),
            reverse=True,
        )

    def update_title(self, thread_id: str, first_message: str):
        """Set a human-readable title from the first user message."""
        if thread_id not in self._index:
            return
        title = first_message[:52].rstrip()
        if len(first_message) > 52:
            title += "…"
        self._index[thread_id]["title"] = title
        self._index[thread_id]["last_updated"] = datetime.now().isoformat()
        self._save_index()

    def touch_thread(self, thread_id: str):
        """Bump last_updated so the thread floats to the top of the list."""
        if thread_id not in self._index:
            return
        self._index[thread_id]["last_updated"] = datetime.now().isoformat()
        self._save_index()

    def get_messages_for_display(self, supervisor, thread_id: str) -> list:
        """
        Pull the full message list from the LangGraph checkpoint state.
        Returns a list of LangChain BaseMessage objects (or an empty list on
        failure / no history yet).
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            state = supervisor.get_state(config)
            if state is None:
                return []
            return state.values.get("messages", [])
        except Exception as e:
            print(f"[ChatHistory] Could not load thread {thread_id}: {e}")
            return []

    def format_messages_as_html(self, messages: list) -> str:
        """
        Convert a list of LangChain messages into HTML snippets ready to be
        appended to a QTextEdit.  Returns a single HTML string.
        """
        lines = []
        for msg in messages:
            msg_type = getattr(msg, "type", "") or ""
            content = _extract_text(getattr(msg, "content", ""))
            tool_calls = getattr(msg, "tool_calls", None) or []

            if msg_type == "human":
                if content:
                    lines.append(f"<p><b>You:</b> {content}</p>")

            elif msg_type == "ai":
                # Only show text responses, not pure tool-dispatch messages
                if content and not tool_calls:
                    lines.append(f"<p>{content}</p>")
                elif tool_calls:
                    for tc in tool_calls:
                        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                        lines.append(
                            f"<p><i style='color:#7f8c8d;'>[Called tool: {name}]</i></p>"
                        )

            # tool / system messages are intentionally omitted from display

        return "\n".join(lines)
