# Phase 1 — Information Gathering

1. Understand the scientific goal.
2. Do NOT call these one at a time. Issue ALL in a single turn — LangGraph runs them in parallel:
   - inspect_all_ui_windows()
   - extract_image_metadata(sample_image_path)
   - rag_retrieve_docs(relevant_query)
   - plugin_manager(task="<describe the scientific goal>", project_root="<path>")
     The plugin manager searches the registry, checks installation, reads skill docs,
     and returns a structured recommendation. ALWAYS prefer a plugin over custom code.

3. Ask the user for clarification if the task is ambiguous (use biologist-friendly language).

4. LEDGER: After gathering is complete, call set_ledger_metadata to record:
   - scientific_goal (one sentence)
   - image_metadata (bit depth, pixel size, channels, number of images,
     and `background_mode` from `threshold_suggestions` — `"dark"` for fluorescence,
     `"bright"` for brightfield/H&E. The coder reads this to pick the `"Otsu dark"` vs
     `"Otsu"` suffix; if omitted, it falls back to a runtime stats check)
   - relevant_skill (use the skill_folder from plugin_manager's recommendation)
   - recommended_plugin (use the recommended_plugin name from plugin_manager).
     This is propagated to the coder, which must use this plugin and not silently
     substitute an alternative. If plugin_manager returned no recommendation, omit this field.
