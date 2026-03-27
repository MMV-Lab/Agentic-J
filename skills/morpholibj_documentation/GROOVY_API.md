# MorphoLibJ — GROOVY / MACRO API REFERENCE

All commands in this file are sourced from the official MorphoLibJ user manual
(Legland et al., 2018) and plugin source code. Commands labelled **[Standard ImageJ]**
are built-in to Fiji/ImageJ and do not require MorphoLibJ.

---

## GENERAL RULES

1. All `IJ.run()` commands are macro-recordable. Use **Plugins ▶ Macros ▶ Record…**
   to capture exact parameter strings for any GUI interaction.
2. Parameter strings use space-separated `key=value` pairs.
3. Image titles with spaces must be wrapped in brackets: `"input=[my image] mask=None"`.
4. Boolean flags in `IJ.run()` are presence/absence keywords (e.g. `"use"` = true,
   omitting `"use"` = false). In `IJ.call()`, use string `"true"` / `"false"`.
5. For the Morphological Segmentation plugin only, use `IJ.run()` then `IJ.wait(1000)`
   then `IJ.call()` — see section E3.

---

## A. MORPHOLOGICAL FILTERS

### A1. Morphological Filters (2D)

```groovy
IJ.run(imp, "Morphological Filters",
    "operation=<OP> element=<ELEM> radius=<R>")
```

| Parameter | Accepted values |
|-----------|----------------|
| operation | `Erosion` `Dilation` `Opening` `Closing` `White Top Hat` `Black Top Hat` `Gradient` `Laplacian` |
| element   | `Disk` `Square` `Octagon` `Diamond` `Line` |
| radius    | integer ≥ 1 |

**Examples:**
```groovy
IJ.run(imp, "Morphological Filters", "operation=Erosion element=Disk radius=2")
IJ.run(imp, "Morphological Filters", "operation=Opening element=Disk radius=3")
IJ.run(imp, "Morphological Filters", "operation=White Top Hat element=Disk radius=10")
IJ.run(imp, "Morphological Filters", "operation=Gradient element=Disk radius=2")
IJ.run(imp, "Morphological Filters", "operation=Closing element=Square radius=4")
```

Output: new image window, same type as input.

---

### A2. Morphological Filters (3D)

```groovy
IJ.run(imp, "Morphological Filters (3D)",
    "operation=<OP> element=<ELEM> radius=<R>")
// Per-axis radius:
IJ.run(imp, "Morphological Filters (3D)",
    "operation=<OP> element=<ELEM> radiusX=<RX> radiusY=<RY> radiusZ=<RZ>")
```

Same operations as 2D. Additional elements: `Ball`, `Cube`.

```groovy
IJ.run(imp, "Morphological Filters (3D)", "operation=Closing element=Ball radius=2")
IJ.run(imp, "Morphological Filters (3D)",
    "operation=Erosion element=Cube radiusX=2 radiusY=2 radiusZ=1")
```

---

### A3. Directional Filtering

Use for images containing thin curvilinear structures (blood vessels, fibres, cell walls).

```groovy
IJ.run(imp, "Directional Filtering",
    "type=<TYPE> operation=<OP> line=<LENGTH> direction=<N>")
```

| Parameter | Accepted values |
|-----------|----------------|
| type      | `Max` `Min` |
| operation | `Opening` `Closing` `Erosion` `Dilation` `Median` |
| line      | line length in pixels (integer) |
| direction | number of orientations to sample, e.g. `32` |

```groovy
IJ.run(imp, "Directional Filtering", "type=Max operation=Opening line=25 direction=32")
IJ.run(imp, "Directional Filtering", "type=Min operation=Closing line=15 direction=16")
```

---

## B. MORPHOLOGICAL RECONSTRUCTION

### B1. Morphological Reconstruction (two-image)

```groovy
IJ.run("Morphological Reconstruction",
    "marker=<MARKER_TITLE> mask=<MASK_TITLE> type=[By Dilation] connectivity=4")
```

| Parameter   | Accepted values |
|-------------|----------------|
| marker      | window title of marker image |
| mask        | window title of mask image |
| type        | `[By Dilation]` `[By Erosion]` |
| connectivity| `4` or `8` (2D); `6` or `26` (3D) |

