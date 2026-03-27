# MorphoLibJ — UI GUIDE

All MorphoLibJ plugins are accessible via **Plugins ▶ MorphoLibJ** in the Fiji menu bar.

> ⚠ **Macro recording:** For exact parameter strings, use **Plugins ▶ Macros ▶ Record…**
> before opening any dialog. Every parameter you set in the GUI is recorded as a
> macro-reproducible command string.

---

## 1. Morphological Filters (2D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Morphological Filters

Works on 2D 8-bit, 16-bit, or 32-bit grayscale images and on RGB (filters only).

1. Open a grayscale image.
2. Go to Plugins ▶ MorphoLibJ ▶ Filtering ▶ **Morphological Filters**.
3. Set the parameters:
   - **Operation** — the morphological operation (see table below).
   - **Element** — shape of the structuring element: `Disk` `Square` `Octagon` `Diamond` `Line`
   - **Radius** — half-size of the structuring element in pixels (integer ≥ 1).
   - **Preview** checkbox — live preview on the image.
4. Click **OK**. A new image is created.

| Operation | Effect |
|-----------|--------|
| Erosion | Replaces each pixel with the neighbourhood minimum; shrinks bright objects |
| Dilation | Replaces each pixel with the neighbourhood maximum; expands bright objects |
| Opening | Erosion then dilation — removes bright structures smaller than the structuring element |
| Closing | Dilation then erosion — fills dark holes smaller than the structuring element |
| White Top Hat | Original minus Opening — highlights small bright structures |
| Black Top Hat | Closing minus Original — highlights small dark structures |
| Gradient | Dilation minus Erosion — outlines object edges |
| Laplacian | Average of Dilation and Erosion, minus original — enhances edges in both directions |

---

## 2. Morphological Filters (3D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Morphological Filters (3D)

Same operations as 2D. Works on 3D image stacks.
Additional structuring element options: **Ball** (sphere) and **Cube**.
Size can be set independently for X, Y, Z axes.

---

## 3. Directional Filtering

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Directional Filtering

Use for images containing thin curvilinear structures (blood vessels, fibres, cell walls).
Applies a morphological operation at many orientations, then combines the results.

1. Open a 2D grayscale image.
2. Plugins ▶ MorphoLibJ ▶ Filtering ▶ **Directional Filtering**.
3. Parameters:
   - **Type** — how to combine oriented results: `Max` (enhances bright structures) or `Min` (enhances dark structures).
   - **Operation** — filter at each orientation: `Opening` `Closing` `Erosion` `Dilation` `Median`
   - **Line Length** — approximate length of the linear structuring element in pixels.
   - **Direction Number** — number of orientations to sample (e.g. `32`). Increase if Line Length is large.
4. Click **OK**.

---

## 4. Morphological Reconstruction

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Morphological Reconstruction

Requires two open images of the same dimensions: a **marker** and a **mask**.

1. Plugins ▶ MorphoLibJ ▶ Filtering ▶ **Morphological Reconstruction**.
2. Select:
   - **Marker image** — starting point for the reconstruction.
   - **Mask image** — constrains the reconstruction.
   - **Type** — `By Dilation` or `By Erosion`.
   - **Connectivity** — `4` or `8` (2D); `6` or `26` (3D).
3. Click **OK**.

**Single-image convenience variants:**
- **Kill Borders** (Plugins ▶ MorphoLibJ ▶ Filtering ▶ Kill Borders) — removes objects or regions touching the image border. Works on binary and grayscale.
- **Fill Holes** (Plugins ▶ MorphoLibJ ▶ Filtering ▶ Fill Holes (Binary/Gray)) — fills enclosed holes in binary objects; fills dark enclosed regions in grayscale images.

---

## 5. Grayscale Attribute Filtering

**Menu:** Plugins ▶ MorphoLibJ ▶ Filtering ▶ Grayscale Attribute Filtering

Removes image components based on a size or diameter attribute. Preserves edges better than morphological filters.

1. Open a grayscale image.
2. Plugins ▶ MorphoLibJ ▶ Filtering ▶ **Grayscale Attribute Filtering**.
3. Parameters:
   - **Operation** — `Opening` `Closing` `White Top Hat` `Black Top Hat`
   - **Attribute** — `Area` (number of pixels) or `Diameter` (bounding box diagonal).
   - **Minimum value** — threshold; components smaller than this are removed.
   - **Connectivity** — `4` or `8`.
