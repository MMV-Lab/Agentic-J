# Fast Track — Single-Operation Requests

Use this track when the user wants ONE self-contained image operation, not a
study. Examples: "segment the nuclei in this image", "threshold this", "count
the cells", "apply a median filter", "convert these to 8-bit", "register this
stack". One operation in, a processed image / mask / simple count out. No
cross-condition comparison, no statistics, no publication figures.

If the request is NOT like this — multiple chained processing steps, comparison
across groups/conditions, statistics, plots, a documented reproducible study, or
an ambiguous goal that needs real clarification — use the FULL pipeline instead
(phases 1→7). When in doubt, prefer the full pipeline.

The fast track is the full pipeline with the ceremony stripped out. Skip:
the 3-pipeline proposal, the separate IO-check round-trip, the RAG literature
review, the single-image→approve→batch split, and all of statistics / plotting /
summarization / documentation / QA. Keep the things that prevent wrong output:
correct image metadata, the debugger loop, a final look at the result, and —
for the operations where it matters — the plugin recommendation (see step 3).

## Steps

1. **Locate the image(s).** They are at `/data/<filename>`. If the path is
   ambiguous, call `inspect_folder_tree("/data")` ONCE. Only ask the user if it
   is still genuinely unclear which file(s) to use.

2. **Initialise minimally — one turn, parallel calls:**
   - `setup_analysis_workspace(project_name)` (short descriptive name).
   - `extract_image_metadata("/data/<filename>")` — the coder needs bit depth,
     channels, calibration, and `background_mode` or it invents values.
   Then ONE `set_ledger_metadata` recording: `scientific_goal`, `track="fast"`,
   `operating_mode` (default `"script"`), `image_metadata`, `channels` (if
   multi-channel), `input_files`. That single record is enough — do NOT spread
   ledger writes across every action the way the full pipeline does.

3. **Decide whether to consult `plugin_manager` — gate on the OPERATION, not on
   whether the coder later gets stuck.** A naive script often runs cleanly while
   producing a worse result, so "wait for the coder to fail" silently ships bad
   output for the operations below.
   - **CONSULT `plugin_manager`** (one call, even in fast mode) when the operation
     is one where plugin choice materially changes correctness: **segmentation of
     touching/biological objects (nuclei, cells), particle tracking, image
     registration, deconvolution, or other specialized analysis** — or whenever
     the user named a specific plugin. Record BOTH `recommended_plugin` AND
     `relevant_skill` in one `set_ledger_metadata` call so the coder uses the
     right tool and the debugger has a skill pointer. If it returns
     `recommended_plugin=None`, just proceed with stock operations.
   - **SKIP `plugin_manager`** for stock-sufficient operations: filters (median,
     Gaussian), bit-depth/format conversions, simple thresholding, basic
     Analyze Particles counts, and straightforward measurements.

4. **Delegate ONE script to `imagej_coder`.** Tell it to: open the image, apply
   the requested operation (with any minimal preprocessing the operation needs),
   save the output to `processed_images/`, save a measurements CSV to `data/` if
   the task involves counting/measuring, and `show()` the result. The IO check is
   folded in — no separate verification script. The coder queries its own recipes
   and mistakes; you do not pre-fetch RAG.

5. **`execute_script`.** On failure, run the normal debugger loop (send
   path + error + project_root to `imagej_debugger`, re-execute, save the lesson
   only after a clean run) — same as the full pipeline.

6. **Show and report.** `show_in_imagej_gui` the result and describe what you got
   in plain, biologist-friendly language.

7. **Offer escalation.** If the user now wants quantification across conditions,
   statistics, plots, or a written-up reproducible analysis, switch to the FULL
   pipeline: re-set `track="full"`, then enter Phase 2 (planning) and continue
   normally. The workspace, metadata, and any output you already produced carry
   over via the ledger — no need to re-gather.