```groovy
IJ.run("Morphological Reconstruction",
    "marker=markerImage mask=originalImage type=[By Dilation] connectivity=4")
```

---

### B2. Kill Borders

Removes objects or regions touching the image border. Works on binary and grayscale images.

```groovy
IJ.run(imp, "Kill Borders", "")
```

---

### B3. Fill Holes (Binary/Gray)

Fills enclosed holes in binary objects or dark enclosed regions in grayscale images.

```groovy
IJ.run(imp, "Fill Holes (Binary/Gray)", "")
```

---

### B4. Gray Scale Attribute Filtering (2D)

Removes (or retains) image components based on a size attribute.
Better edge preservation than morphological erosion/opening.

```groovy
IJ.run(imp, "Gray Scale Attribute Filtering",
    "operation=Opening attribute=Area minimum=100 connectivity=4")
```

| Parameter  | Accepted values |
|------------|----------------|
| operation  | `Opening` `Closing` `White Top Hat` `Black Top Hat` |
| attribute  | `Area` `Diameter` |
| minimum    | integer threshold for the attribute |
| connectivity | `4` or `8` |

```groovy
IJ.run(imp, "Gray Scale Attribute Filtering",
    "operation=Opening attribute=Area minimum=200 connectivity=4")
IJ.run(imp, "Gray Scale Attribute Filtering",
    "operation=Closing attribute=Diameter minimum=10 connectivity=8")
```

---

### B5. Gray Scale Attribute Filtering 3D

```groovy
IJ.run(imp, "Gray Scale Attribute Filtering 3D",
    "operation=Opening attribute=Volume minimum=500 connectivity=6")
```

---

## C. MINIMA AND MAXIMA

### C1. Regional Min & Max (2D)

Returns a binary image (255 at regional extrema, 0 elsewhere).
Regional maxima = plateaus not dominated by any neighbouring pixel.

```groovy
IJ.run(imp, "Regional Min & Max", "operation=[Regional Maxima] connectivity=4")
IJ.run(imp, "Regional Min & Max", "operation=[Regional Minima] connectivity=4")
IJ.run(imp, "Regional Min & Max", "operation=[Regional Maxima] connectivity=8")
```

---

### C2. Extended Min & Max (2D)

Returns a binary image of extended extrema within a given tolerance.
Less noise-sensitive than regional; preferred for real images.

```groovy
IJ.run(imp, "Extended Min & Max",
    "operation=[Extended Maxima] connectivity=4 dynamic=10")
IJ.run(imp, "Extended Min & Max",
    "operation=[Extended Minima] connectivity=4 dynamic=10")
```

`dynamic` — tolerance (integer). Higher = fewer, larger extrema.
Scale to image bit-depth: ~10 for 8-bit, ~2000 for 16-bit.

---

### C3. Impose Min & Max (2D)

Forces a binary image to define regional minima or maxima in another image.

```groovy
IJ.run("Impose Min & Max",
    "image=<INPUT_TITLE> marker=<MARKER_TITLE> operation=[Impose Minima]")
IJ.run("Impose Min & Max",
    "image=<INPUT_TITLE> marker=<MARKER_TITLE> operation=[Impose Maxima]")
```

---

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

## D. SEGMENTATION

### D1. Classic Watershed

```groovy
IJ.run(imp, "Classic Watershed",
    "input=<INPUT_TITLE> mask=None use min=0 max=255")
// With a binary mask:
IJ.run("Classic Watershed",
    "input=<INPUT_TITLE> mask=<MASK_TITLE> use min=0 max=255")
// Without diagonal connectivity (omit "use"):
IJ.run(imp, "Classic Watershed",
    "input=<INPUT_TITLE> mask=None min=0 max=255")
```

| Parameter | Notes |
|-----------|-------|
| input     | window title of grayscale image to flood |
| mask      | binary mask title, or `None` for full image |
| use       | presence = diagonal connectivity (8/26); absence = orthogonal (4/6) |
| min       | minimum flooding level (integer) |
| max       | maximum flooding level (integer) |

Output: new labeled image named `<input>-watershed`.

---

### D2. Marker-controlled Watershed

