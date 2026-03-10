# MorphoLibJ — UI Workflow: Cell Segmentation via Distance Transform Watershed

A step-by-step guide to segment touching cells, count them, and compare the result
against a ground truth — using only Fiji's graphical interface. No scripting required.

**Test image:** File ▶ Open Samples ▶ **Blobs (25K)** — a built-in Fiji 8-bit sample
with 64 bright blobs on a dark background. It is used in all screenshots and steps below.

---

## Overview of the Pipeline

```
Original image
      │
[Step 1]  Threshold → binary mask
      │
[Step 2]  Chamfer Distance Map (MorphoLibJ)
      │  32-bit float: bright = centre of object, dark = near background
      │
[Step 3]  Regional Maxima (MorphoLibJ) → Connected Components Labeling (MorphoLibJ)
      │  one seed label per cell centre
      │
[Step 4]  Invert distance map (ImageJ) + Marker-controlled Watershed (MorphoLibJ)
      │
[Step 5]  Post-process labels → count cells → measure → compare
```

---

## Before You Start

- Open Fiji.
- Confirm MorphoLibJ is installed: the menu **Plugins ▶ MorphoLibJ** must exist.
  If not, install it (Help ▶ Update… ▶ Manage update sites ▶ activate **IJPB-plugins**
  ▶ Apply changes ▶ Restart Fiji).
- Open your test image: **File ▶ Open Samples ▶ Blobs (25K)**.

---

## Step 1 — Threshold to Binary

The distance transform requires a binary input (pixel values 0 and 255 only).

1. Make sure **blobs** is the active image.
2. **Image ▶ Adjust ▶ Threshold…** (`Shift+T`)
   - In the Threshold dialog, click **Auto** to apply an automatic threshold.
   - The thresholded foreground (blobs) should appear **red**.
   - If blobs are not selected: check **Dark background** and click **Auto** again.
3. Click **Apply**.
   - In the "Convert Stack to Binary" dialog (if it appears), choose **Calculate threshold for each image** and click **OK**.
4. Close the Threshold dialog.

**Result:** The image `blobs` is now binary — foreground blobs are white (255),
background is black (0).

> ⚠ **Check:** Run **Analyze ▶ Histogram** — you should see only two bars at
> values 0 and 255. If you see other values, re-threshold with the **Convert to Mask**
> command: **Process ▶ Binary ▶ Convert to Mask**.

---

## Step 2 — Chamfer Distance Map

Each foreground pixel is assigned its distance to the nearest background pixel.
The result is bright at object centres and dark near object edges.

1. Make sure `blobs` (the binary image) is active.
2. **Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Chamfer Distance Map**
3. Dialog settings:
   - **Distances:** `Borgefors (3,4)` *(standard 2D approximation; use Chessknight (5,7,11) for higher accuracy)*
   - **Output type:** `32 bits`
   - ☑ **Normalize weights** *(scales values to approximate Euclidean distances in pixels)*
4. Click **OK**.

**Result:** A new 32-bit image appears (e.g. `blobs-dist`). Rename it for clarity:
double-click the title bar and type `dist`.

> 💡 **Inspect:** Use **Image ▶ Adjust ▶ Brightness/Contrast** to explore the
> distance values. The brightest pixels are at blob centres, which is exactly where
> we want to place the watershed seeds.

---

## Step 3 — Detect Regional Maxima and Label Seeds

Regional maxima of the distance map are at cell centres — one maximum per cell.

### 3a — Find Regional Maxima

1. Make `dist` the active image.
2. **Plugins ▶ MorphoLibJ ▶ Minima and Maxima ▶ Regional Min & Max**
3. Dialog settings:
   - **Operation:** `Regional Maxima`
   - **Connectivity:** `4` *(orthogonal only; use 8 for diagonal too)*
4. Click **OK**.

**Result:** A binary image appears with white pixels at each regional maximum.
Rename it `maxima-binary`.

> 💡 **Check:** Each blob should contain at least one white dot. If you see hundreds
> of tiny dots inside a single blob, the distance map has noise. Go back and apply a
> light Gaussian blur to the distance map (**Process ▶ Filters ▶ Gaussian Blur… sigma=1**)
> and repeat this step. Alternatively, use **Extended Min & Max → Extended Maxima**
> with a small **Dynamic** value (e.g. 1–3) instead of Regional Maxima.

### 3b — Label each maximum region with a unique integer

Watershed needs each seed to carry a unique integer — not just 0/255.

1. Make `maxima-binary` the active image.
2. **Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Connected Components Labeling**
3. Dialog settings:
   - **Connectivity:** `4`
   - **Output type:** `16 bits` *(supports up to 65 535 seeds)*
4. Click **OK**.

**Result:** A new label image appears. Rename it `maxima-lbl`.

Close `maxima-binary` — it is no longer needed.

---

## Step 4 — Invert Distance Map and Run Watershed

Watershed floods a landscape **upward from minima**. To flood from object centres
(which are **maxima** of the distance map), we must invert it first.

### 4a — Duplicate and invert the distance map

1. Make `dist` active.
2. **Image ▶ Duplicate…** (`Shift+D`) → name it `dist-inv` → click **OK**.
3. Make `dist-inv` active.
4. **Edit ▶ Invert** (`Shift+I`)
   — or via **Image ▶ Lookup Tables ▶ Invert LUT** (do NOT use this — it only
   inverts display, not pixel values; you need **Edit ▶ Invert**).

**Result:** `dist-inv` now has its darkest values at blob centres (= minima for
the watershed to flood from) and its brightest values at blob edges.

> ⚠ For a 32-bit image, **Edit ▶ Invert** uses the display minimum and maximum.
> Before inverting, run **Image ▶ Adjust ▶ Brightness/Contrast ▶ Reset** to make
> sure the display range reflects the true pixel range.

