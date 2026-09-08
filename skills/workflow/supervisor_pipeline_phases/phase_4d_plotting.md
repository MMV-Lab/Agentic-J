# Step 4d — Visualization (python_data_analyst — Stage 2)

- Use the python_data_analyst do the plotting
- Only after Statistics_Results.csv exists.
- Delegate: write a plotting-only script that reads from Statistics_Results.csv.
- Plots must be saved as PNG (300 DPI) and SVG in figures/.
- FINAL PLOT VISUAL REVIEW: When `vlm_judge` is available in the current tools, after
  the plotting script succeeds and before Phase 5, call it once on each generated PNG
  figure with a stable `pipeline_step="plotting:<figure_filename>"`. This preserves one
  ledger assessment per figure while allowing a regenerated figure to replace its stale
  verdict. Ask it to check that titles, legends, axis and tick labels, annotations, and
  statistical marks are legible and not clipped,
  overlapping, overflowing, or obscuring the data; also check layout, contrast, and
  whether the visible plot content matches the scientific goal. Use the PNG rather than
  the SVG. Persist each typed handoff with `set_ledger_metadata(vlm_assessment=...)`.
  Relay WARN/FAIL issues to the user. Do not treat visual review as validation of the
  underlying values or statistics. If a plot is revised, review the regenerated PNG
  again before advancing.
- LEDGER: Call update_state_ledger(phase="4d", step="plotting", status="completed",
    details="Generated <N> figures. Saved PNG+SVG to figures/",
    script_path="<path>", output_paths=["figures/"])

## RECIPES (automatic — no action needed)

Plotting recipes are saved automatically: once the plot script runs cleanly, the
Librarian evaluates it in the background and decides on its own whether it is a
reusable, novel figure recipe worth keeping (skipping study-specific one-offs and
duplicates). You do NOT need to call save_recipe.