Requires a grayscale input image, a labeled marker image, and optionally a binary mask.

```groovy
// With watershed lines (dams) + diagonal connectivity:
IJ.run("Marker-controlled Watershed",
    "input=<INPUT_TITLE> marker=<MARKER_TITLE> mask=None calculate use")
// Without dams:
IJ.run("Marker-controlled Watershed",
    "input=<INPUT_TITLE> marker=<MARKER_TITLE> mask=None use")
// With mask, no dams, no diagonal:
IJ.run("Marker-controlled Watershed",
    "input=<INPUT_TITLE> marker=<MARKER_TITLE> mask=<MASK_TITLE> calculate")
```

| Parameter | Notes |
|-----------|-------|
| input     | gradient or landscape image title |
| marker    | labeled integer marker image title (one label per seed) |
| mask      | binary mask title, or `None` |
| calculate | presence = include watershed lines (0-valued pixels) |
| use       | presence = diagonal connectivity (8/26) |

---

### D3. Morphological Segmentation (two-step macro)

This plugin has an interactive GUI and requires `IJ.call()` to drive it from a script.
**Always** insert `IJ.wait(1000)` after `IJ.run()` before any `IJ.call()`.

```groovy
// Step 1: launch plugin
IJ.run("Morphological Segmentation")
// Step 2: mandatory wait for GUI to initialise
IJ.wait(1000)

// Step 3a: if input has bright objects on dark background
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation",
    "setInputImageType", "object")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation",
    "setGradientRadius", "1")

// Step 3b: if input already has bright boundaries (border image)
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation",
    "setInputImageType", "border")

// Step 4: run watershed
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "segment",
    "tolerance=10", "calculateDams=true", "connectivity=4")

// Step 5: choose display and create result image
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation",
    "setDisplayFormat", "Catchment basins")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation",
    "createResultImage")
```

`setDisplayFormat` accepted values: `"Overlaid basins"`, `"Overlaid dams"`,
`"Catchment basins"`, `"Watershed lines"`

`segment()` parameters:
| String | Values |
|--------|--------|
| `"tolerance=N"` | integer; 10 for 8-bit, ~2000 for 16-bit |
| `"calculateDams=true"` or `"calculateDams=false"` | |
| `"connectivity=N"` | `4` or `8` (2D); `6` or `26` (3D) |

---

### D4. Distance Transform Watershed (2D, single step)

Combines Chamfer distance map + watershed in one call.
**Input must be an 8-bit binary image.**

```groovy
IJ.run(imp, "Distance Transform Watershed",
    "distances=[Borgefors (3,4)] output=[32 bits] normalize dynamic=1.00 connectivity=4")
```

| Parameter  | Accepted values |
|------------|----------------|
| distances  | `[Chessboard (1,1)]` `[City-Block (1,2)]` `[Quasi-Euclidean (1,1.41)]` `[Borgefors (3,4)]` `[Weights (2,3)]` `[Chessknight (5,7,11)]` |
| output     | `[16 bits]` `[32 bits]` |
| normalize  | presence = divide distances by first weight |
| dynamic    | float; higher = more merges (fewer segments) |
| connectivity | `4` or `8` |

```groovy
// More accurate weights:
IJ.run(imp, "Distance Transform Watershed",
    "distances=[Chessknight (5,7,11)] output=[32 bits] normalize dynamic=2.00 connectivity=4")
```

---

### D5. Distance Transform Watershed 3D

```groovy
IJ.run(imp, "Distance Transform Watershed 3D",
    "distances=[Borgefors (3,4,5)] output=[16 bits] normalize dynamic=2.00 connectivity=6")
```

---

## E. BINARY IMAGE OPERATIONS

### E1. Connected Components Labeling

```groovy
// 2D, 4-connectivity, 16-bit output:
IJ.run(imp, "Connected Components Labeling", "connectivity=4 type=[16 bits]")
// 2D, 8-connectivity, 32-bit output:
IJ.run(imp, "Connected Components Labeling", "connectivity=8 type=[32 bits]")
// 3D, 6-connectivity:
IJ.run(imp, "Connected Components Labeling", "connectivity=6 type=[16 bits]")
// 3D, 26-connectivity:
IJ.run(imp, "Connected Components Labeling", "connectivity=26 type=[32 bits]")
```

