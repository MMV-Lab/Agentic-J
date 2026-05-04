# Phase 1 — Information Gathering

1. Understand the scientific goal.
2. Do NOT call these one at a time. Issue ALL in a single turn — LangGraph runs them in parallel:
   - inspect_all_ui_windows()
   - extract_image_metadata(sample_image_path)
   - rag_retrieve_docs(relevant_query)
   - plugin_manager(task="<describe the scientific goal>", project_root="<path>")
     MANDATORY — call it on EVERY new project, even when you think the task is
     "easy enough" for stock `IJ.run` commands (Find Maxima, Analyze Particles,
     auto-thresholding, etc.). The manager's response provenance — including
     `recommended_plugin=None` — must be recorded in the ledger. Without this
     record, downstream phases have no skill pointer for the debugger to
     reference.
     The plugin manager searches the registry, checks installation, reads skill docs,
     and returns a structured recommendation. ALWAYS prefer a plugin over custom code.

3. Ask the user for clarification if the task is ambiguous (use biologist-friendly language).

4. LEDGER: After gathering is complete, call set_ledger_metadata to record:
   - scientific_goal (one sentence)
   - image_metadata (bit depth, pixel size, channels, number of images)
   - relevant_skill (use the skill_folder from plugin_manager's recommendation)
