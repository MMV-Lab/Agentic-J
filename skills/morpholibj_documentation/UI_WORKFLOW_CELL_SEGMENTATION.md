# MorphoLibJ — GUI Walkthrough: Segment Touching Cells (Distance-Transform Watershed)

Segment touching round objects, count them, measure them, and (optionally) compare to a
ground truth — using only Fiji's GUI. Verified against MorphoLibJ **1.6.5**.

**Test image:** File ▸ Open Samples ▸ **Blobs (25K)** — 64 blobs on a dark background.

```
Original → [1] Threshold → binary
         → [2] Chamfer Distance Map (bright = object centre)
         → [3] Extended Maxima → Connected Components  (one labelled seed per object)
         → [4] Invert distance map + Marker-controlled Watershed
         → [5] Clean up labels → [6] Count → [7] Measure → [8] Colour → [9] Compare
```

> ⚡ **Shortcut:** steps 2–4 can be replaced by a single **Plugins ▸ MorphoLibJ ▸ Binary
> Images ▸ Distance Transform Watershed** on the binary mask. The steps below show the
> explicit pipeline for full control.

---

## Before you start
- Confirm **Plugins ▸ MorphoLibJ** exists (install IJPB-plugins via Help ▸ Update… if not).
- Set **Process ▸ Binary ▸ Options…** → ☑ **Black background**.

---

## Step 1 — Threshold to binary

> ⚠ **Blobs has an inverting LUT** (objects are bright in value but display dark). Run
> **Image ▸ Lookup Tables ▸ Grays** first, otherwise the mask comes out inverted and you
> end up segmenting the background. (Real fluorescence images usually don't need this.)

1. Select **blobs**. **Image ▸ Adjust ▸ Threshold…** (`Shift+T`).
2. ☑ **Dark background**, pick **Otsu** (or Default), click **Auto** — the *objects* (not the
   gaps between them) should turn red. If the background is red instead, see the LUT note above.
3. **Apply**. Close the Threshold dialog.

**Check:** Analyze ▸ Histogram should show only values 0 and 255, with the foreground (objects)
= 255. Optionally **Plugins ▸ MorphoLibJ ▸ Filtering ▸ Fill Holes (Binary/Gray)**.

---

## Step 2 — Chamfer Distance Map
1. With the binary image active: **Plugins ▸ MorphoLibJ ▸ Binary Images ▸ Chamfer Distance Map**.
2. **Distances:** `Borgefors (3,4)` (or `Chessknight (5,7,11)` for more accuracy) ·
   **Output type:** `32 bits` · ☑ **Normalize weights** · **OK**.
3. A 32-bit map appears (bright at object centres). Rename it `dist`.
4. *(Recommended)* **Process ▸ Filters ▸ Gaussian Blur… sigma=2** on `dist` to suppress
   spurious maxima.

---

## Step 3 — Seeds: Extended Maxima → labelled markers
1. With `dist` active: **Plugins ▸ MorphoLibJ ▸ Minima and Maxima ▸ Extended Min & Max**.
   - **Operation:** `Extended Maxima` · **Dynamic:** `2` (raise to merge multiple peaks per
     object; lower to split) · **Connectivity:** `4` · **OK**. → binary `maxima`.
2. **Plugins ▸ MorphoLibJ ▸ Binary Images ▸ Connected Components Labeling**.
   - **Connectivity:** `4` · **Type of result:** `16 bits` · **OK**. → `markers`.
   - *(For >65 535 seeds choose `float`, not "32 bits".)*

> 💡 Each object should get exactly one seed. Many seeds inside one object → increase the
> distance-map blur or the Dynamic value.

---

## Step 4 — Invert distance map and run Watershed
1. Select `dist`. **Image ▸ Adjust ▸ Brightness/Contrast ▸ Reset** (so the 32-bit invert uses
   the true range). **Image ▸ Duplicate…** → `dist-inv`. **Edit ▸ Invert** on `dist-inv`.
2. **Plugins ▸ MorphoLibJ ▸ Segmentation ▸ Marker-controlled Watershed**.
   - **Input:** `dist-inv` · **Marker:** `markers` · **Mask:** the binary image ·
     **Compactness:** `0` · ☑ **Calculate dams** · ☐ **Use diagonal connectivity** (4-conn =
     rounder) · **OK**. → label image (rename `labels-raw`).

---

## Step 5 — Clean up the labels
**Plugins ▸ MorphoLibJ ▸ Label Images ▸ …**
1. **Remove Border Labels** → tick **Left/Right/Top/Bottom** → OK (drops partial edge objects).
2. **Label Size Filtering** → **Operation:** `Greater_Than`, **Size Limit (pixels):** `20`
   → OK (drops debris). Creates a new image.
3. **Remap Labels** (renumber 1…N). Rename the result `labels`.

---

## Step 6 — Count
**Analyze ▸ Histogram** on `labels` (set Bins high) — the number of non-zero bins = object
count. More reliable: the row count of the Analyze Regions table (Step 7).

---

## Step 7 — Measure
1. With `labels` active: **Plugins ▸ MorphoLibJ ▸ Analyze ▸ Analyze Regions**.
2. Tick **Area, Perimeter, Circularity, Equivalent Ellipse, Convexity, Max. Feret Diameter,
   Geodesic Diameter** → OK.
3. A table titled **`labels-Morphometry`** opens — one row per object. **File ▸ Save As…** → CSV.

---

## Step 8 — Colour overlay
**Plugins ▸ MorphoLibJ ▸ Label Images ▸ Labels To RGB** → **Colormap:** `Golden angle` ·
**Background:** `Black` · ☑ **Shuffle** → OK.

---

## Step 9 — Compare to ground truth (optional)
1. Open your ground-truth label image.
2. **Plugins ▸ MorphoLibJ ▸ Analyze ▸ Label Overlap Measures** → **Source:** `labels` ·
   **Target:** ground truth · ☑ Overlap ☑ Jaccard index ☑ Dice coefficient ☑ Volume Similarity → OK.
3. The `labels-all-labels-overlap-measurements` table reports Jaccard / Dice (1.0 = perfect).

---

## Troubleshooting
| Symptom | Cause | Fix |
|---------|-------|-----|
| Background gets segmented, not the objects | inverting LUT or wrong threshold direction | Image ▸ Lookup Tables ▸ **Grays**, re-threshold with ☑ Dark background |
| Each object split into many fragments | too many maxima / noisy distance map | larger Gaussian blur on `dist`, or higher **Dynamic** in Extended Maxima |
| Touching objects merge into one | too few seeds | lower **Dynamic**, check the mask is clean |
| Watershed floods the whole image | mask not set | set **Mask** to the binary image, not None |
| Empty measurement table | wrong image active, or looked at the default "Results" table | activate `labels`; the table is named `labels-Morphometry` |
| `Connected Components` overflow error | too many seeds for the type | choose **float** output |

## Image names at each step
| Name | Type | From |
|------|------|------|
| blobs | 8-bit binary | Step 1 |
| dist | 32-bit | Step 2 |
| maxima | 8-bit binary | Step 3 |
| markers | 16-bit label | Step 3 |
| dist-inv | 32-bit | Step 4 |
| labels-raw → labels | 16-bit label | Steps 4–5 |
| labels-rgb | RGB | Step 8 |
