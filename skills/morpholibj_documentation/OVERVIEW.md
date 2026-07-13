# MorphoLibJ — OVERVIEW  (installed version: **1.6.5**)

## What It Is
MorphoLibJ is a comprehensive Fiji/ImageJ library of **mathematical morphology** operators
that are absent from core ImageJ. It is developed by David Legland and Ignacio
Arganda-Carreras at the INRAE–IJPB lab (Java package root `inra.ijpb`), is GPL-licensed,
and is distributed through the **IJPB-plugins** Fiji update site. It operates on binary,
grayscale, and label images in both 2D and 3D.

Functional domains:
- **Morphological filtering** — erosion, dilation, opening, closing, white/black top-hats,
  morphological gradient and Laplacian, internal/external gradients, directional filtering,
  and (new in 1.6.5) binary morphological filters based on the Euclidean distance transform.
- **Morphological & geodesic reconstruction** — hole filling, border killing, geodesic
  reconstruction by dilation/erosion, grayscale attribute filtering, regional/extended minima
  and maxima.
- **Watershed segmentation** — Classic Watershed, Marker-controlled Watershed,
  Distance Transform Watershed (2D/3D), and the interactive Morphological Segmentation GUI.
- **Binary & label utilities** — connected-components labelling, Euclidean/Chamfer/geodesic
  distance maps, size/area opening, keep/remove largest region, label editing, merging,
  expansion, ROI conversion.
- **Quantitative region analysis (2D & 3D)** — area/volume, perimeter/surface area (Crofton),
  Euler number, circularity/sphericity, equivalent ellipse/ellipsoid, geodesic diameter,
  largest inscribed disc/ball, intensity statistics per label, label-overlap (Jaccard/Dice).

---

## Typical Inputs and Use Cases

### Fluorescence microscopy — nucleus / cell segmentation
- **Input:** 8/16-bit grayscale, bright nuclei on dark background.
- **Pipeline:** Threshold → Chamfer Distance Map → Extended Maxima → Connected Components
  → Marker-controlled Watershed → Remove Border Labels → Size Opening → Analyze Regions.
- **Goal:** separate touching nuclei, count, measure size/shape. See the workflow script.

### Materials / particle analysis
- **Input:** 8/16-bit SEM/TEM of touching particles or grains.
- **Pipeline:** Threshold → **Distance Transform Watershed** → Label Size Filtering → Analyze Regions.
- **Goal:** split touching particles; size distribution, circularity, Feret diameter.

### Brightfield colony / tissue analysis
- **Input:** 8-bit grayscale.
- **Pipeline:** Morphological Filters (Gradient) → Extended Minima → Marker-controlled Watershed.

### 3D confocal stacks
- **Input:** 16-bit 3D stack.
- **Pipeline:** Morphological Filters (3D) → Extended Min & Max 3D → Distance Transform
  Watershed 3D → Analyze Regions 3D (volume, surface area, equivalent ellipsoid).

### Thin curvilinear structures (vessels, fibres, walls)
- Directional Filtering → Threshold → Connected Components → Geodesic Diameter.

### Segmentation validation
- Two label images → **Label Overlap Measures** → Jaccard, Dice, volume similarity.

---

## Input requirements by task
| Task | Required input |
|------|----------------|
| Morphological filters | 8/16/32-bit gray or RGB (RGB filters only) |
| Chamfer / Euclidean distance map, Distance Transform Watershed | **8-bit binary, values 0/255** |
| Connected Components Labeling | binary image |
| Marker-controlled Watershed | grayscale landscape + label markers (+ optional binary mask) |
| Analyze Regions (2D/3D) | label image (integer) |
| Intensity Measurements | grayscale image + label image, same size |
| Label Overlap Measures | two label images, same size |

## Typical outputs
| Output | Produced by |
|--------|-------------|
| Filtered grayscale | Morphological / Directional Filters |
| Binary image | Reconstruction, Fill Holes, Kill Borders, Regional Min & Max |
| Label image (integer) | Connected Components, watershed variants |
| 16/32-bit distance map | Chamfer / Euclidean / Geodesic Distance Map |
| ResultsTable | Analyze Regions, Intensity Measurements, Label Overlap |
| RGB image | Labels To RGB |

---

## Automation Level
**Fully scriptable** via `IJ.run()` macro commands or the `inra.ijpb.*` Java/Groovy API.
- All non-interactive plugins record in the macro recorder (**Plugins ▸ Macros ▸ Record…**)
  and run unattended — *provided you give complete option strings* (an empty `""` makes the
  dialog block; see `SKILL.md` Rule 1).
- The `inra.ijpb.*` Java API never shows dialogs and is preferred for robust cleanup/counting.
- **Interactive-only** (open a persistent GUI, not for headless scripts): Morphological
  Segmentation, Interactive Marker-controlled Watershed, Interactive Morphological
  Reconstruction (2D/3D), Interactive Geodesic Distance Map, Label Edition.

---

## What changed 1.4 → 1.6.5 (so old macros/skills are corrected)
- **Renames** (old name kept only under a `_Deprecated` submenu):
  *Inertia Ellipse* → **Equivalent Ellipse** (1.4.2); *Inertia Ellipsoid* → **Equivalent
  Ellipsoid** (1.4.1); *Label Size Opening* → **Label Size Filtering** (1.4.2, with more
  filter operators).
- **Added:** Average Thickness, Convexify, Neighbor Labels (1.4.2); Merge Labels, Dilate
  Labels (1.4.3); watershed **Compactness** parameter, 6-weight 3D chamfer masks (1.5.0);
  Label Morphological Filters, Fill Label Holes, Region Boundaries Labeling, Binary/Label
  Overlay, Draw Labels as Overlay (1.6.0); Skeleton Geodesic Diameter, **Label Map to ROIs**
  (1.6.3/1.6.4); **Euclidean Distance Map**, binary morphological filters, Region Influence
  Zones, Skeletonize Labels, **Binarize Image**, Max-Feret/Geodesic in Analyze Regions 3D,
  center-of-mass in Intensity Measures (1.6.5).

## Installation
**Fiji:** Help ▸ Update… ▸ Manage update sites ▸ activate **IJPB-plugins** ▸ Apply changes ▸
Restart. *(Already installed on this system — `Plugins ▸ MorphoLibJ` is present.)*
Update site: `https://sites.imagej.net/IJPB-plugins/`

## Known limitations
- Distance transforms / Distance Transform Watershed require **8-bit binary (0/255)** input.
- `Connected Components Labeling` 32-bit output is `type=float` (not `[32 bits]`); on label
  overflow it errors ("Try with larger data type").
- Label image capacity: 8-bit ≤ 255 labels, 16-bit ≤ 65 535, float ≈ 16 million.
- `dynamic`/`tolerance` scales with intensity range (see SKILL.md).
- RGB images are accepted only by morphological filters — not by segmentation/analysis.
- Interactive plugins cannot run headless and leave windows open.

## Citation & links
Legland, D., Arganda-Carreras, I., & Andrey, P. (2016). *MorphoLibJ: integrated library and
plugins for mathematical morphology with ImageJ.* Bioinformatics 32(22):3532–3534.
DOI: 10.1093/bioinformatics/btw413

| Resource | URL |
|----------|-----|
| Homepage / wiki | https://imagej.net/plugins/morpholibj |
| GitHub (source + releases) | https://github.com/ijpb/MorphoLibJ |
| JavaDoc | https://ijpb.github.io/MorphoLibJ/javadoc/ |
