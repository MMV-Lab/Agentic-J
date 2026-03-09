# MorphoLibJ — GROOVY / MACRO API

This document lists every confirmed IJ.run() command string and scripting API call
for MorphoLibJ. All entries are sourced from the official MorphoLibJ user manual
(Legland et al., 2018) and source code.

---

## IMPORTANT NOTES

1. All `IJ.run()` commands are macro-recordable. Use **Plugins ▶ Macros ▶ Record…** to capture exact parameter strings.
2. The Morphological Segmentation plugin uses `IJ.run()` + `IJ.call()` (not all parameters fit on one line).
3. Parameter strings use `key=value` pairs separated by spaces.
4. Image references in parameter strings use the **window title** (the image name shown in the title bar).
5. Boolean parameters: use `"true"` / `"false"` strings in `call()`, and presence/absence of keyword in `IJ.run()` (e.g. `"use"` = true, omit = false).

---

## A. MORPHOLOGICAL FILTERS

### A1. Morphological Filters (2D)
```groovy
IJ.run(imp, "Morphological Filters", 
    "operation=<OP> element=<ELEM> radius=<R>")
```
**Parameters:**
| Key | Values | Default |
|-----|--------|---------|
| operation | Erosion, Dilation, Closing, Opening, White Top Hat, Black Top Hat, Gradient, Laplacian | Erosion |
| element | Disk, Square, Octagon, Diamond, Line | Disk |
| radius | integer ≥ 1 | 2 |

**Examples:**
```groovy
IJ.run(imp, "Morphological Filters", "operation=Erosion element=Disk radius=2")
IJ.run(imp, "Morphological Filters", "operation=Opening element=Square radius=3")
IJ.run(imp, "Morphological Filters", "operation=White Top Hat element=Disk radius=10")
IJ.run(imp, "Morphological Filters", "operation=Gradient element=Disk radius=1")
```

**Output:** New image window (same type as input).

---

### A2. Morphological Filters (3D)
```groovy
IJ.run(imp, "Morphological Filters (3D)", 
    "operation=<OP> element=<ELEM> radius=<R>")
// or per-axis radius:
IJ.run(imp, "Morphological Filters (3D)", 
    "operation=<OP> element=<ELEM> radiusX=<RX> radiusY=<RY> radiusZ=<RZ>")
```
**Parameters:** Same operations as 2D. Additional elements: **Ball**, **Cube**. Per-axis radius supported.

```groovy
IJ.run(imp, "Morphological Filters (3D)", "operation=Closing element=Ball radius=2")
IJ.run(imp, "Morphological Filters (3D)", "operation=Erosion element=Cube radiusX=2 radiusY=2 radiusZ=1")
```

---

### A3. Directional Filtering
```groovy
IJ.run(imp, "Directional Filtering", 
    "type=<TYPE> operation=<OP> line=<LENGTH> direction=<N>")
```
**Parameters:**
| Key | Values |
|-----|--------|
| type | Max, Min |
| operation | Opening, Closing, Erosion, Dilation, Median |
| line | line length in pixels (integer) |
| direction | number of orientations, e.g. 32 |

```groovy
IJ.run(imp, "Directional Filtering", "type=Max operation=Opening line=25 direction=32")
IJ.run(imp, "Directional Filtering", "type=Min operation=Closing line=15 direction=16")
```

---

## B. MORPHOLOGICAL RECONSTRUCTION

### B1. Morphological Reconstruction
```groovy
IJ.run("Morphological Reconstruction", 
    "marker=<MARKER_TITLE> mask=<MASK_TITLE> type=[By Dilation] connectivity=4")
```
**Parameters:**
| Key | Values |
|-----|--------|
| marker | window title of marker image |
| mask | window title of mask image |
| type | By Dilation, By Erosion |
| connectivity | 4 or 8 (2D); 6 or 26 (3D) |

