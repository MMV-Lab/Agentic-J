# MorphoLibJ — UI GUIDE  (v1.6.5)

All plugins live under **Plugins ▸ MorphoLibJ ▸ …**. The sub-menus below match the installed
1.6.5 menu exactly (from the plugin's `plugins.config`).

> 💡 **Find exact macro strings:** open **Plugins ▸ Macros ▸ Record…** before using a dialog;
> every choice you make is printed as a reproducible `run("…","…")` call. (When scripting,
> always keep the full option string — an empty one makes the dialog re-open and block.)

```
Plugins ▸ MorphoLibJ ▸
  ├─ Filtering        (morphological & directional filters, reconstruction, holes, borders)
  ├─ Minima and Maxima
  ├─ Segmentation     (Classic / Marker-controlled / Morphological / Distance-Transform watershed*)
  ├─ Binary Images    (labeling, distance maps, distance-transform watershed, size opening)
  ├─ Label Images     (colour, cleanup, editing, conversion)
  ├─ Analyze          (region & intensity measurements, overlap)
  └─ Utilities        (extend borders, binarize, overlays, draw table values)
* Distance Transform Watershed lives under Binary Images.
```

---

## Filtering

### Morphological Filters (2D) / (3D)
Plugins ▸ MorphoLibJ ▸ Filtering ▸ **Morphological Filters** *(or "(3D)")*.
- **Operation:** Erosion · Dilation · Opening · Closing · White Top Hat · Black Top Hat ·
  Gradient · Laplacian · Internal Gradient · External Gradient.
- **Element:** Disk · Square · Diamond · Octagon · Horizontal Line · Vertical Line ·
  Line 45 degrees · Line 135 degrees  *(3D adds Ball, Cube, Z-Line)*.
- **Radius (in pixels):** integer ≥ 1.  ☑ **Show Element** optional. Click **OK** → new image.

| Operation | Effect |
|-----------|--------|
| Erosion / Dilation | shrink / grow bright objects |
| Opening / Closing | remove small bright / fill small dark structures |
| White / Black Top Hat | highlight small bright / small dark structures |
| Gradient | object outlines (Dilation − Erosion) |

### Binary Morphological Filters (2D / 3D) *(1.6.5)*
Distance-transform-based erosion/dilation/opening/closing for binary masks — faster than
the grayscale filters on binary input. Parameters: **Operation**, **Radius**.

### Directional Filtering
For thin curvilinear structures. **Type** Max/Min · **Operation** Opening/Closing/Erosion/
Dilation/Median · **Line Length** (px) · **Direction Number** (e.g. 32).

### Morphological Reconstruction (2D / 3D)
Two open images: **Marker**, **Mask**, **Type** (By Dilation / By Erosion), **Connectivity**.
- **Kill Borders** — removes objects touching the border (binary or grayscale).
- **Fill Holes (Binary/Gray)** — fills enclosed holes / dark regions.

### Gray Scale Attribute Filtering (2D / 3D)
Remove components by size attribute (better edge preservation than opening).
**Operation** Opening/Closing/White Top Hat/Black Top Hat · **Attribute** Area / Box Diagonal
(3D: Volume) · **Minimum Value** · **Connectivity**.

---

## Minima and Maxima
**Regional Min & Max** — Operation (Regional Maxima / Regional Minima), Connectivity.
Output: binary (255 at extrema).
**Extended Min & Max** — Operation (Extended Maxima / Minima), **Dynamic** (tolerance;
higher = fewer, larger extrema), Connectivity. Less noise-sensitive — preferred for real data.
**Impose Min & Max** — force a marker image's extrema onto another image. 3D variants exist.

---

## Segmentation

### Classic Watershed
Floods a grayscale image (best on a gradient) from all minima. **Input**, **Mask** (or None),
☑ **Use diagonal connectivity**, **Min h**, **Max h**. Output: labelled basins + 0-valued dams.
Pre-blur noisy images or use Marker-controlled Watershed to avoid over-segmentation.

### Marker-controlled Watershed
Floods from labelled seeds — avoids over-segmentation. **Input** (gradient or inverted
distance map), **Marker** (label seeds), **Mask** (or None), **Compactness** (0 = standard;
>0 = compact watershed), ☑ **Binary markers**, ☑ **Calculate dams**, ☑ **Use diagonal
connectivity**. Output: label image.

### Morphological Segmentation *(interactive GUI)*
A panel wrapping gradient + watershed with a **Tolerance** slider (~10 for 8-bit, ~2000 for
16-bit) and a **Compactness** option. Choose Object vs Border input, Run, pick a display
format (Overlaid basins / Overlaid dams / Catchment basins / Watershed lines), Create Image.
*Not for headless scripts — it opens a persistent window.*

### Interactive Marker-controlled Watershed *(interactive)*
Place seeds with the point tool, set connectivity/dams, Run, Create Image. Cannot be
fully automated.

---

## Binary Images
- **Connected Components Labeling** — Connectivity (4/8, 3D 6/26), **Type of result**
  (8 bits / 16 bits / **float**). Each region → unique integer.
- **Euclidean Distance Map** *(1.6.5)* / **Chamfer Distance Map** / **… 3D** — assign each
  foreground pixel its distance to background. Chamfer: **Distances** (Chessboard, City-Block,
  Quasi-Euclidean, Borgefors (3,4), Chessknight (5,7,11), Verwer), **Output** (16/32 bits),
  ☑ **Normalize weights**. Input must be 8-bit binary.
- **Geodesic Distance Map** / Interactive / 3D — distance within a mask from a marker.
- **Distance Transform Watershed** / **… 3D** — one-step split of touching objects:
  **Distances**, **Output**, ☑ **Normalize**, **Dynamic**, **Connectivity**. 8-bit binary in.
- **Convexify**, **Keep/Remove Largest Region**, **Area Opening**, **Size Opening 2D/3D**.

---

## Label Images
| Plugin | Action |
|--------|--------|
| Set Label Map | change display LUT (Colormap: Glasbey, Golden angle, Fire…; Background; ☑ Shuffle) |
| Labels To RGB | render labels to an RGB image (Colormap, Background, ☑ Shuffle) |
| Draw Labels As Overlay / Assign Measure to Label | overlay labels / paint a table column onto labels |
| Remove Border Labels | remove labels touching selected borders (Left/Right/Top/Bottom, 3D Front/Back) |
| **Label Size Filtering** | keep/remove labels by size (**Operation** Greater_Than/Lower_Than/…, **Size Limit**) |
| Remap Labels | renumber 1…N (no dialog) |
| Keep / Remove Largest Label · Replace/Remove · Merge · Select · Crop Label | per-label edits |
| Expand Labels · Fill Label Holes · Skeletonize Labels · Region Influence Zones | label transforms |
| Label Boundaries · Region Boundaries Labeling · **Label Map to ROIs** · Region Adjacency Graph | conversions / topology |
| **Label Edition** *(interactive)* | merge/erode/remove labels by mouse — not scriptable |

---

## Analyze
- **Analyze Regions (2D)** / **(3D)** — tick the shape features (Area, Perimeter, Circularity,
  Euler Number, Bounding Box, Centroid, **Equivalent Ellipse**, Ellipse Elong., Convexity,
  Max. Feret Diameter, Oriented Box, Geodesic Diameter, Tortuosity, Max. Inscribed Disc,
  Geodesic Elong., **Average Thickness**). Results go to a `<image>-Morphometry` table.
- Individual descriptors as their own commands: Bounding Box, Equivalent Ellipse, Max. Feret
  Diameters, Oriented Bounding Box, Max. Inscribed Circle, Geodesic Diameter, Average Thickness.
- **Intensity Measurements 2D/3D** — Input (grayscale) + Labels; Mean/StdDev/Max/Min/Median/
  Mode/Skewness/Kurtosis/Center of mass.
- **Label Overlap Measures** — Source (result) + Target (ground truth); ☑ Overlap ☑ Jaccard
  index ☑ Dice coefficient ☑ Volume Similarity ☑ False Negative/Positive Error. 1.0 = perfect.
- **Microstructure Analysis / 3D** — area/perimeter densities, etc.

---

## Utilities
**Extend Image Borders**, **Binarize Image** *(1.6.5; foreground = any non-zero pixel)*,
**Binary Overlay**, **Binary/Labels Overlay**, **Draw Table Values**.

---

## Scripting note
Every command above is callable as `IJ.run(imp, "<exact command text>", "<options>")`.
See `GROOVY_API.md` for verified option strings, and `GROOVY_WORKFLOW_CELL_SEGMENTATION.groovy`
for a tested, popup-free pipeline.