---

### E2. Chamfer Distance Map (2D)

Input: binary image (8-bit, 0/255).

```groovy
IJ.run(imp, "Chamfer Distance Map",
    "distances=[Borgefors (3,4)] output=[32 bits] normalize")
IJ.run(imp, "Chamfer Distance Map",
    "distances=[Chessknight (5,7,11)] output=[32 bits] normalize")
```

| distances option | Accuracy |
|------------------|---------|
| `[Chessboard (1,1)]` | Low — 8-connected distance |
| `[City-Block (1,2)]` | Low — 4-connected distance |
| `[Borgefors (3,4)]` | Good — standard 2D approximation |
| `[Chessknight (5,7,11)]` | Better — includes knight moves |

---

### E3. Chamfer Distance Map 3D

```groovy
IJ.run(imp, "Chamfer Distance Map 3D",
    "distances=[Borgefors (3,4,5)] output=[32 bits] normalize")
```

---

### E4. Geodesic Distance Map

```groovy
IJ.run("Geodesic Distance Map",
    "marker=<MARKER_TITLE> mask=<MASK_TITLE> distances=[Borgefors (3,4)] output=[32 bits] normalize")
```

---

### E5. Binary Size and Shape Utilities

```groovy
IJ.run(imp, "Keep Largest Region", "")      // keep only the largest connected component
IJ.run(imp, "Remove Largest Region", "")    // remove the largest connected component
IJ.run(imp, "Size Opening 2D/3D", "min=100") // remove components smaller than 100 px
```

---

## F. ANALYSIS

### F1. Analyze Regions (2D)

Input: label image (or binary treated as single region).

```groovy
IJ.run(imp, "Analyze Regions",
    "area perimeter circularity inertia_ellipse ellipse_elong convexity " +
    "max_feret oriented_box oriented_box_elong geodesic_diameter tortuosity " +
    "max_inscribed_disc geodesic_elong")
```

Include only the keywords for measurements you need:

| Keyword | Columns produced |
|---------|-----------------|
| `area` | Area |
| `perimeter` | Perimeter (Crofton method) |
| `circularity` | Circularity = 4π·Area/Perimeter² |
| `inertia_ellipse` | Ellipse.Center.X/Y, Radius1, Radius2, Orientation |
| `ellipse_elong` | Ellipse.Elong |
| `convexity` | Convexity |
| `max_feret` | MaxFeret |
| `oriented_box` | OBox.Center.X/Y, OBox.Length, OBox.Width, OBox.Orientation |
| `oriented_box_elong` | OBox.Elong |
| `geodesic_diameter` | Geod.Diam, InscrCircle.Radius |
| `tortuosity` | Tortuosity |
| `max_inscribed_disc` | InscrCircle.Center.X/Y, InscrCircle.Radius |
| `geodesic_elong` | Geod.Elong |

---

### F2. Analyze Regions 3D

```groovy
IJ.run(imp, "Analyze Regions 3D",
    "volume surface_area mean_breadth euler_number inertia_ellipsoid " +
    "ellipsoid_elong1 ellipsoid_elong2")
```

---

### F3. Intensity Measurements 2D/3D

Requires one grayscale image and one label image (same size).

```groovy
IJ.run("Intensity Measurements 2D/3D",
    "input=<GRAY_TITLE> labels=<LABEL_TITLE> mean stddev max min median mode")
```

---

### F4. Label Overlap Measures

Compares two label images pixel-by-pixel.
Use this to validate a segmentation result against a ground truth.

```groovy
IJ.run("Label Overlap Measures",
    "source=<SOURCE_TITLE> target=<TARGET_TITLE> overlap jaccard dice")
```

Available metrics: `overlap` `jaccard` `dice`

Output: ResultsTable with per-label and global statistics including:
Target Overlap, Total Overlap, Jaccard Index, Dice Coefficient,
Volume Similarity, False Negative Error, False Positive Error.

---

### F5. Region Adjacency Graph

```groovy
IJ.run(imp, "Region Adjacency Graph", "")
```

Output: ResultsTable with columns Label1, Label2 for each adjacent label pair.

---

## G. LABEL IMAGE UTILITIES

