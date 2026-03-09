# MorphoLibJ — UI GUIDE

All MorphoLibJ plugins are accessible via **Plugins ▶ MorphoLibJ** in the Fiji menu bar.

---

## 1. Morphological Filters (2D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Morphological Filters

1. Open a grayscale or binary image.
2. Go to Plugins ▶ MorphoLibJ ▶ Filtering ▶ **Morphological Filters**.
3. In the dialog:
   - **Operation** — choose one of: Erosion, Dilation, Opening, Closing, Morphological Gradient, Morphological Laplacian, Black Top-Hat, White Top-Hat.
   - **Element** — structuring element shape: Disk, Square, Octagon, Diamond, Horizontal Line, Vertical Line, Line 45°, Line 135°.
   - **Radius** — radius in pixels (integer ≥ 1).
   - **Preview** checkbox — shows the result live.
4. Click **OK**. A new image is created.

**Parameter reference:**
| Parameter | Meaning |
|-----------|---------|
| Erosion | Replaces each pixel with the minimum in its neighborhood |
| Dilation | Replaces each pixel with the maximum |
| Opening | Erosion then dilation — removes bright structures smaller than structuring element |
| Closing | Dilation then erosion — fills dark holes smaller than structuring element |
| Morphological Gradient | Dilation minus Erosion — highlights edges |
| Morphological Laplacian | (Dilation + Erosion)/2 − original — enhances edges |
| White Top-Hat | Original minus Opening — enhances small bright structures |
| Black Top-Hat | Closing minus Original — enhances small dark structures |
| Disk | Circular/approximated disk structuring element |
| Radius | Half-size of the structuring element |

---

## 2. Morphological Filters (3D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Morphological Filters (3D)

Same operations as 2D. Additional structuring element options include **Cube** and **Ball** (spherical). Size can be set independently for X, Y, Z axes.

---

## 3. Directional Filters

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Directional Filtering

Use for images with thin curvilinear structures (blood vessels, cell walls).

1. Open a 2D grayscale image.
2. Plugins ▶ MorphoLibJ ▶ Filtering ▶ **Directional Filtering**.
3. Dialog parameters:
   - **Type** — how to combine oriented results: **Max** (enhances bright structures) or **Min** (enhances dark structures).
   - **Operation** — filter to apply at each orientation: Opening, Closing, Erosion, Dilation, Median.
   - **Line Length** — approximate length of linear structuring element (pixels).
   - **Direction Number** — number of orientations to sample (e.g. 32). Increase if Line Length is large.
4. Click **OK**.

---

## 4. Morphological Reconstruction

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Morphological Reconstruction

1. You need two open images: a **marker** and a **mask** (same dimensions).
2. Plugins ▶ MorphoLibJ ▶ Filtering ▶ **Morphological Reconstruction**.
3. Select **Marker image**, **Mask image**, reconstruction **Type** (By Dilation or By Erosion), and **Connectivity** (4 or 8 for 2D; 6 or 26 for 3D).
4. Click **OK**.

**Simpler variants (single-image):**
- **Kill Borders** (Plugins ▶ MorphoLibJ ▶ Filtering ▶ Kill Borders) — removes particles/regions touching the image border.
- **Fill Holes** (Plugins ▶ MorphoLibJ ▶ Filtering ▶ Fill Holes) — fills holes in binary particles or dark regions enclosed by bright crests in grayscale.

---

## 5. Minima and Maxima

**Menu:** Plugins ▶ MorphoLibJ ▶ Minima and Maxima

| Plugin | Purpose |
|--------|---------|
| Regional Min & Max | Finds exact regional minima or maxima |
| Extended Min & Max | Finds minima/maxima within a tolerance (less noise-sensitive) |
| Impose Min & Max | Forces a binary image to define regional minima/maxima |
| 3D variants | Same as above for 3D stacks |

**Extended Min/Max dialog:**
- **Operation** — Extended Minima or Extended Maxima.
- **Dynamic** — tolerance value (intensity range). Higher = fewer, larger extrema.
- **Connectivity** — 4 or 8 (2D); 6 or 26 (3D).

---