4. Click **OK**.

---

## 6. Minima and Maxima

**Menu:** Plugins ▶ MorphoLibJ ▶ Minima and Maxima

| Plugin | Purpose |
|--------|---------|
| Regional Min & Max | Finds exact regional minima or maxima (plateaus not dominated by neighbours) |
| Extended Min & Max | Finds extrema within a tolerance (less noise-sensitive) |
| Impose Min & Max | Forces a binary image to define regional minima/maxima in another image |
| 3D variants | Same operations for 3D stacks |

**Regional Min & Max dialog:**
- **Operation** — `Regional Maxima` or `Regional Minima`
- **Connectivity** — `4` or `8`

Output: binary image (255 at extrema, 0 elsewhere).

**Extended Min & Max dialog:**
- **Operation** — `Extended Maxima` or `Extended Minima`
- **Dynamic** — tolerance (integer). Higher = fewer, larger extrema. Scale to image bit-depth: ~10 for 8-bit, ~2000 for 16-bit.
- **Connectivity** — `4` or `8`

---

## 7. Classic Watershed

**Menu:** Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Classic Watershed

Segments a grayscale image by simulating flooding from all local minima simultaneously.
Best used on a gradient image or an image with clear intensity valleys at boundaries.

1. Open a grayscale image (morphological gradient recommended).
2. Plugins ▶ MorphoLibJ ▶ Segmentation ▶ **Classic Watershed**.
3. Parameters:
   - **Input** — grayscale image to flood.
   - **Mask** — optional binary mask to restrict flooding. Set to `None` for full image.
   - **Use diagonal connectivity** — enables 8-connectivity (2D) or 26-connectivity (3D).
   - **Min h** — minimum intensity level to start flooding (usually image minimum).
   - **Max h** — maximum level to flood up to (usually image maximum).
4. Click **OK**. Output: labeled image with catchment basins (integer labels 1, 2, …) and watershed lines (value 0).

> ⚠ **Over-segmentation:** Noisy images will produce many small segments. Pre-process with
> **Process ▶ Filters ▶ Gaussian Blur** before running, or use Marker-controlled Watershed instead.

---

## 8. Marker-controlled Watershed

**Menu:** Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Marker-controlled Watershed

Floods a grayscale landscape from pre-defined labeled seeds. Avoids over-segmentation by controlling where floods can start.

Requires at least two open images:

1. **Prepare:**
   - A grayscale **input** image (e.g. a gradient image or inverted distance map).
   - A **marker** label image (each seed region = one connected component with a unique integer label).
   - Optionally, a **binary mask** to restrict flooding to the foreground.
2. Plugins ▶ MorphoLibJ ▶ Segmentation ▶ **Marker-controlled Watershed**.
3. Parameters:
   - **Input** — grayscale landscape image to flood.
   - **Marker** — labeled seed image (one integer per object).
   - **Mask** — binary mask, or `None` for full image.
   - **Calculate dams** — include watershed lines (0-valued boundary pixels) in output.
   - **Use diagonal connectivity** — enables 8/26-connectivity.
4. Click **OK**. Output: labeled image (one integer per segmented region).

---

## 9. Interactive Marker-controlled Watershed

**Menu:** Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Interactive Marker-controlled Watershed

Allows you to place watershed seeds interactively with the mouse.

1. Open a grayscale image and launch the plugin.
2. Use the **Point selection tool** (or Freehand ROI) to click seed positions. Hold **SHIFT** to add multiple points.
3. In the **Watershed Segmentation** panel: set connectivity, toggle dams, click **Run**.
4. In the **Results** panel: choose display format and click **Create Image** to export the result.
5. In the **Post-processing** panel: **Merge labels** (select labels with SHIFT+click, then click Merge) or **Shuffle colors**.

> This plugin cannot be fully automated from a macro because it requires interactive mouse input.

---

## 10. Morphological Segmentation

**Menu:** Plugins ▶ MorphoLibJ ▶ Segmentation ▶ Morphological Segmentation

An interactive GUI that wraps gradient computation + watershed. Good starting point
when you want a quick result with an adjustable tolerance slider.