```groovy
// Change display LUT / shuffle colours
IJ.run(imp, "Set Label Map", "colormap=Golden_angle background=Black shuffle")
IJ.run(imp, "Set Label Map", "colormap=Golden_angle background=White shuffle")

// Map a ResultsTable measurement column back onto label image as pixel values
IJ.run("Assign Measure to Label",
    "results=<TABLE_TITLE> column=<COLUMN_NAME> labels=<LABEL_TITLE>")

// Create binary boundary image (pixels between differently-labelled regions)
IJ.run(imp, "Label Boundaries", "")

// Remove any label touching the image border
IJ.run(imp, "Remove Border Labels", "")

// Replace one label value with another (or with 0 to delete)
IJ.run(imp, "Replace/Remove Label(s)", "label=3 new=0")   // delete label 3
IJ.run(imp, "Replace/Remove Label(s)", "label=3 new=5")   // merge label 3 into 5

// Keep only specified labels; all others become 0
IJ.run(imp, "Select Label(s)", "label=2 label=5 label=8")

// Extract one label into a new cropped image
IJ.run(imp, "Crop Label", "label=3 border=0")

// Remove labels with area below threshold
IJ.run(imp, "Label Size Opening", "min=100")

// Renumber labels 1…N to remove gaps left after deletion
IJ.run(imp, "Remap Labels", "")

// Keep / remove the single largest label
IJ.run(imp, "Keep Largest Label", "")
IJ.run(imp, "Remove Largest Label", "")
```

---

## H. JAVA / GROOVY DIRECT API

For scripting without the GUI, import and call `inra.ijpb` classes directly:

```groovy
import inra.ijpb.binary.BinaryImages
import inra.ijpb.morphology.Morphology
import inra.ijpb.morphology.Strel
import inra.ijpb.morphology.Strel3D
import inra.ijpb.morphology.MinimaAndMaxima
import inra.ijpb.morphology.MinimaAndMaxima3D
import inra.ijpb.watershed.Watershed
import inra.ijpb.label.LabelImages
```

Selected static calls:
```groovy
// Morphological gradient (2D)
def strel = Strel.Shape.DISK.fromRadius(2)
def gradient = Morphology.gradient(imp.getProcessor(), strel)

// Morphological gradient (3D)
def strel3d = Strel3D.Shape.BALL.fromRadius(2)
def gradientStack = Morphology.gradient(imp.getImageStack(), strel3d)

// Extended minima (3D)
def minima = MinimaAndMaxima3D.extendedMinima(gradientStack, 30, 6)

// Connected component labeling (2D, 16-bit output)
def labeled = BinaryImages.componentsLabeling(binaryImp.getProcessor(), 4, 16)

// Connected component labeling (3D, 32-bit output)
def labeled3d = BinaryImages.componentsLabeling(binaryStack, 6, 32)

// Watershed (3D, with dams)
def result = Watershed.computeWatershed(imposedStack, labeledStack, 6, true)

// Get all label values in a label image
def labels = LabelImages.findAllLabels(imp)
int cellCount = labels.length
```

---

## I. KNOWN PITFALLS

1. **Morphological Segmentation timing:** Always add `IJ.wait(1000)` after
   `IJ.run("Morphological Segmentation")` before any `IJ.call()` commands.

2. **Image title spaces:** Wrap in brackets: `"input=[my image] mask=None"`.

3. **Connectivity keyword (`use`):** In Classic Watershed and Marker-controlled
   Watershed, the keyword `"use"` toggles diagonal connectivity (8/26). Omitting
   it uses orthogonal-only connectivity (4/6).

4. **Tolerance scaling:** For Morphological Segmentation, `tolerance=10` suits
   8-bit images. Scale proportionally: ~2000 for 16-bit.

5. **Distance Transform Watershed input must be 8-bit binary:**
   Convert with `IJ.run(imp, "8-bit", "")` + threshold before calling this plugin.

6. **Chamfer Distance Map input must be binary:**
   Pixel values must be 0 (background) and 255 (foreground).

7. **Label image capacity:** Use `type=[16 bits]` (max 65 535 labels) or
   `type=[32 bits]` (max ~16 million) depending on expected object count.
