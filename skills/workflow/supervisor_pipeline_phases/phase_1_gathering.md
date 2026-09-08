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
   - When `vlm_judge` is available in the current tools:
     vlm_judge(task="Review the whole image for visual context relevant to <goal>",
       pipeline_step="input_review", expected_output="The target is visually discernible",
       image_source="/data/<filename>")
   - rag_retrieve_docs(relevant_query)
   - recall_concepts("<the scientific goal>")   ← ALWAYS pair this with rag_retrieve_docs. It
     returns expert WHEN/DO/WHY/AVOID strategy heuristics for the task (thresholding approach,
     splitting touching objects, denoise-vs-quantify, metric/stats choice, acquisition trade-offs).

   NOTE: `plugin_manager` is deliberately NOT in this batch — see step 4b.

4a. RECORD THE MEASURED FACTS BEFORE CHOOSING A TOOL. As soon as
   `extract_image_metadata` returns, call:
     set_ledger_metadata(project_root=project_root, image_metadata={...})
   filling in AT LEAST: n_channels, bit_depth, pixel_size_um, n_z_slices,
   n_timepoints, dimensions — and `modality`, which is not measured like the rest
   (see below). These are the properties that mechanically ADMIT OR EXCLUDE a tool —
   a brightfield H&E image cannot use a fluorescent-nuclei model, whatever the prose
   suggests.

   `modality` is the one field in that record `extract_image_metadata` does NOT
   return. It is the CONTRAST MECHANISM (`brightfield`, `phase-contrast`, `DIC`,
   `H&E`, `confocal fluorescence`, `EM`, `microCT`, …) and **nothing infers it for
   you** — not the metadata tool, not the ledger. Establish it from what the user
   said, the acquisition metadata/filename, and the Vision Judge's description.
   Do NOT read it off the pixel layout: 8-bit RGB is not evidence of brightfield and
   a single 16-bit channel is not evidence of fluorescence — bit depth describes the
   CAMERA, not the contrast mechanism. A code rule that tried exactly that inference
   was measured 42% wrong against real project ledgers and has been removed, so there
   is no fallback behind you here. **If the file and the user's words do not settle
   it, ASK THE USER** — one short question, they always know, and it costs far less
   than segmenting for the wrong contrast mechanism. Never write `"unknown"`: a
   placeholder is read as no answer.

4b. DO NOT choose a tool in this phase. Tool routing now happens in PHASE 2, after the
   pipeline STEPS have been designed and written to `pipeline_plan` — see
   phase_2_planning.md. Deciding the tool here would pin the plan to a choice made
   before the steps existed, and the recommendation is rendered as a binding
   "USE THIS PLUGIN" line, so that pin is hard to undo.
   Phase 1 ends with the FACTS recorded (metadata, files, user preferences); Phase 2
   turns them into steps and only then asks which tool performs each.

   (Historical note, kept because it is the reason for the split: `plugin_manager` used
   to be issued in the step-4 parallel batch, concurrently with
   `extract_image_metadata`. It therefore decided from the task PROSE alone — the
   highest-variance input available — and the same H&E task scored 0.11 with one
   supervisor backbone and 0.75 with another, diverging at that call.)

   For reference, the call Phase 2 will make:
   - plugin_manager(task="<describe the scientific goal>", project_root=project_root)
     `plugin_manager` re-reads the ledger via PROJECT STATE, so the metadata recorded in
     4a is what it sees. Called in the step-4 batch instead, it would run CONCURRENTLY
     with `extract_image_metadata` and decide from the task PROSE ALONE — the highest-
     variance input there is. That is not hypothetical: on an H&E nuclear-segmentation
     task the same image scored 0.11 with one supervisor backbone and 0.75 with another,
     and the runs diverged at this line, before any parameter was chosen. The measured
     facts existed in the same turn and were never routed to the decision.
     Do NOT "optimise" this back into the parallel batch: the extra round-trip costs
     seconds against a multi-hour budget, and buys a tool choice grounded in the data
     rather than in wording.
     MANDATORY — call it on EVERY new project, even when you think the task is
     "easy enough" for stock `IJ.run` commands (Find Maxima, Analyze Particles,
     auto-thresholding, etc.). The manager's response provenance — including
     `recommended_plugin=None` — must be recorded in the ledger. Without this
     record, downstream phases have no skill pointer for the debugger to
     reference.
     The plugin manager is the TOOL ROUTER: it surveys Fiji plugins, Python packages,
     AND napari plugins (micro_sam), and returns a structured recommendation with a
     `backend` per tool ("imagej_coder" / "python_data_analyst" / "napari" / "core").
     For a MULTI-STEP task it also returns `pipeline_steps` — each step routed to its own
     backend (e.g. Fiji-register → micro_sam-segment → Python-measure). Prefer a
     specialised tool over custom code, but honour each step's backend — do NOT force
     everything onto Groovy/imagej_coder.

5. Ask the user for clarification if the task is ambiguous (use biologist-friendly language).

6. Ask the user how they prefer to work:
   - **Script-based (recommended)**: The agent generates and runs Groovy scripts automatically — faster, reproducible, no manual clicking.
   - **UI-guided**: The agent guides you step-by-step through Fiji menus and dialogs.
   Record the answer as `operating_mode`: "script" or "ui".

7. LEDGER: After gathering is complete, call set_ledger_metadata to record:
   - scientific_goal (one sentence)
   - operating_mode ("script" or "ui")
   - image_metadata (bit depth, pixel size, channels, number of images,
     and `background_mode` from `threshold_suggestions` — `"dark"` for fluorescence,
     `"bright"` for brightfield/H&E. The coder reads this to pick the `"Otsu dark"` vs
     `"Otsu"` suffix; if omitted, it falls back to a runtime stats check)
   - When Vision Judge is enabled, vlm_assessment (compact typed handoff from the input_review call: pipeline_step,
     overall_verdict, summary, issues_found, recommended_action,
     image_paths_inspected, success). Treat visual observations as advisory and do
     not overwrite metadata or channel identity with visual guesses.
   - relevant_skill (use the skill_folder from plugin_manager's recommendation)
   - recommended_plugin (use the recommended_plugin name from plugin_manager).
     This is propagated to the executor, which must use this tool and not silently
     substitute an alternative. If plugin_manager returned no recommendation, omit this field.
   - If plugin_manager returned `pipeline_steps` (multi-step), also record `pipeline_plan`
     as the ordered step list, copying each step's tool + backend VERBATIM from the
     recommendation, in the form "<step>: <recommended_tool> (<backend>)". Do not invent or
     substitute tool names — use exactly what plugin_manager returned. Phase 2 reads this to
     delegate each step to the correct specialist (imagej_coder / python_data_analyst / napari).
