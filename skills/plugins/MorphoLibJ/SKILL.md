# MorphoLibJ — SKILL SUMMARY (LLM Reference Card)

## Overview
MorphoLibJ is a Fiji/ImageJ plugin library providing mathematical morphology operations
missing from core ImageJ. It covers: **morphological filtering** (erosion/dilation/opening/
closing/top-hat/gradient/Laplacian), **morphological reconstruction** (fill holes, kill borders),
**watershed segmentation** (classic, marker-controlled, interactive, morphological, distance-
transform-based), **region measurements** (area, perimeter, shape, 3D), and **label image
utilities** (labeling, editing, distance maps). All major plugins are fully scriptable via
`IJ.run()` or the `inra.ijpb.*` Java API. Install via Fiji update site **IJPB-plugins**.

---

## Quick-Reference Command Table

| Purpose | IJ.run() command string |
|---------|------------------------|
| Morphological erosion (2D) | `"Morphological Filters", "operation=Erosion element=Disk radius=2"` |
| Morphological opening (2D) | `"Morphological Filters", "operation=Opening element=Disk radius=3"` |
| White top-hat (2D) | `"Morphological Filters", "operation=White Top Hat element=Disk radius=10"` |
| Morphological gradient (2D) | `"Morphological Filters", "operation=Gradient element=Disk radius=1"` |
| Morphological filters (3D) | `"Morphological Filters (3D)", "operation=Closing element=Ball radius=2"` |
| Directional filtering | `"Directional Filtering", "type=Max operation=Opening line=25 direction=32"` |
| Kill borders | `"Kill Borders", ""` |
| Fill holes | `"Fill Holes (Binary/Gray)", ""` |
| Morphological reconstruction | `"Morphological Reconstruction", "marker=m mask=img type=[By Dilation] connectivity=4"` |
| Regional maxima | `"Regional Min & Max", "operation=[Regional Maxima] connectivity=4"` |
| Extended maxima | `"Extended Min & Max", "operation=[Extended Maxima] connectivity=4 dynamic=10"` |
| Attribute size opening | `"Grayscale Attribute Filtering", "operation=Opening attribute=Area minimum=100 connectivity=4"` |
| Classic watershed | `"Classic Watershed", "input=img mask=None use min=0 max=255"` |
| Marker-controlled watershed | `"Marker-controlled Watershed", "input=grad marker=markers mask=None calculate use"` |
| Morphological segmentation | `"Morphological Segmentation"` + `IJ.call(...)` (see GROOVY_API.md §E3) |
| Distance transform watershed | `"Distance Transform Watershed", "distances=[Borgefors (3,4)] output=[32 bits] normalize dynamic=1.00 connectivity=4"` |
| Connected component labeling | `"Connected Components Labeling", "connectivity=4 type=[16 bits]"` |
| Chamfer distance map | `"Chamfer Distance Map", "distances=[Borgefors (3,4)] output=[32 bits] normalize"` |
| Analyze regions 2D | `"Analyze Regions", "area perimeter circularity inertia_ellipse convexity"` |
| Analyze regions 3D | `"Analyze Regions 3D", "volume surface_area mean_breadth euler_number inertia_ellipsoid"` |
| Intensity measurements | `"Intensity Measurements 2D/3D", "input=orig labels=lbl mean stddev max min median"` |
| Label overlap measures | `"Label Overlap Measures", "source=S target=T overlap jaccard dice"` |
| Remove border labels | `"Remove Border Labels", ""` |
| Label size opening | `"Label Size Opening", "min=100"` |
| Remap labels | `"Remap Labels", ""` |
| Labels to RGB | `"Labels to RGB", "colormap=Golden_angle background=Black shuffle"` |

---

## 3 Most Common Pitfalls

### Pitfall 1 — Morphological Segmentation macro timing
**Problem:** Calling `IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", ...)` immediately after `IJ.run("Morphological Segmentation")` fails silently — the GUI is not yet loaded.
**Fix:** Always insert `IJ.wait(1000)` between launching the plugin and calling its methods:
```groovy
IJ.run("Morphological Segmentation")
IJ.wait(1000)   // ← mandatory
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setInputImageType", "object")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "segment",
    "tolerance=10", "calculateDams=true", "connectivity=4")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "createResultImage")
```

