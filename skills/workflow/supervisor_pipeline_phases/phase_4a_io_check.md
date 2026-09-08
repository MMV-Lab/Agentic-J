# Step 4a — IO Check (imagej_coder)

- Verify all input files are accessible.
- Open one sample image per condition.
- Confirm with inspect_all_ui_windows.
- INPUT VISUAL REVIEW: When `vlm_judge` is available in the current tools, call it on
  an exact representative input path alongside `extract_image_metadata`, using
  `pipeline_step="input_review"`. Request advisory visual context relevant to the
  scientific goal: visible structures, focus, contrast/background, saturation,
  artifacts, heterogeneity, and whether the target is discernible. Never let visual
  guesses overwrite numeric metadata, calibration, channel names, or user-provided
  facts. Persist the typed handoff with `set_ledger_metadata(vlm_assessment=...)`.
- LEDGER: Call update_state_ledger(phase="4a", step="io_check", status="completed", details="Verified N images accessible in <path>")
