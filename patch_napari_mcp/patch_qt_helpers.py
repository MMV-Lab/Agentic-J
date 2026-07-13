#!/usr/bin/env python
"""Patch the installed napari-mcp ``qt_helpers.py`` for Agent J.

Agent J runs the napari-mcp standalone stdio server as a long-lived,
agent-driven, in-container viewer. Two upstream behaviours break that model,
and this patch fixes both (fail-fast if the upstream source drifts, matching
the philosophy of ``patch_stardist/``):

1. **Window close kills the server.** Upstream ``_on_destroyed`` (fired when the
   user clicks the window's close button) calls ``state.request_shutdown()``,
   which stops the FastMCP event loop and crashes the server
   (``RuntimeError: Event loop stopped before Future completed``). The agent
   then reopens against a freshly respawned server. We drop the shutdown call so
   the server simply clears the viewer and stays alive for reopen.

2. **Reopened viewer is not interactive.** Upstream starts the ``qt_event_pump``
   task only in ``init_viewer``. When the agent reopens via ``add_layer`` (which
   calls ``ensure_viewer``, not ``init_viewer``), the pump never restarts: tool
   calls still render via their one-shot ``process_events()`` burst, but nothing
   services mouse/keyboard between calls, so the window looks frozen. We start
   the pump in ``ensure_viewer`` so any viewer (re)creation is interactive.

Run with the napari-mcp env's python:
    /opt/conda/envs/napari-mcp/bin/python patch_napari_mcp/patch_qt_helpers.py
"""
from __future__ import annotations

import sys

import napari_mcp.qt_helpers as qh

PATH = qh.__file__
MARKER = "Patched for Agent J"

with open(PATH, encoding="utf-8") as fh:
    src = fh.read()

if MARKER in src:
    print(f"[patch] {PATH} already patched — skipping")
    sys.exit(0)

REPLACEMENTS = [
    # 1) Do not shut the server down when the window is closed.
    (
        "        def _on_destroyed(*_args: Any) -> None:\n"
        "            state.viewer = None\n"
        "            state.window_close_connected = False\n"
        "            state.request_shutdown()\n",
        "        def _on_destroyed(*_args: Any) -> None:\n"
        "            state.viewer = None\n"
        "            state.window_close_connected = False\n"
        "            # Patched for Agent J: do NOT request_shutdown() on window\n"
        "            # close, so the server survives and the agent can reopen.\n",
    ),
    # 2) Guarantee the interactive Qt event pump on any viewer creation.
    (
        "    ensure_qt_app(state)\n"
        "    if state.viewer is None:\n"
        "        state.viewer = napari.Viewer()\n"
        "        connect_window_destroyed_signal(state, state.viewer)\n"
        "    return state.viewer\n",
        "    ensure_qt_app(state)\n"
        "    if state.viewer is None:\n"
        "        state.viewer = napari.Viewer()\n"
        "        connect_window_destroyed_signal(state, state.viewer)\n"
        "    # Patched for Agent J: guarantee the interactive Qt event pump for\n"
        "    # any viewer (re)creation (e.g. via add_layer, not just init_viewer)\n"
        "    # so a reopened window stays responsive to mouse/keyboard input.\n"
        "    if state.qt_pump_task is None or state.qt_pump_task.done():\n"
        "        try:\n"
        "            state.qt_pump_task = asyncio.get_running_loop().create_task(\n"
        "                qt_event_pump(state)\n"
        "            )\n"
        "        except RuntimeError:\n"
        "            pass\n"
        "    return state.viewer\n",
    ),
]

for old, new in REPLACEMENTS:
    count = src.count(old)
    if count != 1:
        sys.stderr.write(
            f"[patch] ERROR: expected exactly 1 match but found {count} for block:\n{old}\n"
            "napari-mcp source has drifted; update patch_napari_mcp/patch_qt_helpers.py.\n"
        )
        sys.exit(1)
    src = src.replace(old, new)

compile(src, PATH, "exec")  # fail before writing if the result is not valid
with open(PATH, "w", encoding="utf-8") as fh:
    fh.write(src)
print(f"[patch] patched {PATH}")