## 6. Attribute Filtering

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Grayscale Attribute Filtering

1. Open a grayscale image.
2. Plugins ▶ MorphoLibJ ▶ Filtering ▶ **Grayscale Attribute Filtering**.
3. Dialog:
   - **Operation** — Opening, Closing, White Top-Hat, Black Top-Hat.
   - **Attribute** — Area (number of pixels) or Diameter (bounding box diagonal).
   - **Minimum value** — threshold for the attribute.
   - **Connectivity** — 4 or 8.
4. Click **OK**. Structures smaller than the threshold are removed (better edge preservation than morphological filters).

---

## 7. Classic Watershed

**Menu:** Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Classic Watershed

1. Open a grayscale image (ideally the gradient of your image).
2. Plugins ▶ MorphoLibJ ▶ Segmentation ▶ **Classic Watershed**.
3. Dialog:
   - **Input** — select the input grayscale image.
   - **Mask** (optional) — binary mask to restrict the area. Set to "None" for full image.
   - **Use diagonal connectivity** — enables 8-connectivity (2D) or 26-connectivity (3D).
   - **Min h** — minimum grayscale level to start flooding (default: image type minimum).
   - **Max h** — maximum grayscale level to flood up to (default: image type maximum).
4. Click **OK**. Output: labeled image with catchment basins (integer labels 1, 2, …) and watershed lines (value 0).

**⚠ Over-segmentation tip:** Pre-process noisy images with Gaussian Blur (Process ▶ Filters ▶ Gaussian Blur) before running the plugin.

---

## 8. Marker-controlled Watershed

**Menu:** Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Marker-controlled Watershed

Requires at least two open images.

1. Prepare: (a) a gradient image as input, (b) a labeled marker image (each seed = one connected region with a unique integer label).
2. Plugins ▶ MorphoLibJ ▶ Segmentation ▶ **Marker-controlled Watershed**.
3. Dialog:
   - **Input** — gradient image to flood.
   - **Marker** — labeled marker image (usually local minima of the gradient).
   - **Mask** (optional) — binary restriction mask.
   - **Calculate dams** — include watershed lines (0-valued) in output.
   - **Use diagonal connectivity** — enables 8/26-connectivity.
4. Click **OK**. Output: labeled image.

---

## 9. Interactive Marker-controlled Watershed

**Menu:** Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Interactive Marker-controlled Watershed

1. Open a grayscale image.
2. Launch the plugin. The image opens in a custom canvas.
3. Use the **Point selection tool** (or Freehand/Rectangle in ROI Manager) to click seed markers. Hold **SHIFT** to add multiple points across slices.
4. In the **Watershed Segmentation** panel: set connectivity, toggle "Calculate dams", then click **Run** (or **STOP** to abort).
5. In the **Results** panel: choose display format (Overlaid basins, Overlaid dams, Catchment basins, Watershed lines) and click "Show result overlay" or "Create Image".
6. In the **Post-processing** panel: "Merge labels" (select labels with point tool + SHIFT, click button) or "Shuffle colors".

---

## 10. Morphological Segmentation

**Menu:** Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Morphological Segmentation

1. Open a grayscale image (2D or 3D stack).
2. Launch the plugin. Main canvas + left panel appears.
3. **Input Image panel:**
   - **Border Image** — your image already has bright object boundaries (e.g. after gradient).
   - **Object Image** — objects are bright; plugin will compute a gradient internally. Set Gradient type (Morphological recommended) and Gradient radius.
4. **Watershed Segmentation panel:**
   - **Tolerance** — controls splitting. Start with 10 for 8-bit images; ~2000 for 16-bit images. Higher = fewer segments.
   - **Advanced options** — exposes Calculate dams and Connectivity.
   - **Calculate dams** — include watershed lines.
   - **Connectivity** — 4 or 8 (2D); 6 or 26 (3D). Non-diagonal (4/6) = more rounded objects.
   - Click **Run**.
5. **Results panel** (enabled after Run):
   - Display: Overlaid basins | Overlaid dams | Catchment basins | Watershed lines.
   - "Show result overlay" toggles the overlay.
   - "Create Image" saves the current result as a new image window.
