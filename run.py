# interactive_agent_runner.py
# Run this from the same environment where `supervisor` is defined.

import sys
sys.path.insert(0, 'src')
import time
from langsmith import traceable
import os
from imagentj.agents import init_agent
from langchain_openai import ChatOpenAI
from imagentj.imagej_context import get_ij
from config.imagej_config import FIJI_JAVA_HOME


os.environ["JAVA_HOME"] = FIJI_JAVA_HOME

# from langgraph.checkpoint.memory import MemorySaver  # alternative (in-memory)

# ----- CONFIG -----
THREAD_ID = "imagej_supervisor_thread"   # keep constant to preserve context


# ----- Prepare checkpointer (persistent across runs) -----



# If your supervisor was created *without* the checkpoint, you can re-create it
# or set supervisor.checkpoint = checkpointer depending on API. Here we assume
# you can pass checkpointer when creating the agent. If you already created
# ``supervisor`` without checkpoint, recreate it like you did earlier with:
#
# supervisor = create_deep_agent(..., checkpoint=checkpointer, debug=True, verbose=True)
#
# If you already set checkpoint at creation, skip re-creation.

# ----- Helper: nicely print streaming events -----

thinking = True

def extract_tool_names(event):
    names = []

    # Case 1: explicit tool calls
    if "tool" in event and isinstance(event["tool"], dict):
        names.append(event["tool"].get("name"))

    if "tool_calls" in event and isinstance(event["tool_calls"], list):
        for tc in event["tool_calls"]:
            if "name" in tc:
                names.append(tc["name"])
            elif "function" in tc:
                names.append(tc["function"].get("name"))

    # Case 2: nested inside model messages (OpenAI streaming)
    model = event.get("model")
    if isinstance(model, dict):
        for msg in model.get("messages", []):
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                names.append(fn.get("name"))

    return [n for n in names if n]

def handle_event(event):
    global thinking

    # --- Model thinking / streaming ---
    if "model" in event:
        if thinking:
            print("\n[AI is thinking...]\n")
            thinking = True

        msgs = event["model"].get("messages", [])
        if msgs:
            last = msgs[-1]
            content = (
                last.get("content")
                if isinstance(last, dict)
                else getattr(last, "content", None)
            )
            if content:
                print(content, end="", flush=True)
        return

   # --- Tool invocation ---
    tool_names = extract_tool_names(event)
    for name in tool_names:
        print(f"\n[Calling tool: {name}]")
    if tool_names:
        return

    # --- Final output ---
    if "output" in event:
        thinking = False
        out = event["output"]
        final_text = out.get("output") or out.get("result") or out

        print("\n\n=== AI ===")
        print(final_text if isinstance(final_text, str) else str(final_text))
        print("==========\n")



intro_message ="""
Hello I am ImageJ agent, some call me ImagentJ :) 
I can design a step-by-step protocol and, if useful, generate a runnable Groovy macro (and execute/test it if you want).

To get started, please share:
- Goal: what you want measured/segmented/processed.
- Example data: 1–2 sample images (file type), single image or batch?
- Image details: dimensions, channels, z-stacks/time series, pixel size (units).
- Targets: what objects/features to detect; which channel(s) matter.
- Preprocessing: background/flat-field correction, denoising needs?
- Outputs: tables/measurements, labeled masks/overlays, ROIs, saved images.
- Constraints: plugins available (e.g., Fiji with Bio-Formats, MorpholibJ, TrackMate, StarDist), OS, any runtime limits.

If you’re unsure, tell me the biological question and show one representative image—I’ll propose a clear plan and a script you can run.

"""

# ----- Interactive loop -----
@traceable
def interactive_loop(agent, checkpointer, thread_id=THREAD_ID):
    config = {"configurable": {"thread_id": thread_id}}

    try:
        agent.checkpoint = checkpointer
    except Exception:
        pass

    print("----- Starting interactive session -----")
    print("(type 'exit' or 'quit' to stop)\n")
    print(intro_message)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        print("\nAI:", end=" ", flush=True)

        for event in agent.stream(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
            stream_mode="updates",
        ):
            handle_event(event)



try:
    global ij
    ij = get_ij()
    ij.ui().showUI()

    supervisor , checkpointer = init_agent() # noqa: F821
except NameError:
    print("ERROR: 'supervisor' agent object not found in this namespace.")
    print("Make sure you created it with create_deep_agent(..., checkpoint=checkpointer, debug=True).")
    sys.exit(1)

interactive_loop(supervisor, checkpointer)

