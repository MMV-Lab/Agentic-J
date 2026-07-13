# Step 4b — Image Processing (imagej_coder)

- LEDGER: Call read_state_ledger FIRST to recall the pipeline plan and any completed steps.
- For each step in the pipeline, a separate script is generated and executed. NEVER combine steps into one script.

NEGATIVE EXAMPLE (do not do this):
❌ Task: "Do registration, then thresholding, then segmentation" → give all the instruction at once to the coder

POSITIVE EXAMPLE (do this):
✅ Task: "Do registration, then thresholding, then segmentation" 
→ Write a script for registration where the output is saved to processed images
→ Write a script for thresholding that reads the registered images and saves the thresholded images
→ Write a script for segmentation that reads the thresholded images and saves the segmented images

- Call rag_retrieve_mistakes before delegating.
- Call rag_retrieve_docs to do an extensive literature review on the best practices for each step (eg. preprocessing, thresholding etc.) and relay that information to the coder.
- LEDGER: After EACH rag_retrieve_docs call, record the finding:
  set_ledger_metadata(project_root, rag_reference={
    "query": "<your query>", "step": "<step_name>",
    "finding": "<one-line key takeaway for the coder>"
  })
- Generate and verify scripts one step at a time.

## SAMPLE VERIFICATION RULE

After executing the single-image verification script:

1. Show the user the result and ask for approval.
2. SIMULTANEOUSLY call imagej_coder to generate the batch version of the script.
   Tell it: "Batch version of [script_path]: add IJ.runMacro("setBatchMode(true);"), loop over all images, 
   wrap in try/catch, remove show() calls. Do not execute yet."
3. When the user approves, execute the already-generated batch script immediately.
4. If the user requests changes, send the batch script to imagej_debugger and the single-image verification script.
5. Loop until the user approves the single-image script. Only execute the batch script once the single-image version is approved.

## LEDGER

After EACH processing step (single-image verified + batch executed), call:
  update_state_ledger(phase="4b", step="<step_name>", status="completed",
    details="<what was done and key parameters>",
    script_path="<path>", output_paths=["<output_dir>"],
    parameters={"threshold_method": "Otsu", ...})

## RECIPES (automatic — no action needed)

Recipes are saved automatically. The moment a script runs cleanly via
execute_script, the Librarian evaluates it in the background and decides on its
own whether it is a generalizable, novel recipe worth keeping (skipping one-offs
and duplicates) and writes it with its own name/description. You do NOT need to
call save_recipe — only use it to force-save a specific script you don't want
left to the automatic decision.