6. **Post-processing panel:** Merge labels or Shuffle colors.

---

## 11. Distance Transform Watershed (2D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Distance Transform Watershed

Best for separating touching round objects (nuclei, cells).

1. Provide an 8-bit binary image.
2. Plugins ▶ MorphoLibJ ▶ Binary Images ▶ **Distance Transform Watershed**.
3. Dialog:
   - **Distances** — Chamfer weight set: Borgefors (3,4) recommended for 2D, Chessknight (5,7,11) for better accuracy.
   - **Output Type** — 16 or 32 bits.
   - **Normalize weights** — divides distances by first weight (makes values comparable to Euclidean).
   - **Dynamic** — tolerance for minima in the inverted distance map. Higher = more merges.
   - **Connectivity** — 4 (more rounded) or 8.
   - **Preview** — shows result live.
4. Click **OK**. Output: 32-bit label image (one value per object).

---

## 12. Region Analysis (2D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Analyze ▶ Analyze Regions

1. Active image must be **binary** (single region) or **label image** (multiple regions).
2. Plugins ▶ MorphoLibJ ▶ Analyze ▶ **Analyze Regions**.
3. Check the measurements you want:

| Option | Output column(s) |
|--------|-----------------|
| Area | Area |
| Perimeter | Perimeter (Crofton method) |
| Circularity | Circularity (4π·A/P²) |
| Inertia Ellipse | Ellipse.Center.X/Y, Radius1, Radius2, Orientation |
| Ellipse elongation | Ellipse_Elong |
| Convexity | Convexity |
| Max. Feret Diameter | MaxFeret |
| Oriented Box | OBox.Center.X/Y, Length, Width, Orientation |
| Oriented Box Elongation | OBox_Elong |
| Geodesic Diameter | Geod.Diam, Radius (inscribed circle) |
| Tortuosity | Tortuosity |
| Max inscribed disc | InscrCircle.Center.X/Y, Radius |
| Geodesic Elongation | Geod.Elong |

4. Click **OK**. Results appear in an ImageJ ResultsTable.

**Sub-plugins (Plugins ▶ MorphoLibJ ▶ Analyze):**
- **Bounding Box** — XMin, XMax, YMin, YMax per label.
- **Inertia Ellipse** — ellipse parameters only.
- **Max Feret Diameter** — diameter, orientation, endpoint coordinates.
- **Oriented Box** — oriented bounding box.
- **Geodesic Diameter** — geodesic path length + inscribed circle.
- **Largest Inscribed Circle** — circle center + radius.

---

## 13. Region Analysis 3D

**Menu:** Plugins ▶ MorphoLibJ ▶ Analyze ▶ Analyze Regions 3D

Similar to 2D. Measures: Volume, Surface Area, Mean Breadth, Euler Number (3D), Inertia Ellipsoid (center, 3 radii, 3 angles φ/θ/ψ), elongation factors.

---

## 14. Intensity Measurements 2D/3D

**Menu:** Plugins ▶ MorphoLibJ ▶ Analyze ▶ Intensity Measurements 2D/3D

Requires one grayscale image and one label image (same dimensions).
Computes: Mean, Std Dev, Max, Min, Median, Mode, Skewness, Kurtosis per label region, plus the same statistics for neighboring (adjacent) regions.

---

## 15. Label Overlap Measures

**Menu:** Plugins ▶ MorphoLibJ ▶ Analyze ▶ Label Overlap Measures

Compares two label images (source S, target T). Outputs: Target Overlap, Total Overlap, Jaccard Index (Union Overlap), Dice Coefficient (Mean Overlap), Volume Similarity, False Negative Error, False Positive Error — both per-label and globally.

---

## 16. Connected Components Labeling

**Menu:** Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Connected Components Labeling

1. Open a binary image.
2. Dialog: **Connectivity** (4 or 8 for 2D; 6 or 26 for 3D), **Output type** (8, 16, or 32-bit).
3. Output: label image where each connected component has a unique integer.

---

## 17. Chamfer Distance Map

**Menu:** Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Chamfer Distance Map

1. Open a binary or label image.
2. Select: Chamfer weights, Output type (16 or 32 bits), Normalize checkbox.
3. Output: distance map (each foreground pixel = distance to nearest background or differently-labeled pixel).