### 4b — Marker-controlled Watershed

1. **Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Marker-controlled Watershed**
2. Dialog settings:
   - **Input:** `dist-inv` *(the landscape to flood)*
   - **Marker:** `maxima-lbl` *(the labelled seeds)*
   - **Mask:** `blobs` *(the binary image restricts flooding to foreground)*
   - ☑ **Calculate dams** *(adds 0-valued watershed lines between cells)*
   - **Use diagonal connectivity:** unchecked *(4-connectivity = rounder cell shapes)*
3. Click **OK**.

**Result:** A label image appears (e.g. `maxima-lbl-watershed`). Rename it `labels-raw`.

---

## Step 5 — Post-process the Label Image

Remove incomplete cells at the border and discard tiny debris.

1. Make `labels-raw` active.
2. **Plugins ▶ MorphoLibJ ▶ Label Images ▶ Label Edition**
   - Click **Remove in border** — removes any cell that touches the image edge (incomplete cells).
   - Click **Size opening** — set a minimum area (e.g., `50`); labels below it are removed.
   - Click **Done** — confirms all changes and closes the plugin.
3. **Plugins ▶ MorphoLibJ ▶ Label Images ▶ Remap Labels**
   — renumbers labels 1…N to close any gaps left by removed labels.
4. Rename the image `labels`.

---

## Step 6 — Count the Cells

The number of distinct non-zero label values = number of cells.

**Method A — Quick count from Histogram:**
1. Make `labels` active.
2. **Analyze ▶ Histogram** → set **Bins = 65535** (or increase until you see sharp peaks).
3. Each non-zero bin with a count > 0 represents one label (one cell).
   The number of such bins = cell count.

**Method B — From ResultsTable (more reliable):**
1. Follow Step 7 (Analyze Regions) below.
2. The number of rows in the ResultsTable = number of cells.

---

## Step 7 — Measure Region Properties

1. Make `labels` the active image (**not** the RGB overlay from Step 8).
2. **Plugins ▶ MorphoLibJ ▶ Analyze ▶ Analyze Regions**
3. Tick your desired measurements (suggested):
   - ☑ Area
   - ☑ Perimeter
   - ☑ Circularity
   - ☑ Inertia Ellipse
   - ☑ Convexity
4. Click **OK**.

**Result:** A **ResultsTable** opens. Each row = one cell.
The row count at the bottom of the table = total cell count.

**Save:** In the ResultsTable window → **File ▶ Save As…** → save as `.csv`.

---

## Step 8 — Create a Colour Overlay

1. Make `labels` active.
2. **Plugins ▶ MorphoLibJ ▶ Label Images ▶ Set Label Map**
   - **Colormap:** `Golden angle`
   - **Background:** `Black`
   - ☑ **Shuffle**
   - Click **OK**.
3. *(Optional)* Use **Analyze ▶ Tools ▶ ROI Manager** to overlay the label
   boundaries on the original image for a publication-quality figure.

---

## Step 9 — Compare Against Ground Truth (Optional)

If you have a ground-truth label image (e.g. manually annotated), compare it to
your result to quantify segmentation accuracy.

1. Open your ground-truth label image (**File ▶ Open…**).
2. **Plugins ▶ MorphoLibJ ▶ Analyze ▶ Label Overlap Measures**
3. Dialog:
   - **Source image:** `labels` *(your segmentation result)*
   - **Target image:** your ground-truth label image
   - ☑ **Overlap** ☑ **Jaccard** ☑ **Dice**
4. Click **OK**.

**Result:** A ResultsTable with per-label and global statistics:

| Metric | Meaning | Perfect value |
|--------|---------|--------------|
| Jaccard Index | Intersection / Union per label | 1.0 |
| Dice Coefficient | 2 × Intersection / (A + B) | 1.0 |
| Total Overlap | Labels correctly identified | 1.0 |
| False Negative Error | GT labels missed by result | 0.0 |
| False Positive Error | Extra labels not in GT | 0.0 |

Save this table via **File ▶ Save As…** in the ResultsTable window.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Every blob is split into many tiny fragments | Too many regional maxima; noisy distance map | Blur distance map (Gaussian σ=1) before Step 3, or use **Extended Maxima** with dynamic=1–3 |
| Adjacent cells merge into one segment | Too few seeds; dynamic too high | Lower **Dynamic** (Extended Maxima) or check that binary mask is clean |
| Watershed fills entire image outside blobs | Mask not set correctly in dialog | Make sure **Mask** is set to `blobs` (the binary image), not `None` |
| Empty ResultsTable after Analyze Regions | Wrong image active | Make integer-label image `labels` active, not the RGB overlay |
| `dist` image looks flat / all one colour | Brightness/Contrast not adjusted | Image ▶ Adjust ▶ Brightness/Contrast ▶ Reset |
| Set Label Map gives black image | Label values are all zero | Check that Remap Labels was applied; use Analyze ▶ Histogram to verify non-zero values |
| Border labels not removed | Labels were remapped before Remove in border | Reverse the order: Remove in border → Size opening → Remap Labels |

---

## Quick Reference — Image Names at Each Step

| Image name | Type | Created at |
|------------|------|-----------|
| `blobs` | 8-bit binary | Step 1 |
| `dist` | 32-bit float | Step 2 |
| `maxima-binary` | 8-bit binary | Step 3a |
| `maxima-lbl` | 16-bit label | Step 3b |
| `dist-inv` | 32-bit float | Step 4a |
| `labels-raw` | 16-bit label | Step 4b |
| `labels` | 16-bit label | Step 5 |
| `labels-overlay` | RGB | Step 8 |