```groovy
IJ.run("Morphological Reconstruction", 
    "marker=marker mask=myImage type=[By Dilation] connectivity=4")
```

---

### B2. Kill Borders
```groovy
IJ.run(imp, "Kill Borders", "")
```
Removes particles/regions touching the image border. Works on 2D and 3D binary or grayscale images.

---

### B3. Fill Holes
```groovy
IJ.run(imp, "Fill Holes (Binary/Gray)", "")
```
Fills holes in binary particles. On grayscale images, fills dark regions enclosed by bright crests.

---

## C. MINIMA AND MAXIMA

### C1. Regional Min & Max
```groovy
IJ.run(imp, "Regional Min & Max", 
    "operation=[Regional Maxima] connectivity=4")
IJ.run(imp, "Regional Min & Max", 
    "operation=[Regional Minima] connectivity=8")
```

### C2. Extended Min & Max
```groovy
IJ.run(imp, "Extended Min & Max", 
    "operation=[Extended Maxima] connectivity=4 dynamic=10")
IJ.run(imp, "Extended Min & Max", 
    "operation=[Extended Minima] connectivity=4 dynamic=10")
```
**dynamic** — tolerance value (integer). Higher = fewer, larger extrema.

### C3. Impose Min & Max
```groovy
IJ.run("Impose Min & Max", 
    "image=<INPUT_TITLE> marker=<MARKER_TITLE> operation=[Impose Minima]")
```

### C4. 3D Variants
```groovy
IJ.run(imp, "Regional Min & Max 3D", 
    "operation=[Regional Maxima] connectivity=6")
IJ.run(imp, "Extended Min & Max 3D", 
    "operation=[Extended Maxima] connectivity=6 dynamic=30")
IJ.run("Impose Min & Max 3D", 
    "image=<INPUT_TITLE> marker=<MARKER_TITLE> operation=[Impose Minima]")
```

---

## D. ATTRIBUTE FILTERING

### D1. Grayscale Attribute Filtering (2D)
```groovy
IJ.run(imp, "Grayscale Attribute Filtering", 
    "operation=Opening attribute=Area minimum=100 connectivity=4")
```
**Parameters:**
| Key | Values |
|-----|--------|
| operation | Opening, Closing, White Top Hat, Black Top Hat |
| attribute | Area, Diameter |
| minimum | integer threshold for attribute |
| connectivity | 4 or 8 |

```groovy
IJ.run(imp, "Grayscale Attribute Filtering", 
    "operation=Opening attribute=Area minimum=200 connectivity=4")
IJ.run(imp, "Grayscale Attribute Filtering", 
    "operation=Closing attribute=Diameter minimum=10 connectivity=8")
```

### D2. Grayscale Attribute Filtering 3D
```groovy
IJ.run(imp, "Grayscale Attribute Filtering 3D", 
    "operation=Opening attribute=Volume minimum=500 connectivity=6")
```

---

## E. SEGMENTATION

### E1. Classic Watershed
```groovy
IJ.run(imp, "Classic Watershed", 
    "input=<INPUT_TITLE> mask=None use min=0 max=255")
// With mask:
IJ.run("Classic Watershed", 
    "input=<INPUT_TITLE> mask=<MASK_TITLE> use min=0 max=255")
// Without diagonal connectivity (omit "use"):
IJ.run(imp, "Classic Watershed", 
    "input=<INPUT_TITLE> mask=None min=0 max=255")
```
**Parameters:**
| Key | Notes |
|-----|-------|
| input | window title of grayscale input image |
| mask | window title of binary mask, or "None" |
| use | presence = use diagonal connectivity (8/26); absence = no diagonals (4/6) |
| min | minimum flooding level (integer) |
| max | maximum flooding level (integer) |

**Output:** New labeled image (title: "<input>-watershed").

