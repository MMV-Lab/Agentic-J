# Phase 1 — Information Gathering

1. Understand the scientific goal.

2. Call setup_analysis_workspace(project_name) FIRST — before ANY ledger calls.
   Use a short, descriptive name (e.g. "nuclei_count_hela"). This creates the project folder
   at /app/data/projects/<name>/ and must be done before set_ledger_metadata or update_state_ledger.
   project_root = "/app/data/projects/<name>"

3. Do NOT call these one at a time. Issue ALL in a single turn — LangGraph runs them in parallel:
   - inspect_all_ui_windows()
   - extract_image_metadata(sample_image_path)
   - rag_retrieve_docs(relevant_query)
   - plugin_manager(task="<describe the scientific goal>", project_root=project_root)
     The plugin manager searches the registry, checks installation, reads skill docs,
     and returns a structured recommendation. ALWAYS prefer a plugin over custom code.

4. Ask the user for clarification if the task is ambiguous (use biologist-friendly language).

5. Ask the user how they prefer to work:
   - **Script-based (recommended)**: The agent generates and runs Groovy scripts automatically — faster, reproducible, no manual clicking.
   - **UI-guided**: The agent guides you step-by-step through Fiji menus and dialogs.
   Record the answer as `operating_mode`: "script" or "ui".

6. LEDGER: After gathering is complete, call set_ledger_metadata to record:
   - scientific_goal (one sentence)
   - operating_mode ("script" or "ui")
   - image_metadata (bit depth, pixel size, channels, number of images)
   - relevant_skill (use the skill_folder from plugin_manager's recommendation)