1. Open a grayscale image and launch the plugin.
2. **Input Image panel:**
   - **Object Image** — objects are bright; plugin computes the gradient internally. Set **Gradient radius**.
   - **Border Image** — your image already shows bright boundaries; gradient is not computed.
3. **Watershed Segmentation panel:**
   - **Tolerance** — controls splitting sensitivity. Start at `10` for 8-bit images; ~`2000` for 16-bit. Higher = fewer segments.
   - Expand **Advanced options** to see **Calculate dams** and **Connectivity**.
   - Click **Run**.
4. **Results panel** (enabled after Run):
   - Display: `Overlaid basins` `Overlaid dams` `Catchment basins` `Watershed lines`
   - Click **Create Image** to generate a new image window with the selected result.
5. **Post-processing panel:** Merge labels or Shuffle colors.

> ⚠ **Macro scripting:** This plugin requires `IJ.wait(1000)` after launching before
> calling any `IJ.call()` commands. See GROOVY_API.md §D3.

---

## 11. Distance Transform Watershed (2D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Distance Transform Watershed

Combines distance transform + watershed in a single step. Best for separating
touching round objects (nuclei, cells, particles). **Requires an 8-bit binary input.**

1. Provide an 8-bit binary image (values 0 and 255 only).
2. Plugins ▶ MorphoLibJ ▶ Binary Images ▶ **Distance Transform Watershed**.
3. Parameters:
   - **Distances** — Chamfer weight set. `Borgefors (3,4)` is a good standard choice; `Chessknight (5,7,11)` is more accurate.
   - **Output type** — `16 bits` or `32 bits` (use 32 bits if you expect > 65 535 objects).
   - **Normalize weights** — scales distances to approximate Euclidean pixel distances.
   - **Dynamic** — tolerance for seed detection. Higher = more merges (fewer, larger segments). Start at `1.00` for 8-bit images.
   - **Connectivity** — `4` (more rounded objects) or `8`.
4. Click **OK**. Output: labeled image (one integer per object).

> 💡 For finer control over the individual steps (threshold → distance map → maxima → watershed),
> use the four-step pipeline described in **UI_WORKFLOW_CELL_SEGMENTATION.md**.

---

## 12. Connected Components Labeling

**Menu:** Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Connected Components Labeling

Assigns a unique integer to each connected foreground region in a binary image.

1. Open a binary image.
2. Plugins ▶ MorphoLibJ ▶ Binary Images ▶ **Connected Components Labeling**.
3. Parameters:
   - **Connectivity** — `4` or `8` (2D); `6` or `26` (3D).
   - **Output type** — `8 bits` (max 255 labels), `16 bits` (max 65 535), `32 bits` (max ~16 million).
4. Click **OK**. Output: label image where each connected region has a unique integer.

---

## 13. Chamfer Distance Map

**Menu:** Plugins ▶ MorphoLibJ ▶ Binary Images ▶ Chamfer Distance Map

Assigns to each foreground pixel its shortest distance to the nearest background pixel,
using a Chamfer approximation of Euclidean distance.

**Input:** binary image (8-bit, values 0/255).

1. Plugins ▶ MorphoLibJ ▶ Binary Images ▶ **Chamfer Distance Map**.
2. Parameters:
   - **Distances** — weight set:

   | Option | Accuracy |
   |--------|---------|
   | Chessboard (1,1) | Low |
   | City-Block (1,2) | Low |
   | Borgefors (3,4) | Good |
   | Chessknight (5,7,11) | Better |

   - **Output type** — `16 bits` or `32 bits`.
   - **Normalize weights** — recommended; produces pixel-unit distances.
3. Click **OK**. Output: float distance image.

---

## 14. Region Analysis (2D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Analyze ▶ Analyze Regions

Measures shape properties of all labeled regions in a label image.
Active image must be a **binary** or **label (integer)** image.

1. Make the label image active.
2. Plugins ▶ MorphoLibJ ▶ Analyze ▶ **Analyze Regions**.
3. Tick the measurements you want:

| Option | Output columns |
|--------|----------------|
| Area | Area |
| Perimeter | Perimeter (Crofton formula) |
| Circularity | Circularity (4π·Area/Perimeter²) |
| Inertia Ellipse | Ellipse.Center.X/Y, Radius1, Radius2, Orientation |
| Ellipse elongation | Ellipse.Elong |
| Convexity | Convexity |
| Max. Feret Diameter | MaxFeret |
| Oriented Box | OBox.Center.X/Y, Length, Width, Orientation |
| Oriented Box Elongation | OBox.Elong |
| Geodesic Diameter | Geod.Diam |
| Tortuosity | Tortuosity |
| Max inscribed disc | InscrCircle.Center.X/Y, Radius |
| Geodesic Elongation | Geod.Elong |

4. Click **OK**. Results appear in an ImageJ ResultsTable.

---

## 15. Region Analysis (3D)

**Menu:** Plugins ▶ MorphoLibJ ▶ Analyze ▶ Analyze Regions 3D

Same principle as 2D; works on 3D label stacks. Measures:
Volume, Surface Area, Mean Breadth, Euler Number, Inertia Ellipsoid
(centre, 3 semi-axis radii, 3 orientation angles), elongation factors.

---

## 16. Intensity Measurements 2D/3D

**Menu:** Plugins ▶ MorphoLibJ ▶ Analyze ▶ Intensity Measurements 2D/3D

Requires one grayscale image and one label image of the same dimensions.
Computes per-label statistics: Mean, Std Dev, Max, Min, Median, Mode, Skewness, Kurtosis.

1. Plugins ▶ MorphoLibJ ▶ Analyze ▶ **Intensity Measurements 2D/3D**.
2. Select:
   - **Input** — grayscale intensity image.
   - **Labels** — label image with object regions.
   - Tick the statistics you need.
3. Click **OK**.

---

## 17. Label Overlap Measures

**Menu:** Plugins ▶ MorphoLibJ ▶ Analyze ▶ Label Overlap Measures

Compares two label images to quantify segmentation accuracy.
Use **source = your result**, **target = ground truth**.

1. Plugins ▶ MorphoLibJ ▶ Analyze ▶ **Label Overlap Measures**.
2. Select:
   - **Source image** — your segmentation result.
   - **Target image** — the reference / ground-truth label image.
   - ☑ Overlap ☑ Jaccard ☑ Dice
3. Click **OK**. Output: ResultsTable with per-label and global metrics.

| Metric | Meaning | Best value |
|--------|---------|-----------|
| Jaccard Index | Intersection / Union | 1.0 |
| Dice Coefficient | 2×Intersection / (A+B) | 1.0 |
| Total Overlap | Correctly identified labels | 1.0 |
| False Negative Error | Missed GT labels | 0.0 |
| False Positive Error | Extra labels not in GT | 0.0 |

---

## 18. Label Utilities

**Menu:** Plugins ▶ MorphoLibJ ▶ Label Images

| Plugin | Action |
|--------|--------|
| Set Label Map | Change the colour LUT for display; shuffle colours |
| Assign Measure to Label | Map a ResultsTable column onto the label image as pixel values |
| Label Boundaries | Create binary image marking pixels between differently-labelled regions |
| Remove Border Labels | Remove labels that touch the image border |
| Replace / Remove Label(s) | Set a label value to 0 (delete) or to another value (merge) |
| Select Label(s) | Keep only the specified labels; all others become 0 |
| Crop Label | Extract a single label into a new cropped binary image |
| Label Size Opening | Remove labels with area below a threshold |
| Remap Labels | Renumber labels 1…N to remove gaps after deletion |
| Keep Largest Label | Keep only the label with the largest area |
| Remove Largest Label | Remove the label with the largest area |

---

## 19. Label Edition (Interactive)

**Menu:** Plugins ▶ MorphoLibJ ▶ Label Images ▶ Label Edition

Interactive GUI for post-processing label images.

- **Merge** — select two or more labels with the Point tool (hold SHIFT for multiple), then click Merge.
- **Dilate / Erode / Open / Close** — morphological operations applied to all labels in-place.
- **Remove selected** — select a label with Point tool, click Remove selected.
- **Remove in border** — removes all labels touching the image edge.
- **Size opening** — set a minimum area; labels below it are removed.
- **Reset** — restores the image to the state when Label Edition was launched.
- **Done** — confirms all changes and closes the plugin.

> All operations modify the label image in-place. The original is preserved only until
> you click **Done** or close the plugin without resetting.