```groovy
// Complete example (macro style, works in Groovy too):
IJ.run("Blobs (25K)")
IJ.run("Invert LUT")
IJ.run("Invert")
IJ.run("Classic Watershed", "input=blobs mask=None use min=0 max=150")
IJ.run("3-3-2 RGB")
```

---

### E2. Marker-controlled Watershed
```groovy
IJ.run("Marker-controlled Watershed", 
    "input=<INPUT_TITLE> marker=<MARKER_TITLE> mask=None calculate use")
// Without dams (omit "calculate"):
IJ.run("Marker-controlled Watershed", 
    "input=<INPUT_TITLE> marker=<MARKER_TITLE> mask=None use")
```
**Parameters:**
| Key | Notes |
|-----|-------|
| input | gradient image window title |
| marker | labeled marker image window title |
| mask | binary mask or "None" |
| calculate | presence = compute watershed lines (dams) |
| use | presence = use diagonal connectivity |

---

### E3. Morphological Segmentation (via macro call)
This plugin requires a two-step approach: launch GUI, then call methods.

```groovy
// Step 1: open the plugin
IJ.run("Morphological Segmentation")
// Step 2: wait for GUI to load
IJ.wait(1000)

// Step 3: set input image type
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setInputImageType", "object")
// OR for border images:
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setInputImageType", "border")

// Step 4: set gradient radius (only relevant when input type = "object")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setGradientRadius", "1")

// Step 5: run segmentation
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "segment",
    "tolerance=10", "calculateDams=true", "connectivity=6")
// For 2D images use connectivity=4 or connectivity=8

// Step 6: set display format
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setDisplayFormat", "Overlaid basins")
// Other formats: "Overlaid dams", "Catchment basins", "Watershed lines"

// Step 7 (optional): toggle overlay
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "toggleOverlay")

// Step 8: create result image
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "createResultImage")
```

**segment() parameters:**
| Parameter string | Values |
|-----------------|--------|
| tolerance=N | integer; 10 for 8-bit, ~2000 for 16-bit |
| calculateDams=true/false | include watershed lines |
| connectivity=N | 4 or 8 (2D); 6 or 26 (3D) |

**⚠ Note:** In Groovy scripts, use `IJ.call(className, methodName, args...)` syntax.
In IJ macro language, use `call("inra.ijpb.plugins.MorphologicalSegmentation.methodName", args...)`.

**Full Groovy example:**
```groovy
import ij.IJ

IJ.run("Blobs (25K)")
IJ.run("Morphological Segmentation")
IJ.wait(1000)
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setInputImageType", "object")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setGradientRadius", "1")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "segment",
    "tolerance=32", "calculateDams=true", "connectivity=4")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setDisplayFormat", "Overlaid dams")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "createResultImage")
```

---

### E4. Distance Transform Watershed (2D)
```groovy
IJ.run(imp, "Distance Transform Watershed", 
    "distances=[Borgefors (3,4)] output=[32 bits] normalize dynamic=1.00 connectivity=4")
```
**Parameters:**
| Key | Values |
|-----|--------|
| distances | Chessboard (1,1), City-Block (1,2), Quasi-Euclidean (1,1.41), Borgefors (3,4), Weights (2,3), Weights (5,7), Chessknight (5,7,11) |
| output | 16 bits, 32 bits |
| normalize | presence = normalize weights |
| dynamic | float; higher = more merges |
| connectivity | 4 or 8 |

```groovy
IJ.run(imp, "Distance Transform Watershed", 
    "distances=[Borgefors (3,4)] output=[32 bits] normalize dynamic=1.00 connectivity=4")
IJ.run(imp, "Distance Transform Watershed", 
    "distances=[Chessknight (5,7,11)] output=[32 bits] normalize dynamic=2.00 connectivity=4")
```

### E5. Distance Transform Watershed 3D
```groovy
IJ.run(imp, "Distance Transform Watershed 3D",
    "distances=[Borgefors (3,4,5)] output=[16 bits] normalize dynamic=2.00 connectivity=6")
```