---

## 18. Label Utilities

**Menu:** Plugins ▶ MorphoLibJ ▶ Labels

| Plugin | Action |
|--------|--------|
| Set Label Map | Change the color LUT for display; shuffle colors |
| Label To RGB | Convert label image to true color RGB |
| Assign Measure To Label | Map a ResultsTable column back onto the label image as pixel values |
| Label Boundaries | Create binary image marking pixels adjacent to differently-labeled pixels |
| Remove Border Labels | Remove labels touching the image border |
| Replace / Remove Label(s) | Set chosen label values to 0 or another label |
| Select Label(s) | Keep only specified labels; all others become 0 |
| Crop Label | Extract a single label into a new cropped binary image |
| Label Size Opening | Remove labels with area/volume below threshold |
| Remap Labels | Renumber labels 1…N to remove gaps after deletion |
| Label Edition | Interactive GUI: merge, erode, dilate, remove, size-filter labels |

---

## 19. Label Edition Plugin

**Menu:** Plugins ▶ MorphoLibJ ▶ Labels ▶ Label Edition

Interactive GUI for post-processing label images. Operations: Merge (point tool + SHIFT to select), Dilate, Erode, Open, Close, Remove selected, Remove largest, Remove in border, Size opening, Reset, Done. All operations are in-place (original modified directly; Reset restores initial state).

---

## 20. Sample End-to-End UI Workflow — Segment & Measure Touching Objects

This walkthrough takes a fluorescence or brightfield image containing touching objects (e.g. cell nuclei, blobs) and produces a labelled segmentation plus a measurements table — entirely through the Fiji GUI, no scripting required.

**You will use:** Morphological Filters → Extended Min & Max → Connected Components Labeling → Marker-controlled Watershed → Remove Border Labels → Label Size Opening → Remap Labels → Labels to RGB → Analyze Regions

---

### Step 1 — Open and prepare your image

1. **File ▶ Open…** — open your 8-bit or 16-bit grayscale image.
2. *(If your image is RGB)* **Image ▶ Type ▶ 8-bit** to convert to grayscale.
3. *(Optional)* **Image ▶ Duplicate…** (`Shift+D`) — work on a copy to preserve the original. Name it `input`.

> 💡 **Sample image to try:** File ▶ Open Samples ▶ **Blobs (25K)** — a built-in Fiji image ideal for testing.

---

### Step 2 — Compute a morphological gradient (boundary image)

The gradient highlights object edges and forms the landscape the watershed will flood.

1. Make sure `input` (or your image) is the active window.
2. **Plugins ▶ MorphoLibJ ▶ Filtering ▶ Morphological Filters**
3. Set:
   - **Operation:** `Gradient`
   - **Element:** `Disk`
   - **Radius:** `2` *(increase to 3–4 for larger objects)*
4. Click **OK** → a new image `input-Gradient` appears.

---

### Step 3 — Find extended minima (watershed seeds)

The minima of the gradient image mark the interior of each object and will become the seeds for the watershed.

1. Make `input-Gradient` the active window.
2. **Plugins ▶ MorphoLibJ ▶ Minima and Maxima ▶ Extended Min & Max**
3. Set:
   - **Operation:** `Extended Minima`
   - **Dynamic:** `10` *(tolerance — increase if you get too many seeds; decrease if objects are missed. Scale to ~2000 for 16-bit images)*
   - **Connectivity:** `4`
4. Click **OK** → a new binary image `input-Gradient-Extended-Min` appears (white dots = seeds).

> 💡 **Check:** You should see one bright cluster of pixels roughly centred inside each object. If you see hundreds of tiny dots, raise **Dynamic**; if some objects have no dot, lower it.

---

### Step 4 — Label the seeds (connected components)

Watershed needs each seed to carry a unique integer label.

1. Make `input-Gradient-Extended-Min` active.
2. **Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Connected Components Labeling**
3. Set:
   - **Connectivity:** `4`
   - **Output type:** `16 bits` *(supports up to 65 535 objects)*
