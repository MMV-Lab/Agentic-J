# MorphoLibJ — OVERVIEW

## What It Is
MorphoLibJ is a comprehensive Fiji/ImageJ plugin library implementing mathematical
morphology operators that are absent from core ImageJ. It is developed and maintained
by INRA (now INRAE) and is freely available via the IJPB-plugins Fiji update site.

The library covers four major domains:
- **Morphological filtering** — erosion, dilation, opening, closing, top-hats, gradients, Laplacian
- **Morphological reconstruction** — hole filling, border removal, attribute filtering
- **Watershed segmentation** — classic, marker-controlled, interactive, morphological, distance-transform-based
- **Quantitative region analysis** — 2D and 3D shape descriptors, intensity measurements, label overlap

---

## Typical Inputs and Use Cases

### Fluorescence microscopy — cell / nucleus segmentation
- **Input:** 8-bit or 16-bit grayscale fluorescence image of stained nuclei or cells
- **Pipeline:** Threshold → Chamfer Distance Map → Regional Maxima → Marker-controlled Watershed
- **Goal:** Separate touching or overlapping round objects; count cells; measure size and shape
- **Key plugins:** Chamfer Distance Map, Regional Min & Max, Connected Components Labeling, Marker-controlled Watershed, Analyze Regions

### Brightfield microscopy — cell colony analysis
- **Input:** 8-bit grayscale phase contrast or brightfield image
- **Pipeline:** Morphological Gradient → Extended Minima → Marker-controlled Watershed → Remove Border Labels → Analyze Regions
- **Goal:** Segment colony boundaries, measure colony area, count cells
- **Key plugins:** Morphological Filters (Gradient), Extended Min & Max, Marker-controlled Watershed, Label Size Opening

### Plant cell imaging — cell wall segmentation
- **Input:** 8-bit or 16-bit fluorescence image with bright cell walls and dark cell interiors
- **Pipeline:** Morphological Segmentation (border image mode) → Analyze Regions
- **Goal:** Segment individual plant cells bounded by bright walls; measure cell area, perimeter, elongation
- **Key plugins:** Morphological Segmentation, Analyze Regions (2D or 3D)

### 3D tissue analysis (confocal stacks)
- **Input:** 16-bit 3D stack
- **Pipeline:** Morphological Filters 3D (Gradient) → Extended Min & Max 3D → Marker-controlled Watershed (3D via Java API) → Analyze Regions 3D
- **Goal:** Segment 3D cells or organelles; measure volume, surface area, inertia ellipsoid
- **Key plugins:** Morphological Filters (3D), Extended Min & Max 3D, Analyze Regions 3D

### Materials science — particle / grain analysis
- **Input:** 8-bit or 16-bit SEM/TEM image of particles, fibres, or grains
- **Pipeline:** Threshold → Distance Transform Watershed → Label Size Opening → Analyze Regions
- **Goal:** Separate touching particles; measure size distribution, circularity, Feret diameter
- **Key plugins:** Distance Transform Watershed, Analyze Regions, Max Feret Diameter

### Thin structures — blood vessels, fibres, cell walls
- **Input:** 2D fluorescence or bright-field image with curvilinear structures
- **Pipeline:** Directional Filtering (Max, Opening) → Threshold → Connected Components → Geodesic Diameter
- **Goal:** Enhance and segment thin curvilinear structures; measure length, tortuosity
- **Key plugins:** Directional Filtering, Connected Components Labeling, Geodesic Diameter

### Segmentation validation / comparison
- **Input:** Two label images (predicted segmentation vs. ground truth)
- **Pipeline:** Label Overlap Measures
- **Goal:** Quantify segmentation accuracy with Jaccard index, Dice coefficient, overlap fractions
- **Key plugins:** Label Overlap Measures

---

## Input Image Requirements by Task

| Task | Required type | Notes |
|------|--------------|-------|
| Morphological filters | 8/16/32-bit gray or RGB | RGB supported for filters only |
| Distance Transform (Chamfer) | Binary 8-bit (0/255) | Must be 8-bit for Distance Transform Watershed |
| Watershed segmentation | 8/16-bit grayscale | Gradient or inverted distance map |
| Connected Components Labeling | Binary (any bit-depth) | |
| Analyze Regions | Label image (integer values) | Binary treated as single region |
| Analyze Regions 3D | Label image stack | |
| Label Overlap Measures | Two label images, same size | |

---

## Typical Output Types

| Output type | Produced by |
|-------------|-------------|
| Filtered grayscale image | Morphological Filters, Directional Filtering |
| Binary image | Morphological Reconstruction, Fill Holes, Kill Borders, Regional Min & Max |
| Label image (integer) | Connected Components Labeling, Watershed variants |
| Distance map (32-bit float) | Chamfer Distance Map, Geodesic Distance Map |
| ImageJ ResultsTable | Analyze Regions, Intensity Measurements, Label Overlap Measures |
| RGB color image | Labels to RGB |

---

## Automation Level
**Fully scriptable** via `IJ.run()` macro commands or the `inra.ijpb.*` Java/Groovy API.
- All standard plugins record in the Fiji macro recorder (Plugins ▶ Macros ▶ Record…)
- Interactive plugins (Interactive Marker-controlled Watershed, Interactive Morphological
  Reconstruction) require user ROI input and cannot run headless, but all have
  programmatic equivalents
- Morphological Segmentation uses `IJ.run()` + `IJ.call()` (two-step approach)

---

## Installation

**Fiji (recommended):**
1. Help ▶ Update…
2. Click **Manage update sites**
3. Activate **IJPB-plugins**
4. Click **Apply changes**, then **Restart Fiji**

**ImageJ (plain):**
Download the latest MorphoLibJ `.jar` from https://github.com/ijpb/MorphoLibJ/releases
and place it in `ImageJ/plugins/`, then restart ImageJ.

Update site URL: `http://sites.imagej.net/IJPB-plugins/`

---

## Known Limitations

- `Distance Transform Watershed` requires an **8-bit binary** input image. Convert with
  `Image ▶ Type ▶ 8-bit` and apply a threshold before using it.
- `Chamfer Distance Map` also requires binary input (8-bit, values 0 and 255).
- Geodesic diameter uses Chamfer approximation and may slightly overestimate true geodesic length.
- `Morphological Segmentation` macro automation requires `wait(1000)` between launching
  the plugin and calling methods via `IJ.call()`, otherwise the GUI is not ready.
- Image titles containing spaces must be wrapped in brackets in parameter strings:
  `"input=[my image] mask=None"`.
- Tolerance in Morphological Segmentation is intensity-scale-dependent: use ~10 for
  8-bit images and ~2000 for 16-bit images.
- Label image capacity: byte = 255 labels, short = 65 535, 32-bit float ≈ 16 million.
- 3D plugins generally do not provide a live Preview option.
- RGB images are accepted only by morphological filters — not by segmentation or analysis plugins.

---

## Citation

> Legland, D., Arganda-Carreras, I., & Andrey, P. (2016).
> MorphoLibJ: integrated library and plugins for mathematical morphology with ImageJ.
> *Bioinformatics*, 32(22), 3532–3534.
> DOI: 10.1093/bioinformatics/btw413

## Links

| Resource | URL |
|----------|-----|
| Project homepage | http://ijpb.github.io/MorphoLibJ/ |
| GitHub (source + releases) | https://github.com/ijpb/MorphoLibJ |
| JavaDoc API | http://ijpb.github.io/MorphoLibJ/javadoc/ |
| ImageJ wiki page | https://imagej.net/plugins/morpholibj |