---

## F. BINARY IMAGES

### F1. Connected Components Labeling
```groovy
IJ.run(imp, "Connected Components Labeling", "connectivity=4 type=[16 bits]")
IJ.run(imp, "Connected Components Labeling", "connectivity=8 type=[32 bits]")
// 3D:
IJ.run(imp, "Connected Components Labeling", "connectivity=6 type=[16 bits]")
IJ.run(imp, "Connected Components Labeling", "connectivity=26 type=[32 bits]")
```

### F2. Chamfer Distance Map (2D)
```groovy
IJ.run(imp, "Chamfer Distance Map", 
    "distances=[Borgefors (3,4)] output=[32 bits] normalize")
IJ.run(imp, "Chamfer Distance Map", 
    "distances=[Chessknight (5,7,11)] output=[32 bits] normalize")
```

### F3. Chamfer Distance Map 3D
```groovy
IJ.run(imp, "Chamfer Distance Map 3D", 
    "distances=[Borgefors (3,4,5)] output=[32 bits] normalize")
```

### F4. Geodesic Distance Map
```groovy
IJ.run("Geodesic Distance Map", 
    "marker=<MARKER_TITLE> mask=<MASK_TITLE> distances=[Borgefors (3,4)] output=[32 bits] normalize")
```

### F5. Binary Utilities
```groovy
IJ.run(imp, "Keep Largest Region", "")
IJ.run(imp, "Remove Largest Region", "")
IJ.run(imp, "Size Opening 2D/3D", "min=100")   // removes connected components with area < 100 px
```

---

## G. ANALYSIS

### G1. Analyze Regions (2D)
```groovy
IJ.run(imp, "Analyze Regions", 
    "area perimeter circularity inertia_ellipse ellipse_elong convexity " +
    "max_feret oriented_box oriented_box_elong geodesic_diameter tortuosity " +
    "max_inscribed_disc geodesic_elong")
```
Include only the keywords for measurements you want. All are optional.

**Keyword reference:**
| Keyword | Columns produced |
|---------|-----------------|
| area | Area |
| perimeter | Perimeter |
| circularity | Circularity |
| inertia_ellipse | Ellipse.Center.X, Ellipse.Center.Y, Ellipse.Radius1, Ellipse.Radius2, Ellipse.Orientation |
| ellipse_elong | Ellipse.Elong |
| convexity | Convexity |
| max_feret | MaxFeret |
| oriented_box | OBox.Center.X, OBox.Center.Y, OBox.Length, OBox.Width, OBox.Orientation |
| oriented_box_elong | OBox.Elong |
| geodesic_diameter | Geod.Diam, InscrCircle.Radius |
| tortuosity | Tortuosity |
| max_inscribed_disc | InscrCircle.Center.X, InscrCircle.Center.Y, InscrCircle.Radius |
| geodesic_elong | Geod.Elong |

### G2. Analyze Regions 3D
```groovy
IJ.run(imp, "Analyze Regions 3D",
    "volume surface_area mean_breadth euler_number inertia_ellipsoid " +
    "ellipsoid_elong1 ellipsoid_elong2")
```

### G3. Intensity Measurements 2D/3D
```groovy
IJ.run("Intensity Measurements 2D/3D",
    "input=<GRAY_IMAGE_TITLE> labels=<LABEL_IMAGE_TITLE> mean stddev max min median mode")
```

### G4. Label Overlap Measures
```groovy
IJ.run("Label Overlap Measures",
    "source=<SOURCE_TITLE> target=<TARGET_TITLE> overlap jaccard dice")
```

### G5. Region Adjacency Graph
```groovy
IJ.run(imp, "Region Adjacency Graph", "")
```
Output: ResultsTable with columns Label1, Label2 for each adjacent pair.

### G6. Microstructure Analysis (2D)
```groovy
IJ.run(imp, "Microstructure Analysis", "")
```

