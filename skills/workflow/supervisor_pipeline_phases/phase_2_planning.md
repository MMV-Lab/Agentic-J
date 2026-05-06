# Phase 2 — Task Planning

Read the state ledger to check `operating_mode` before planning.

## Script-based mode (operating_mode = "script")

1. Design a pipeline broken into isolated, sequential scripts:
   Pre-processing → Segmentation → Measurement → Statistics → Plotting
   For each step, a separate script is generated and executed. NEVER combine steps into one script.
   ALWAYS apply preprocessing adjusted to the task.
   For Image Processing generate 3 different approaches for the pipeline. Then ask the user to choose one of them. NEVER generate just one pipeline.

   PLUGIN RECOMMENDATION DISCIPLINE: If plugin_manager returned a recommendation in Phase 1,
   AT LEAST ONE of the three proposed pipelines MUST use that plugin as the core step
   (e.g., if TurboReg was recommended, one pipeline uses TurboReg for registration; if
   StarDist was recommended, one pipeline uses StarDist for segmentation). Do not
   silently replace it with a generic alternative. The other pipelines may explore
   different approaches, but each pipeline description must name the plugin(s) it uses
   so the user is choosing knowingly.

2. Data persistence rule: variables do not survive between scripts.
   - Step N must SAVE its output (CSV/TIFF) to a file.
   - Step N+1 must READ that file from a hardcoded path.

3. Delegate IO Check and Image Processing to imagej_coder separately. Never hand over the full pipeline at once.

4. Delegate statistics and plotting to python_data_analyst.

## UI-guided mode (operating_mode = "ui")

1. Outline the same logical pipeline stages but as a sequence of manual Fiji steps, not scripts.
   Present 2–3 approach options (e.g. different threshold methods) and let the user choose.

2. For each stage, describe: which Fiji menu to open, which plugin to launch, and what parameters to set.
   After each instruction, tell the user "if you get stuck on any parameter, let me know and I'll take a look."
   Only call `capture_plugin_dialog` if the user says they are stuck or confused — not proactively.
   Do NOT call imagej_coder or imagej_debugger in UI mode.

3. After each step, use `inspect_all_ui_windows` to verify the output is correct before proceeding.

## Both modes

LEDGER: After the user chooses a pipeline, call set_ledger_metadata to record:
   - pipeline_plan (ordered list of step names)
   - key_decision ("User chose Pipeline B: Otsu threshold → watershed segmentation")
