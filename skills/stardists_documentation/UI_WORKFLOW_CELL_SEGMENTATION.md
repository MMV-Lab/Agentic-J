# StarDist — UI Workflow: Nuclei Segmentation, Cell Counting, and Comparison

A complete, step-by-step guide to running StarDist 2D from the Fiji GUI — no scripting
required. You will segment nuclei in a fluorescence image, count the detected cells,
measure their properties, and optionally compare the result against a ground truth.

**Test image:** A suitable public test image can be downloaded from the
[Broad Bioimage Benchmark Collection (BBBC008)](https://data.broadinstitute.org/bbbc/BBBC008/BBBC008_v1_images.zip)
— a set of 8-bit fluorescence nuclei images. Alternatively, use any 2D grayscale
image with round bright nuclei on a dark background.

---

## Prerequisites

- Fiji installed with update sites **CSBDeep**, **StarDist**, and **TensorFlow** enabled.
  Verify: **Plugins ▶ StarDist** must appear in the menu bar.
- A 2D single-channel fluorescence image open in Fiji.

---

## Pipeline Overview

```
Open 2D fluorescence image
        │
[Step 1]  (Optional) Prepare image — extract channel, convert to 8-bit
        │
[Step 2]  Run StarDist 2D — choose model and thresholds
        │           │
        │     Label Image (integer)   +   ROI Manager (polygon outlines)
        │
[Step 3]  Inspect and count cells
        │
[Step 4]  Measure cell properties (area, perimeter, etc.)
        │
[Step 5]  (Optional) Post-process label image
        │
[Step 6]  (Optional) Compare against ground truth
        │
[Step 7]  Save results
```

---

## Step 1 — Prepare Your Image

StarDist 2D works on **single-channel 2D grayscale images** only.

**If your image has multiple channels:**
1. **Image ▶ Color ▶ Split Channels** — this creates one image per channel.
2. Select the nuclear channel window (e.g. the DAPI channel).
3. Close the other channel windows.

**If your image is RGB:**
1. **Image ▶ Type ▶ 8-bit** to convert to grayscale.
   *(Or Image ▶ Color ▶ Split Channels, then use the relevant grey channel.)*

**If your image is a 3D stack:**
- StarDist 2D cannot process 3D stacks as a volume. Either select a single plane
  (**Image ▶ Stacks ▶ Z Project…**) or process slice-by-slice.

> 💡 Rename the image to something simple with no spaces for easier reference:
> **Image ▶ Rename…** → type `nuclei`

---

## Step 2 — Run StarDist 2D

1. Make sure `nuclei` (your prepared image) is the active window.
2. **Plugins ▶ StarDist ▶ StarDist 2D**

**Set the parameters:**

**Model section:**
- **Model:** `Versatile (fluorescent nuclei)` *(for standard fluorescence nuclei)*
- ☑ **Normalize Image** — leave checked
- **Percentile low:** `1.0` *(default — usually fine)*
- **Percentile high:** `99.8` *(default — usually fine)*

**NMS Postprocessing section:**
- **Probability/Score Threshold:** `0.5` *(start here; raise if too many false detections)*
- **Overlap Threshold:** `0.4` *(start here; lower if adjacent nuclei are merging)*
- **Output type:** `Both` *(creates both a label image and ROI outlines)*

**Advanced Options section:**
- **Number of Tiles:** `1` *(increase to 4 or 9 if you get an out-of-memory error)*
- **Boundary Exclusion:** `2` *(nuclei touching the edge are excluded; set to 0 to keep them)*
- **ROI Position:** `Automatic`

3. Click **OK**.

Fiji will run the neural network. Watch the Log window for progress messages.
When complete, two new windows appear:
- **`Label Image`** — integer label image (one value per nucleus)
- **ROI Manager** — filled with polygon outlines of all detected nuclei

> 💡 If you are using the `Versatile (H&E nuclei)` model for histology, click
> **Load defaults** in the Advanced section to set the model's optimised thresholds
> before clicking OK.

---

## Step 3 — Inspect Results and Count Cells

### Visually inspect the label image

1. Make `Label Image` the active window.
2. **Image ▶ Lookup Tables ▶ glasbey on dark** — assigns distinct colours to each label
   for easy visual inspection.
3. Use the mouse to hover over cells — the status bar shows the label value (= cell number).

### Check ROI outlines on the original image

1. Make your original `nuclei` image the active window.
2. In the ROI Manager, click **Show All** — polygon outlines appear over the image.
3. Zoom in to verify that touching nuclei are separated and outlines are accurate.

### Count the cells

**Method A — From ROI Manager:**
The number shown at the bottom of the ROI Manager (e.g. `8 ROIs`) = total cell count.

**Method B — From the label image maximum:**
1. Make `Label Image` active.
2. **Analyze ▶ Measure** — the `Max` value in the Results table = highest label number
   = total number of detected cells (assuming sequential labelling from 1).

> 💡 **Write down the cell count** — you will compare it to the ground truth in Step 6.

---

## Step 4 — Measure Cell Properties

1. In the ROI Manager, click **Deselect** (ensures all ROIs are measured, not just selected ones).
2. Make the original `nuclei` image the active window (so intensity measurements read from it).
3. **Analyze ▶ Set Measurements…** — tick:
   - ☑ Area
   - ☑ Mean gray value
   - ☑ Min & max gray value
   - ☑ Perimeter
   - ☑ Shape descriptors *(adds Circularity, AR, Roundness)*
   - ☑ Centroid
   - Click **OK**
4. In the ROI Manager, click **Measure** — a Results Table opens with one row per nucleus.

The number of rows in the Results Table = total cell count (cross-check with Step 3).

> **Or use MorphoLibJ (if installed):**
> Make `Label Image` the active window, then:
> **Plugins ▶ MorphoLibJ ▶ Analyze ▶ Analyze Regions**
> This gives Crofton perimeter, circularity, ellipse fit, geodesic diameter, and more.

---

## Step 5 — (Optional) Post-process the Label Image

If you see incorrect detections, refine with standard Fiji or MorphoLibJ tools.

**Remove very small false positives:**
1. Make `Label Image` active.
2. *(MorphoLibJ required)* **Plugins ▶ MorphoLibJ ▶ Labels ▶ Label Size Opening**
   - **Min:** `50` *(or choose based on expected minimum cell area in pixels)*
   - Click **OK** — labels smaller than threshold are removed.
3. **Plugins ▶ MorphoLibJ ▶ Labels ▶ Remap Labels** — renumbers labels 1…N.

**Remove cells at the image border:**
1. **Plugins ▶ MorphoLibJ ▶ Labels ▶ Remove Border Labels**

**Create a coloured overlay:**
1. Make `Label Image` active.
2. **Plugins ▶ MorphoLibJ ▶ Labels ▶ Labels to RGB**
   - Colormap: `Golden angle`, ☑ Shuffle → Click **OK**

> After post-processing, re-count cells using Step 3 methods. The count will have changed.

---

## Step 6 — (Optional) Compare Against Ground Truth

If you have a manually annotated ground-truth label image, compare it to your
StarDist result to quantify segmentation accuracy.

**Requirement:** A ground-truth label image (integer labels, one value per cell)
open in Fiji alongside your `Label Image`.

1. *(MorphoLibJ required)* **Plugins ▶ MorphoLibJ ▶ Analyze ▶ Label Overlap Measures**
2. Set:
   - **Source image:** `Label Image` *(your StarDist result)*
   - **Target image:** your ground-truth label image
   - ☑ Overlap ☑ Jaccard ☑ Dice
3. Click **OK**.

A Results Table appears with per-label and global metrics:

| Metric | Meaning | Perfect score |
|--------|---------|--------------|
| Jaccard Index | Intersection / Union | 1.0 |
| Dice Coefficient | 2×Intersection / (A+B) | 1.0 |
| Total Overlap | Fraction of GT labels correctly found | 1.0 |
| False Negative Error | GT labels missed | 0.0 |
| False Positive Error | Extra labels not in GT | 0.0 |

> **Without MorphoLibJ:** Use **Analyze ▶ Analyze Particles…** on both the ground
> truth and the StarDist result to get area statistics for comparison.

---

## Step 7 — Save Results

| What to save | How |
|---|---|
| Cell count (quick) | Copy from ROI Manager count or Analyze ▶ Measure max value |
| Measurements Table | In Results Table window → **File ▶ Save As…** → `.csv` |
| Overlap metrics | In Label Overlap Measures table → **File ▶ Save As…** → `.csv` |
| Label Image (TIFF) | Make `Label Image` active → **File ▶ Save As ▶ Tiff…** |
| ROI set | In ROI Manager → **More ▶ Save…** → `.zip` |
| RGB overlay (PNG) | Flatten overlay onto image → **Image ▶ Overlay ▶ Flatten** → **File ▶ Save As ▶ PNG…** |

---

## Adjusting Parameters — Practical Guide

Start with the defaults. Then adjust one parameter at a time:

| Observation | Action |
|-------------|--------|
| Too many small noise detections | Raise `probThresh` (e.g. 0.5 → 0.65 → 0.8) |
| Real cells being missed | Lower `probThresh` (e.g. 0.5 → 0.35 → 0.2) |
| Touching nuclei merging into one | Lower `nmsThresh` (e.g. 0.4 → 0.2) |
| Nuclei being split into multiple detections | Raise `nmsThresh` (e.g. 0.4 → 0.5) |
| Edge cells incorrectly excluded | Set `excludeBoundary` to `0` |
| Very dim cells missed | Lower `percentileTop` (e.g. 99.8 → 99.0) |
| Background areas detected as cells | Raise `percentileBottom` (e.g. 1.0 → 5.0) |
| Memory error / crash | Increase `nTiles` (try 4, then 9) |

> 💡 After any parameter change, use **Plugins ▶ Macros ▶ Record…** while running the
> dialog to capture the exact command string for automation.

---

## Quick Reference — Image Windows at Each Step

| Window name | Type | Created at |
|-------------|------|-----------|
| `nuclei` (or your image) | 8-bit gray | Step 1 |
| `Label Image` | 16/32-bit integer | Step 2 |
| ROI Manager entries | Polygon ROIs | Step 2 |
| `Results` (measurements) | Table | Step 4 |
| `Label Image` (post-processed) | 16/32-bit integer | Step 5 (optional) |
| `Label Image-RGB` | RGB | Step 5 (optional) |
| `Label Overlap Measures` | Table | Step 6 (optional) |