### Pitfall 2 — Wrong tolerance for 16-bit images
**Problem:** Using `tolerance=10` on a 16-bit image (0–65535 range) produces a single giant segment because every local fluctuation is smaller than 10 intensity units.
**Fix:** Scale tolerance proportionally to the image bit-depth. For 16-bit data, start with `tolerance=2000`. For 32-bit float images, determine appropriate value empirically from the intensity histogram.

### Pitfall 3 — Image title spaces in parameter strings
**Problem:** `IJ.run("Classic Watershed", "input=my image mask=None ...")` fails when the image title contains spaces — the parameter parser splits on the space.
**Fix:** Wrap titles in square brackets:
```groovy
IJ.run("Classic Watershed", "input=[my image with spaces] mask=None use min=0 max=255")
```
Always use `imp.getTitle()` and wrap in `[...]` if the title might contain spaces.

---

## Detail Files
| File | Contents |
|------|---------|
| `OVERVIEW.md` | Plugin description, input/output types, installation, citation |
| `UI_GUIDE.md` | Step-by-step GUI instructions for all 19 plugin groups |
| `GROOVY_API.md` | Every confirmed IJ.run() command with parameter tables and examples |
| `GROOVY_WORKFLOW.groovy` | End-to-end executable script: gradient → watershed → region analysis → CSV export |

---

## Menu Structure (Plugins ▶ MorphoLibJ)
```
MorphoLibJ
├── Filtering
│   ├── Morphological Filters
│   ├── Morphological Filters (3D)
│   ├── Directional Filtering
│   ├── Morphological Reconstruction
│   ├── Morphological Reconstruction 3D
│   ├── Interactive Morphological Reconstruction
│   ├── Interactive Morphological Reconstruction 3D
│   ├── Kill Borders
│   ├── Fill Holes (Binary/Gray)
│   ├── Grayscale Attribute Filtering
│   └── Grayscale Attribute Filtering 3D
├── Minima and Maxima
│   ├── Regional Min & Max
│   ├── Regional Min & Max 3D
│   ├── Extended Min & Max
│   ├── Extended Min & Max 3D
│   ├── Impose Min & Max
│   └── Impose Min & Max 3D
├── Segmentation
│   ├── Classic Watershed
│   ├── Marker-controlled Watershed
│   ├── Interactive Marker-controlled Watershed
│   ├── Morphological Segmentation
│   └── (Distance Transform Watershed → Binary Images submenu)
├── Analyze
│   ├── Analyze Regions
│   ├── Bounding Box
│   ├── Inertia Ellipse
│   ├── Max Feret Diameter
│   ├── Oriented Box
│   ├── Geodesic Diameter
│   ├── Largest Inscribed Circle
│   ├── Analyze Regions 3D
│   ├── Inertia Ellipsoid
│   ├── Intensity Measurements 2D/3D
│   ├── Label Overlap Measures
│   ├── Microstructure Analysis
│   ├── Microstructure 3D
│   └── Region Adjacency Graph
├── Binary Images
│   ├── Connected Components Labeling
│   ├── Chamfer Distance Map
│   ├── Chamfer Distance Map 3D
│   ├── Geodesic Distance Map
│   ├── Interactive Geodesic Distance Map
│   ├── Geodesic Distance Map 3D
│   ├── Distance Transform Watershed
│   ├── Distance Transform Watershed 3D
│   ├── Keep Largest Region
│   ├── Remove Largest Region
│   └── Size Opening 2D/3D
└── Labels
    ├── Set Label Map
    ├── Labels to RGB
    ├── Assign Measure to Label
    ├── Label Boundaries
    ├── Remove Border Labels
    ├── Replace/Remove Label(s)
    ├── Select Label(s)
    ├── Crop Label
    ├── Keep/Remove Largest Label
    ├── Label Size Opening
    ├── Remap Labels
    └── Label Edition
```
