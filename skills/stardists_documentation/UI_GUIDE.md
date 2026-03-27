# StarDist — UI GUIDE

StarDist is accessible via **Plugins ▶ StarDist ▶ StarDist 2D** in the Fiji menu bar.

> **Before you start:** Confirm StarDist is installed. The menu **Plugins ▶ StarDist**
> must be visible. If not, install it (Help ▶ Update… ▶ Manage update sites → tick
> **CSBDeep**, **StarDist**, **TensorFlow** → Apply changes → Restart Fiji).

---

## The StarDist 2D Dialog

Launch: **Plugins ▶ StarDist ▶ StarDist 2D**

The dialog has three collapsible sections:

---

### Section 1 — Model

| Control | Description |
|---------|-------------|
| **Model** dropdown | Select a built-in model or a custom model. |

**Available built-in models:**

| Model name | Best for |
|------------|---------|
| `Versatile (fluorescent nuclei)` | Fluorescence images with round nuclei (DAPI, Hoechst, etc.) |
| `DSB 2018 (from StarDist 2D paper)` | Fluorescence nuclei; alternative to Versatile |
| `Versatile (H&E nuclei)` | Histology images stained with haematoxylin and eosin |

To use a custom model: select `Model (.zip) from File` or `Model (.zip) from URL`
in the dropdown — an additional path/URL field appears.

**Input normalisation:**
- ☑ **Normalize Image** — recommended for most images. Applies percentile-based
  contrast stretching before neural network inference.
- **Percentile low** — lower clip point (default: `1.0`). Pixels below this percentile
  map to 0 after normalisation.
- **Percentile high** — upper clip point (default: `99.8`). Pixels above this percentile
  map to 1.
- Uncheck **Normalize Image** only if your image is already normalised to [0, 1]
  or if you have a specific reason to skip it.

**Load default NMS parameters** button — resets `probThresh` and `nmsThresh` to the
values optimised for the selected built-in model.

---

### Section 2 — NMS Postprocessing

Non-Maximum Suppression (NMS) removes duplicate detections after the neural network
predicts objects.

| Control | Default | Effect |
|---------|---------|--------|
| **Probability/Score Threshold** | `0.5` | Minimum confidence for a detection to be kept. Higher = fewer objects, fewer false positives. Lower = more objects, may include false positives. |
| **Overlap Threshold** | `0.4` | Maximum allowed Intersection over Union (IoU) between two detections. Higher = more overlapping objects allowed. Lower = more aggressive suppression of overlaps. |

**Output type** dropdown:

| Option | What is created |
|--------|----------------|
| `Label Image` | New image window with integer labels (1 per object, 0 = background) |
| `ROI Manager` | All detections added to the ImageJ ROI Manager as polygon outlines |
| `Both` | Label image + ROI Manager entries |

> 💡 **Tip:** Use `Both` when you want both a visual overlay and the ability to
> measure shapes. Use `ROI Manager` alone when batch processing and you only need counts.

---

### Section 3 — Advanced Options

| Control | Default | Description |
|---------|---------|-------------|
| **Custom model path** | — | Path to a `.zip` file or URL (only visible when custom model is selected) |
| **Number of Tiles** | `1` | Splits the image into a grid of N tiles for inference. Increase if you see out-of-memory errors on large images. Common values: 1 (small images), 4, 9, 16. |
| **Boundary Exclusion** | `2` | Objects within this many pixels of the image border are suppressed. Set to `0` to keep objects at the edge. |
| **ROI Position** | `Automatic` | How ROIs are placed in stacks. `Automatic` = correct for single 2D images. Use `Stack` or `Hyperstack` for time-lapse. |
| **Load defaults** button | — | Resets all NMS parameters to the selected model's optimised defaults. |
| **Restore defaults** button | — | Resets all parameters in the entire dialog to factory defaults. |

---

## Running the Plugin

1. Open a 2D grayscale image (or extract the channel of interest from a multi-channel image).
2. **Plugins ▶ StarDist ▶ StarDist 2D**
3. Set the model and parameters.
4. Click **OK**.

The neural network runs inference. Progress is shown in the Fiji log window.
When complete, the selected output(s) appear automatically:
- A new window `"Label Image"` if Label Image output was selected.
- ROI Manager populated with polygon outlines if ROI Manager output was selected.

---

## Inspecting and Counting Results

### From the Label Image

- Use **Analyze ▶ Histogram** to verify the image has non-zero values.
- The maximum value in the label image = total number of detected cells
  (assuming labels 1…N without gaps).
- Measure region properties via **Analyze ▶ Analyze Particles…** or via MorphoLibJ's
  **Analyze Regions** if MorphoLibJ is installed.

### From the ROI Manager

- Open the ROI Manager (**Analyze ▶ Tools ▶ ROI Manager…** or Ctrl+Shift+T).
- The entry count at the bottom of the ROI Manager = number of detected cells.
- To overlay outlines: click **Show All** in the ROI Manager, then look at the image.
- To measure all cells: click **Deselect**, then click **Measure**.
  A Results Table opens with one row per cell.

---

## Post-processing the Label Image in the UI

After StarDist produces a label image, you can refine it with standard Fiji tools
or (if installed) with MorphoLibJ's label utilities:

| Task | How |
|------|-----|
| Remove cells at the edge | Plugins ▶ MorphoLibJ ▶ Labels ▶ Remove Border Labels |
| Remove very small detections | Plugins ▶ MorphoLibJ ▶ Labels ▶ Label Size Opening (set min area) |
| Renumber labels 1…N | Plugins ▶ MorphoLibJ ▶ Labels ▶ Remap Labels |
| Create colour overlay | Plugins ▶ MorphoLibJ ▶ Labels ▶ Labels to RGB |
| Measure shape properties | Plugins ▶ MorphoLibJ ▶ Analyze ▶ Analyze Regions |
| Compare to ground truth | Plugins ▶ MorphoLibJ ▶ Analyze ▶ Label Overlap Measures |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Plugin not found in menu | StarDist not installed | Help ▶ Update… → tick CSBDeep, StarDist, TensorFlow → Apply → Restart |
| Out-of-memory / crash | Image too large for single inference | Increase **Number of Tiles** (try 4, 9, or 16) |
| Too many false detections | `probThresh` too low | Raise **Probability/Score Threshold** (e.g. 0.5 → 0.7) |
| Adjacent objects not separated | `nmsThresh` too high | Lower **Overlap Threshold** (e.g. 0.4 → 0.3) |
| Objects at image edge missing | `excludeBoundary` too high | Set **Boundary Exclusion** to 0 |
| Poor segmentation with built-in model | Image type mismatch | Use `Versatile (fluorescent nuclei)` for fluorescence; `Versatile (H&E nuclei)` for histology |
| All output is background (label = 0) | Wrong channel active | Extract / select the nuclear channel before running |
| Very slow inference | CPU only; large image | Enable GPU (Edit ▶ Options ▶ TensorFlow) or increase Tiles to reduce per-tile memory |
