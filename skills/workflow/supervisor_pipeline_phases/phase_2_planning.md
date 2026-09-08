# Phase 2 — Task Planning

Read the state ledger to check `operating_mode` before planning.

**STEPS FIRST, TOOL SECOND.** Decide WHAT has to happen and in what order, and record
that as `pipeline_plan`, BEFORE asking which tool performs each step. Choosing the tool
first inverts the dependency: the recommendation is rendered as a binding
"USE THIS PLUGIN" line, so an early pick silently constrains the plan built around it,
and the run's outcome is decided before the steps are even known. Planning first also
gives the tool router two things it otherwise never has — the measured image properties
(recorded in Phase 1, step 4a) and the list of steps that actually need a tool.

So the order within this phase is:
  1. `recall_concepts(...)` — strategy heuristics (see below).
  2. Design the pipeline as STEPS and write it with
     `set_ledger_metadata(pipeline_plan=[...])`. Name each step for what it does
     ("segment_nuclei", "measure_intensity"), not for the tool you imagine using.
  3. ONLY NOW call `plugin_manager(task=..., project_root=project_root)` to route those
     steps. It re-reads PROJECT STATE, so it sees both the metadata and the plan, and it
     can return `pipeline_steps` routing each step to its own backend.
  4. Record the result (`recommended_plugin`, `relevant_skill`, per-step backends).
     PROJECT STATE also renders a "TRY IN THIS ORDER" default for this modality where one
     exists — treat it as the starting point and depart from it only with a recorded reason.

BEFORE designing any pipeline (BOTH modes): call
`recall_concepts("<scientific goal + the processing steps you are considering>")` to pull
strategic WHEN/DO/WHY/AVOID heuristics from the concept library (thresholding strategy,
splitting touching objects, denoise-vs-quantify, metric/statistics choice, 3D anisotropy,
acquisition/figure trade-offs). Let the returned **DO**s shape the pipelines you propose and
the **AVOID**s rule options out. Whenever you also look something up with `rag_retrieve_docs`,
call `recall_concepts` alongside it.

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

   PER-STEP BACKEND ROUTING: plugin_manager may route different steps to different software
   (its `pipeline_steps`, recorded as pipeline_plan in Phase 1). Preserve that routing —
   each step names both its TOOL and its BACKEND, and Step 3 below delegates accordingly:
     • backend "imagej_coder"        → imagej_coder writes/executes the Groovy for that step.
     • backend "python_data_analyst" → python_data_analyst writes the Python; pass the step's
       `env` so its script carries `# imagentj-env: <env>` ("napari-mcp" for micro_sam batch).
     • backend "napari"              → YOU drive micro_sam in the live viewer via the
       mcp__napari_mcp__* tools (execute_code / add_layer / screenshot); save the label mask
       to a file so the next step can read it.
     • backend "core"                → imagej_coder writes plain IJ.run().
   A single pipeline may legitimately span all of these. Name the backend for every step in
   each proposed pipeline so the user (and later phases) know who runs what.

2. Data persistence rule: variables do not survive between scripts.
   - Step N must SAVE its output (CSV/TIFF) to a file.
   - Step N+1 must READ that file from a hardcoded path.

3. Delegate each step to the backend plugin_manager assigned it (see PER-STEP BACKEND ROUTING),
   one step at a time. Never hand over the full pipeline at once. Image-processing steps go to
   imagej_coder (Groovy), python_data_analyst (Python), or your own napari MCP tools per the routing.

4. Delegate statistics and plotting to python_data_analyst (always Python — never Fiji).

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