---

## H. LABEL IMAGE UTILITIES

```groovy
// Change LUT / shuffle colors
IJ.run(imp, "Set Label Map", "colormap=Golden_angle background=White shuffle")

// Convert to RGB
IJ.run(imp, "Labels to RGB", "colormap=Golden_angle background=White shuffle")

// Assign measurement to label image
IJ.run("Assign Measure to Label", 
    "results=<TABLE_TITLE> column=<COLUMN_NAME> labels=<LABEL_TITLE>")

// Create binary boundary image
IJ.run(imp, "Label Boundaries", "")

// Remove border labels
IJ.run(imp, "Remove Border Labels", "")

// Replace / Remove labels
IJ.run(imp, "Replace/Remove Label(s)", "label=3 new=0")   // removes label 3
IJ.run(imp, "Replace/Remove Label(s)", "label=3 new=5")   // merges label 3 into 5

// Select specific labels
IJ.run(imp, "Select Label(s)", "label=2 label=5 label=8")

// Crop single label
IJ.run(imp, "Crop Label", "label=3 border=0")

// Size opening on labels
IJ.run(imp, "Label Size Opening", "min=100")

// Remap labels to 1..N (remove gaps)
IJ.run(imp, "Remap Labels", "")

// Keep / Remove largest label
IJ.run(imp, "Keep Largest Label", "")
IJ.run(imp, "Remove Largest Label", "")
```

---

## I. JAVA / GROOVY SCRIPTING API

For advanced scripting, use the `inra.ijpb.*` library directly.

### Key import packages:
```groovy
import inra.ijpb.binary.BinaryImages
import inra.ijpb.morphology.Morphology
import inra.ijpb.morphology.Strel
import inra.ijpb.morphology.Strel3D
import inra.ijpb.morphology.MinimaAndMaxima
import inra.ijpb.morphology.MinimaAndMaxima3D
import inra.ijpb.watershed.Watershed
import inra.ijpb.label.LabelImages
import inra.ijpb.measure.region2d.RegionAnalysis2D
```

### Key static method calls:
```groovy
// Morphological gradient (3D)
def strel = Strel3D.Shape.CUBE.fromRadius(1)
def gradientStack = Morphology.gradient(imp.getImageStack(), strel)

// Extended minima (3D)
def minima = MinimaAndMaxima3D.extendedMinima(gradientStack, 30, 6)

// Impose minima (3D)
def imposed = MinimaAndMaxima3D.imposeMinima(gradientStack, minima, 6)

// Connected component labeling (3D, 32-bit output)
def labeled = BinaryImages.componentsLabeling(minima, 6, 32)

// Watershed (3D, with dams)
def result = Watershed.computeWatershed(imposed, labeled, 6, true)

// All labels in image
def labels = LabelImages.findAllLabels(imp)
```

---

## J. KNOWN QUIRKS AND PITFALLS

1. **Morphological Segmentation + macros:** Always add `IJ.wait(1000)` after launching the plugin before calling any `IJ.call()` commands, or the GUI won't be ready.
2. **Image title spaces:** When an image title contains spaces, wrap it in brackets in the parameter string: `"input=[my image] mask=None"`.
3. **Classic Watershed connectivity:** The `"use"` keyword enables diagonal connectivity. Omitting it uses 4-connectivity (2D) / 6-connectivity (3D).
4. **Tolerance scaling for 16-bit:** A tolerance of 10 is suitable for 8-bit (0–255 range). Scale proportionally for 16-bit (~2000) or 32-bit.
5. **Distance Transform Watershed input:** Requires an 8-bit binary image (not 16-bit or 32-bit). Convert with `IJ.run(imp, "8-bit", "")` if needed.
6. **Label image types:** Byte (max 255 labels), Short (max 65535), Float-32 (max ~16M). Use `type=[16 bits]` or `type=[32 bits]` in Connected Components Labeling.
