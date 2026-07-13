# Step 4d — Visualization (python_data_analyst — Stage 2)

- Use the python_data_analyst do the plotting
- Only after Statistics_Results.csv exists.
- Delegate: write a plotting-only script that reads from Statistics_Results.csv.
- Plots must be saved as PNG (300 DPI) and SVG in figures/.
- LEDGER: Call update_state_ledger(phase="4d", step="plotting", status="completed",
    details="Generated <N> figures. Saved PNG+SVG to figures/",
    script_path="<path>", output_paths=["figures/"])

## RECIPES (automatic — no action needed)

Plotting recipes are saved automatically: once the plot script runs cleanly, the
Librarian evaluates it in the background and decides on its own whether it is a
reusable, novel figure recipe worth keeping (skipping study-specific one-offs and
duplicates). You do NOT need to call save_recipe.
