# Prompting Guide

The agent works best when you give it enough context to make decisions without having to ask clarifying questions at every step. This page shows what good prompts look like and common pitfalls to avoid.

---

## The essentials: what to include upfront

The more context you give at the start, the fewer back-and-forth rounds are needed.

| What | Example |
|------|---------|
| **Goal** | "Segment nuclei and measure area and mean intensity per nucleus" |
| **Image details** | "16-bit TIFF, 3-channel fluorescence, channel 1 = DAPI, 1024×1024 px, ~50 images" |
| **File location** | "Images are in `/data/experiment_01/`" or "Image is open in the window" |
| **Output format** | "Save a CSV with one row per nucleus and a labelled mask as TIFF" |
| **Solving approach (UI/script)** | "I want to do this task using UI " |
| **Plugin preference (optional)** | "Use StarDist if possible" |

---

## Example prompts

**Minimal (agent will ask follow-up questions):**
> "Segment my cells."

**Better:**
> "Segment DAPI-stained nuclei in the 16-bit TIFFs in `/data/batch_01/`. Use StarDist with the `dsb2018_heavy_augment` model. Save a results table (area, mean intensity) and a labelled mask for each image."

**Batch processing:**
> "Run the same StarDist nuclei segmentation on all `.tif` files in `/data/`. Save one CSV per image named `<original_name>_results.csv` in `/data/results/`."

**Iterative refinement:**
> "The segmentation is merging touching nuclei. Can you add a watershed step to split them?"

**Asking about the current Fiji window:**
> "I have the TrackMate dialog open. What should I set for 'Estimated blob diameter' for nuclei that are roughly 10 µm and imaged at 0.2 µm/px?"

---

## Tips

- **Name the plugin** you want to use if you have a preference. The agent knows 24 plugins — telling it which one avoids unnecessary deliberation.
- **Provide the pixel size** when spatial measurements matter (e.g. "0.325 µm/px, 1.0 µm/slice").
- **Mention the channel** for multi-channel images ("segment objects in channel 2").
- **Ask for the script** if you want to reuse it: "Save the final working script so I can run it again."
- **Iterate step by step** for complex pipelines rather than asking for the full workflow at once. Get segmentation right first, then add measurement, then batch.
- **If it fails** ask the agent to try again. Sometimes it just gets confused, while other times the error is too severe.
---

## What to avoid

- Vague goals without image details ("analyse my data")
- Assuming the agent knows which image is open in Fiji (tell it the file path)
- Asking the agent to install many plugins at once (conflicts can occur; install one at a time)