4. Click **OK** → `input-Gradient-Extended-Min-lbl` appears (each seed region has a unique integer).

---

### Step 5 — Run marker-controlled watershed

Flood the gradient image upward from each labelled seed.

1. **Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Marker-controlled Watershed**
2. Set:
   - **Input:** `input-Gradient` *(the landscape to flood)*
   - **Marker:** `input-Gradient-Extended-Min-lbl` *(the seeds)*
   - **Mask:** `None`
   - ☑ **Calculate dams** *(adds 0-pixel watershed lines between objects)*
   - **Use diagonal connectivity:** unchecked *(4-connectivity — produces rounder objects)*
3. Click **OK** → a label image `input-Gradient-Extended-Min-lbl-watershed` appears.

> 💡 **Rename it** for clarity: double-click its title bar → type `labels`.

---

### Step 6 — Post-process the label image

Remove incomplete objects at the border and discard debris.

1. Make `labels` active.
2. **Plugins ▶ MorphoLibJ ▶ Labels ▶ Remove Border Labels** — removes any object touching the image edge.
3. **Plugins ▶ MorphoLibJ ▶ Labels ▶ Label Size Opening**
   - **Min:** `50` *(remove objects smaller than 50 px² — adjust to your scale)*
   - Click **OK**.
4. **Plugins ▶ MorphoLibJ ▶ Labels ▶ Remap Labels** — renumbers labels 1…N to close any gaps after removal.

---

### Step 7 — Create a colour overlay for visual inspection

1. Make `labels` active.
2. **Plugins ▶ MorphoLibJ ▶ Labels ▶ Labels to RGB**
   - **Colormap:** `Golden angle`
   - **Background:** `Black`
   - ☑ **Shuffle** *(randomises colours so adjacent objects differ)*
   - Click **OK** → an RGB overlay image appears.
3. *(Optional)* Use **Image ▶ Overlay ▶ Add Image…** to overlay it on the original for side-by-side comparison.

---

### Step 8 — Measure region properties

1. Make `labels` active (the integer-label image, not the RGB one).
2. **Plugins ▶ MorphoLibJ ▶ Analyze ▶ Analyze Regions**
3. Tick the measurements you need (suggested starter set):
   - ☑ Area
   - ☑ Perimeter
   - ☑ Circularity
   - ☑ Inertia Ellipse
   - ☑ Convexity
   - ☑ Geodesic Diameter
4. Click **OK** → a **ResultsTable** opens with one row per object.

---

### Step 9 — Save results

| What to save | How |
|---|---|
| Measurements table | In the ResultsTable window → **File ▶ Save As…** → save as `.csv` |
| Label image (TIFF) | Make `labels` active → **File ▶ Save As ▶ Tiff…** |
| RGB overlay (PNG) | Make the RGB image active → **File ▶ Save As ▶ PNG…** |

---

### Workflow summary diagram

```
Original image
      │
      ▼
[Morphological Filters — Gradient, Disk r=2]
      │  gradient image
      ▼
[Extended Min & Max — Extended Minima, dynamic=10]
      │  binary minima image
      ▼
[Connected Components Labeling — 16-bit]
      │  integer seed labels
      ▼
[Marker-controlled Watershed — with dams]
      │  raw label image
      ▼
[Remove Border Labels]  →  [Label Size Opening min=50]  →  [Remap Labels]
      │  clean label image
      ├──▶  [Labels to RGB]          → visual overlay
      └──▶  [Analyze Regions]        → ResultsTable (.csv)
```

---

### Troubleshooting quick reference

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Too many small segments | Dynamic too low | Raise Extended Minima **Dynamic** (Step 3) |
| Adjacent objects merged into one | Dynamic too high | Lower **Dynamic** |
| Objects split into halves | Gradient radius too large | Reduce **Radius** in Step 2 |
| Edge objects not removed | Label values are short integers but border removal needs reset | Re-run **Remap Labels** before **Remove Border Labels** |
| Empty ResultsTable | RGB image was active instead of label image | Make the integer-label image active before Analyze Regions |
| Watershed lines (0-valued pixels) included in measurements | Dams included and not masked | Uncheck **Calculate dams**, or post-process with threshold |
