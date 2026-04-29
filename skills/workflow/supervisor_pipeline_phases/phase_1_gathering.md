# Phase 1 — Information Gathering

1. Understand the scientific goal.

2. Call setup_analysis_workspace(project_name) FIRST — before ANY ledger calls.
   Use a short, descriptive name (e.g. "nuclei_count_hela"). This creates the project folder
   at /app/data/projects/<name>/ and must be done before set_ledger_metadata or update_state_ledger.
   project_root = "/app/data/projects/<name>"

3. Find the user's images: they are at /data/<filename>. If the user did not specify an exact path,
   call inspect_folder_tree("/data") to list available files, then ask the user which file(s) to use.
   Do NOT guess paths inside the project folder — images are never in raw_images/ until you copy them.

4. Do NOT call these one at a time. Issue ALL in a single turn — LangGraph runs them in parallel:
   - inspect_all_ui_windows()
   - extract_image_metadata("/data/<filename>")   ← use the actual file path from step 3
   - rag_retrieve_docs(relevant_query)
   - plugin_manager(task="<describe the scientific goal>", project_root=project_root)
     The plugin manager searches the registry, checks installation, reads skill docs,
     and returns a structured recommendation. ALWAYS prefer a plugin over custom code.

5. Ask the user for clarification if the task is ambiguous (use biologist-friendly language).

6. Ask the user how they prefer to work:
   - **Script-based (recommended)**: The agent generates and runs Groovy scripts automatically — faster, reproducible, no manual clicking.
   - **UI-guided**: The agent guides you step-by-step through Fiji menus and dialogs.
   Record the answer as `operating_mode`: "script" or "ui".

7. LEDGER: After gathering is complete, call set_ledger_metadata to record:
   - scientific_goal (one sentence)
   - operating_mode ("script" or "ui")
   - image_metadata (bit depth, pixel size, channels, number of images)
   - relevant_skill (use the skill_folder from plugin_manager's recommendation)
