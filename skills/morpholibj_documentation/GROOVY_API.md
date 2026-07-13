# MorphoLibJ — GROOVY / MACRO API REFERENCE (v1.6.5)

Every command name and parameter in this file was **verified against the installed
MorphoLibJ 1.6.5 JAR** (`MorphoLibJ_-1.6.5.jar`): command names come from the plugin's
`plugins.config`; dialog parameter keys, choice values and enum labels were extracted
from the compiled classes and confirmed by executing each command on a live Fiji
(ImageJ 2.16.0 / 1.54p) through `ij.py.run_script`.

Commands marked **[Standard ImageJ]** are built into Fiji and are not part of MorphoLibJ.

---

## 0. THE #1 RULE — NEVER PASS AN EMPTY OPTIONS STRING

> When you call any MorphoLibJ plugin that has a dialog via `IJ.run(imp, "Command", "<options>")`,
> **always supply a complete, non-empty options string.**
>
> Passing `""` (empty) makes the plugin's GenericDialog **pop up on screen and block,
> waiting for the user to click OK.** In a scripted/agent workflow this is a hang.

```groovy
// WRONG — opens a Left/Right/Top/Bottom dialog and waits for the user:
IJ.run(labels, "Remove Border Labels", "")

// CORRECT — fully specified, runs silently:
IJ.run(labels, "Remove Border Labels", "left right top bottom")
```

Verified behaviour (1.6.5): an empty string pops the dialog for *Remove Border Labels*,
*Analyze Regions*, *Label Size Filtering*, *Label Overlap Measures*, and every other
plugin that declares a dialog. A handful of plugins have **no** dialog (*Remap Labels*,
*Kill Borders*, *Fill Holes (Binary/Gray)*) and accept `""` safely — but when unsure,
either supply full options or use the **Java API** (§J), which never shows a dialog.

Other rules:
1. All non-interactive plugins are macro-recordable (**Plugins ▸ Macros ▸ Record…**).
2. Parameter strings are space-separated `key=value` pairs.
3. **Multi-word values and image titles with spaces MUST be bracketed:**
   `distances=[Borgefors (3,4)]`, `operation=[White Top Hat]`, `input=[my image]`.
4. Boolean flags are presence/absence keywords in `IJ.run()` (`normalize`, `calculate`,
   `use`, `shuffle`); in `IJ.call()` use the strings `"true"`/`"false"`.
5. **Avoid interactive-only plugins in scripts** (§D6): *Morphological Segmentation*,
   *Interactive Marker-controlled Watershed*, *Interactive Morphological Reconstruction*,
   *Label Edition*, *Interactive Geodesic Distance Map*. They open a persistent GUI.

---

## A. MORPHOLOGICAL FILTERS

### A1. Morphological Filters (2D)

```groovy
IJ.run(imp, "Morphological Filters", "operation=[<OP>] element=[<ELEM>] radius=<R>")
```

| Parameter | Verified accepted values |
|-----------|--------------------------|
| operation | `Erosion` `Dilation` `Opening` `Closing` `White Top Hat` `Black Top Hat` `Gradient` `Laplacian` `Internal Gradient` `External Gradient` |
| element   | `Disk` `Square` `Diamond` `Octagon` `Horizontal Line` `Vertical Line` `Line 45 degrees` `Line 135 degrees` |
| radius    | integer ≥ 1 (label is "Radius (in pixels)") |

> ⚠ Multi-word operations/elements need brackets: `operation=[White Top Hat]`,
> `element=[Horizontal Line]`. There is **no** plain `Line` element — use a directional
> line shape. (The old skill's `element=Line` and unbracketed `White Top Hat` were wrong.)

```groovy
IJ.run(imp, "Morphological Filters", "operation=Erosion element=Disk radius=2")
IJ.run(imp, "Morphological Filters", "operation=Opening element=Disk radius=3")
IJ.run(imp, "Morphological Filters", "operation=[White Top Hat] element=Disk radius=10")
IJ.run(imp, "Morphological Filters", "operation=Gradient element=Disk radius=2")
IJ.run(imp, "Morphological Filters", "operation=Closing element=Square radius=4")
```
Output: a new image window `<title>-<Operation>`, same type as input.

### A2. Morphological Filters (3D)

```groovy
IJ.run(imp, "Morphological Filters (3D)", "operation=[Closing] element=[Ball] radius=2")
```
2D operations plus 3D elements: `Ball` `Cube` `Square` `Diamond` `Octagon`
`Horizontal Line` `Vertical Line` `Z-Line` `Line 45 degrees` `Line 135 degrees`.

### A3. Binary Morphological Filters (2D / 3D)  *(new in 1.6.5)*

Distance-transform-based binary filters — faster on binary masks than the grayscale ones.
```groovy
IJ.run(imp, "Binary Morphological Filters", "operation=[Closing] radius=3")
IJ.run(imp, "Binary Morphological Filters 3D", "operation=[Opening] radius=2")
```

### A4. Directional Filtering

For thin curvilinear structures (vessels, fibres, cell walls).
```groovy
IJ.run(imp, "Directional Filtering", "type=[Max] operation=[Opening] line=25 direction=32")
```
| Parameter | Values |
|-----------|--------|
| type | `Max` `Min` |
| operation | `Erosion` `Dilation` `Opening` `Closing` `Median` |
| line | line length in pixels (integer) |
| direction | number of orientations (e.g. `32`) |

---

## B. MORPHOLOGICAL RECONSTRUCTION & ATTRIBUTE FILTERING

### B1. Morphological Reconstruction (two images)
```groovy
IJ.run("Morphological Reconstruction",
    "marker=[<MARKER>] mask=[<MASK>] type=[By Dilation] connectivity=4")
```
`type` = `[By Dilation]` or `[By Erosion]`; `connectivity` = `4`/`8` (2D), `6`/`26` (3D).
3D variant: `"Morphological Reconstruction 3D"`.

### B2. Kill Borders — *no dialog, `""` is safe*
```groovy
IJ.run(imp, "Kill Borders", "")     // removes objects/regions touching the border
```

### B3. Fill Holes (Binary/Gray) — *no dialog, `""` is safe*
```groovy
IJ.run(imp, "Fill Holes (Binary/Gray)", "")
```

### B4. Gray Scale Attribute Filtering (2D)
```groovy
IJ.run(imp, "Gray Scale Attribute Filtering",
    "operation=[Opening] attribute=[Area] minimum=100 connectivity=4")
```
| Parameter | Values |
|-----------|--------|
| operation | `Opening` `Closing` `White Top Hat` `Black Top Hat` (bracket multi-word) |
| attribute | `Area` `Box Diagonal` |
| minimum   | integer (label "Minimum Value", in pixels) |
| connectivity | `4` `8` |

3D variant: `"Gray Scale Attribute Filtering 3D"` with `attribute=[Volume]`.

---

## C. MINIMA AND MAXIMA

### C1. Regional Min & Max (2D) — binary output (255 at extrema)
```groovy
IJ.run(imp, "Regional Min & Max", "operation=[Regional Maxima] connectivity=4")
IJ.run(imp, "Regional Min & Max", "operation=[Regional Minima] connectivity=8")
```
`operation` = `[Regional Maxima]` / `[Regional Minima]`; `connectivity` = `4`/`8`.

### C2. Extended Min & Max (2D) — tolerance-based, less noise-sensitive
```groovy
IJ.run(imp, "Extended Min & Max", "operation=[Extended Maxima] dynamic=10 connectivity=4")
IJ.run(imp, "Extended Min & Max", "operation=[Extended Minima] dynamic=10 connectivity=4")
```
`dynamic` = tolerance (higher → fewer, larger extrema). Scale to bit depth:
~`1`–`3` for a normalized distance map, ~`10` for raw 8-bit, ~`2000` for 16-bit.

### C3. Impose Min & Max (2D)
```groovy
IJ.run("Impose Min & Max", "image=[<INPUT>] marker=[<MARKER>] operation=[Impose Minima]")
```
`operation` = `[Impose Minima]` / `[Impose Maxima]`.

### C4. 3D variants
```groovy
IJ.run(imp, "Regional Min & Max 3D",  "operation=[Regional Maxima] connectivity=6")
IJ.run(imp, "Extended Min & Max 3D",  "operation=[Extended Maxima] dynamic=30 connectivity=6")
IJ.run("Impose Min & Max 3D", "image=[<INPUT>] marker=[<MARKER>] operation=[Impose Minima]")
```

---

## D. SEGMENTATION

### D1. Classic Watershed  *(class Watershed3DPlugin — handles 2D and 3D)*
```groovy
IJ.run("Classic Watershed", "input=[<INPUT>] mask=[None] use min=0 max=255")
```
| Parameter | Notes |
|-----------|-------|
| input | grayscale image title to flood (a gradient image works well) |
| mask  | binary mask title, or `None` for the whole image |
| use   | presence = diagonal connectivity (8/26); absence = orthogonal (4/6) |
| min / max | flooding levels (labels "Min h" / "Max h") |

Output: a labeled image `<input>-watershed` (basins = integer labels, dams = 0).

### D2. Marker-controlled Watershed  *(class MarkerControlledWatershed3DPlugin)*
```groovy
// dams + 4-connectivity (omit "use"):
IJ.run("Marker-controlled Watershed",
    "input=[<INPUT>] marker=[<MARKERS>] mask=[<MASK>] compactness=0 calculate")
// dams + 8-connectivity:
IJ.run("Marker-controlled Watershed",
    "input=[<INPUT>] marker=[<MARKERS>] mask=[<MASK>] compactness=0 calculate use")
```
| Parameter | Notes |
|-----------|-------|
| input  | landscape image title (gradient, or **inverted** distance map) |
| marker | labeled seed image (one integer label per object) |
| mask   | binary mask title, or `None` |
| compactness | `0` = standard watershed; `>0` = compact/protected watershed (new since 1.5.0) |
| binary | flag: treat the marker image as binary instead of labeled |
| calculate | flag: include watershed lines / dams (0-valued boundaries) |
| use    | flag: diagonal connectivity (8/26) |

> ⚠ **Inputs are selected by window title** — `input`, `marker` and `mask` must each be an
> **open, shown window** whose title exactly matches the bracketed value *before* this call.
> If an image isn't shown (e.g. a freshly created/duplicated/inverted image you haven't
> `.show()`n, or whose title you changed after showing), the plugin reports
> `"<title>" is not a valid choice for "input"` and pops a **blocking MessageDialog
> (Macro canceled)**. Always `setTitle(...)` then `show()` the input/marker/mask first.
> Also: `marker` must contain ≥1 non-zero label, and input/marker/mask must share dimensions.

### D3. Distance Transform Watershed (2D, one step)

Combines Chamfer distance map + watershed. **Input must be an 8-bit binary image (0/255).**
```groovy
IJ.run(imp, "Distance Transform Watershed",
    "distances=[Borgefors (3,4)] output=[32 bits] normalize dynamic=1 connectivity=4")
```
| Parameter | Verified values |
|-----------|-----------------|
| distances | `[Chessboard (1,1)]` `[City-Block (1,2)]` `[Quasi-Euclidean (1,1.41)]` `[Borgefors (3,4)]` `[Chessknight (5,7,11)]` `[Verwer (12,17,27,38)]` |
| output    | `[16 bits]` `[32 bits]` |
| normalize | flag — divide weights by the first weight |
| dynamic   | float; higher → more merges (fewer segments) |
| connectivity | `4` `8` |

> There is no `[Weights (2,3)]` mask — that value from the old skill does not exist.

### D4. Distance Transform Watershed 3D
```groovy
IJ.run(imp, "Distance Transform Watershed 3D",
    "distances=[Borgefors (3,4,5)] output=[16 bits] normalize dynamic=2 connectivity=6")
```
3D distance masks: `[Chessboard (1,1,1)]` `[City-Block (1,2,3)]`
`[Quasi-Euclidean (1,1.41,1.73)]` `[Borgefors (3,4,5)]` `[Svensson <3,4,5,7>]` (+ larger masks).

### D5. Euclidean Distance Map  *(new in 1.6.5)*
```groovy
IJ.run(imp, "Euclidean Distance Map", "output=[32 bits] normalize")   // 2D
```
Exact Saito–Toriwaki Euclidean distance; alternative to the Chamfer approximation.

### D6. Interactive / GUI plugins — DO NOT use in scripted (no-popup) workflows
- **Morphological Segmentation** — opens a persistent GUI panel; driven by `IJ.call()`
  (see §K). Not headless-safe and leaves a window open. Prefer Distance Transform Watershed
  or the marker-controlled pipeline instead.
- **Interactive Marker-controlled Watershed**, **Interactive Morphological Reconstruction
  (3D)**, **Interactive Geodesic Distance Map**, **Label Edition** — all require mouse input.

---

## E. BINARY IMAGE OPERATIONS

### E1. Connected Components Labeling
```groovy
IJ.run(imp, "Connected Components Labeling", "connectivity=4 type=[16 bits]")
```
| Parameter | Verified values |
|-----------|-----------------|
| connectivity | `4` `8` (2D); `6` `26` (3D) |
| type | `[8 bits]` (≤255 labels) · `[16 bits]` (≤65 535) · `float` (≈16 M) |

> ⚠ For 32-bit output the value is **`type=float`, not `type=[32 bits]`**
> (the old skill was wrong here). On overflow the plugin errors with
> "Try with larger data type".

### E2. Chamfer Distance Map (2D) — input must be 8-bit binary (0/255)
```groovy
IJ.run(imp, "Chamfer Distance Map", "distances=[Borgefors (3,4)] output=[32 bits] normalize")
```
`distances` values: same 2D list as §D3. `output` = `[16 bits]`/`[32 bits]`. `normalize` flag.

### E3. Chamfer Distance Map 3D
```groovy
IJ.run(imp, "Chamfer Distance Map 3D", "distances=[Borgefors (3,4,5)] output=[32 bits] normalize")
```

### E4. Geodesic Distance Map
```groovy
IJ.run("Geodesic Distance Map",
    "marker=[<MARKER>] mask=[<MASK>] distances=[Borgefors (3,4)] output=[32 bits] normalize")
```

### E5. Binary size/shape utilities
```groovy
IJ.run(imp, "Keep Largest Region", "")       // no dialog
IJ.run(imp, "Remove Largest Region", "")      // no dialog
IJ.run(imp, "Size Opening 2D/3D", "min=100")  // remove components < 100 px/voxels
IJ.run(imp, "Area Opening", "pixel=100")      // 2D area opening (new in 1.6.5)
IJ.run(imp, "Convexify", "")                  // per-component convex hull (new in 1.6.x)
```

---

## F. REGION & INTENSITY ANALYSIS

### F1. Analyze Regions (2D)

Input: a label image (or binary, treated as one region). **Verified feature keywords**
(each toggles one or more result columns):

```groovy
IJ.run(labels, "Analyze Regions",
    "pixel_count area perimeter circularity euler_number bounding_box centroid " +
    "equivalent_ellipse ellipse_elong. convexity max._feret_diameter oriented_box " +
    "oriented_box_elong. geodesic_diameter tortuosity max._inscribed_disc " +
    "geodesic_elong. average_thickness")
```

| Keyword | Result columns |
|---------|----------------|
| `pixel_count` | PixelCount |
| `area` | Area |
| `perimeter` | Perimeter (Crofton) |
| `circularity` | Circularity = 4π·Area/Perimeter² |
| `euler_number` | EulerNumber |
| `bounding_box` | Box.X.Min/Max, Box.Y.Min/Max |
| `centroid` | Centroid.X/Y |
| `equivalent_ellipse` | Ellipse.Center.X/Y, Radius1, Radius2, Orientation *(was "Inertia Ellipse" before 1.4.2)* |
| `ellipse_elong.` | Ellipse.Elong *(note the trailing period in the keyword)* |
| `convexity` | ConvexArea, Convexity |
| `max._feret_diameter` | MaxFeretDiam, MaxFeretDiamAngle |
| `oriented_box` | OBox.Center.X/Y, OBox.Length, OBox.Width, OBox.Orientation |
| `oriented_box_elong.` | OBox.Elong |
| `geodesic_diameter` | GeodesicDiameter |
| `tortuosity` | Tortuosity |
| `max._inscribed_disc` | InscrDisc.Center.X/Y, InscrDisc.Radius |
| `geodesic_elong.` | GeodesicElongation |
| `average_thickness` | AverageThickness *(new in 1.4.2)* |

> Results go to a table titled **`<image>-Morphometry`**, *not* the default "Results"
> table. Retrieve it by title (see §F4 and the workflow script).

Individual measurements are also exposed as separate Analyze-menu commands:
`Bounding Box`, `Equivalent Ellipse`, `Max. Feret Diameters`, `Oriented Bounding Box`,
`Max. Inscribed Circle`, `Geodesic Diameter`, `Average Thickness`, `Skeleton Geodesic Diameter`.

### F2. Analyze Regions 3D
```groovy
IJ.run(labels, "Analyze Regions 3D",
    "volume surface_area mean_breadth sphericity euler_number equivalent_ellipsoid " +
    "ellipsoid_elongations max._inscribed_ball")
```
Produces Volume, SurfaceArea, MeanBreadth, Sphericity, EulerNumber, the equivalent
ellipsoid (centre, 3 radii, 3 orientation angles), and (since 1.6.5) Max Feret / Geodesic
diameter. *("Inertia Ellipsoid" → "Equivalent Ellipsoid" since 1.4.1.)*

### F3. Intensity Measurements 2D/3D
```groovy
IJ.run("Intensity Measurements 2D/3D",
    "input=[<GRAY>] labels=[<LABELS>] mean stddev max min median mode")
```
Also: `numberofvoxels`, `volume`, `skewness`, `kurtosis`, `centerofmass` (new in 1.6.5).
Both images must have the same dimensions.

### F4. Label Overlap Measures — validate a result against a ground truth
```groovy
IJ.run("Label Overlap Measures",
    "source=[<RESULT>] target=[<GROUND_TRUTH>] overlap jaccard dice volume")
```
Dialog checkboxes: `Overlap`, `Jaccard index`, `Dice coefficient`, `Volume Similarity`,
`False Negative Error`, `False Positive Error`. Verified keyword tokens `overlap jaccard
dice volume` produce the global table **`<source>-all-labels-overlap-measurements`** with
columns TotalOverlap, JaccardIndex, DiceCoefficient, VolumeSimilarity (1.0 = perfect).
A per-label table `<source>-individual-labels-overlap-measurements` is also created.

### F5. Microstructure / adjacency
```groovy
IJ.run(imp, "Microstructure Analysis", "area_density perimeter_density connectivity=4")
IJ.run(labels, "Region Adjacency Graph", "show")  // table of adjacent Label1/Label2 pairs; NOT "" (would pop a dialog)
```

---

## G. LABEL IMAGE UTILITIES

```groovy
// --- Display / colour ---
IJ.run(labels, "Set Label Map", "colormap=[Golden angle] background=Black shuffle")
IJ.run(labels, "Labels To RGB", "colormap=[Golden angle] background=White shuffle") // -> <t>-rgb
// colormap values: Grays | Fire | Glasbey | Glasbey (Dark) | Glasbey (Bright) |
//   Golden angle | Ice | Spectrum | Jet | RGB 3-3-2 | Main Colors | Mixed Colors | Red-Green
// background values: Black | White

// --- Cleanup (verified) ---
IJ.run(labels, "Remove Border Labels", "left right top bottom")  // 3D adds: front back
IJ.run(labels, "Label Size Filtering", "operation=Greater_Than size=50") // -> <t>-sizeFilt
//   operation: Greater_Than | Lower_Than | Greater_Than_Or_Equal |
//              Lower_Than_Or_Equal | Equal | Not_Equal   (size in pixels/voxels)
IJ.run(labels, "Remap Labels", "")            // no dialog — renumber 1..N
IJ.run(labels, "Keep Largest Label", "")      // no dialog
IJ.run(labels, "Remove Largest Label", "")    // no dialog

// --- Edit ---
IJ.run(labels, "Replace/Remove Label(s)", "label(s)=3 final=0")  // delete label 3 (final= new value)
IJ.run(labels, "Select Label(s)", "label(s)=2,5,8")             // keep only these
IJ.run(labels, "Crop Label", "label=3 border=2")
IJ.run(labels, "Expand Labels", "factor=20")                    // new in 1.4.x
IJ.run(labels, "Fill Label Holes", "connectivity=4 type=[16 bits]")  // 1.6.0 — NOT "" (would pop a dialog)
// Merge Label(s): merges the labels under the current point/area SELECTION (interactive),
//   gap = [No Gap|Orthogonal|Diagonal]. For unattended scripts merge via Replace/Remove instead:
//   IJ.run(labels, "Replace/Remove Label(s)", "label(s)=3 final=2")   // relabel 3 -> 2

// --- Convert ---
IJ.run(labels, "Label Boundaries", "")        // binary boundary image (no dialog)
IJ.run(labels, "Label Map to ROIs",           // 1.6.3 — sends region outlines to the ROI Manager
    "connectivity=C4 vertex=[Pixel_Centers] name=Label")  // connectivity=C4/C8; vertex=Corners/Edge_Middles/Pixel_Centers
IJ.run(labels, "Assign Measure to Label", "results=[<TABLE>] column=[Area]")
```

> **Output windows.** `Remove Border Labels` and `Label Size Filtering` create a **new
> image** (`-killBorders`, `-sizeFilt`) and do **not** make it the active image, so
> `WindowManager.getCurrentImage()` returns the *input*. Grab the result by title
> (`WindowManager.getImage(title + "-sizeFilt")`) or, more robustly, use the Java API (§J).

---

## H. UTILITIES

```groovy
IJ.run(imp, "Extend Image Borders", "left=10 right=10 top=10 bottom=10 fill=0")
IJ.run(imp, "Binarize Image", "")              // foreground = any non-zero pixel (new 1.6.5)
IJ.run("Binary Overlay", "reference=[<GRAY>] binary=[<MASK>] ...")
```

---

## J. JAVA / GROOVY DIRECT API  (no dialogs, fully headless-safe)

For robust scripts, call the `inra.ijpb` classes directly. These never pop a dialog and
return/modify concrete objects — the recommended approach for the cleanup/counting steps.

```groovy
import inra.ijpb.binary.BinaryImages
import inra.ijpb.label.LabelImages
import inra.ijpb.morphology.Morphology
import inra.ijpb.morphology.Strel
import inra.ijpb.morphology.MinimaAndMaxima
import inra.ijpb.binary.distmap.ChamferMask2D

// Morphological gradient (2D)
def strel    = Strel.Shape.DISK.fromRadius(2)
def gradIp   = Morphology.gradient(imp.getProcessor(), strel)

// Connected-components labelling (2D, conn=4, 16-bit) -> ImagePlus
def labeled  = BinaryImages.componentsLabeling(binaryImp, 4, 16)

// Chamfer distance map (ImageProcessor in, normalized float out)
def distIp   = BinaryImages.distanceMap(binaryImp.getProcessor(),
                   ChamferMask2D.BORGEFORS, true, false)

// Label cleanup — all verified:
LabelImages.removeBorderLabels(labelImp)          // in place
def opened = LabelImages.sizeOpening(labelImp, 50) // returns new ImagePlus (labels < 50 px removed)
LabelImages.remapLabels(opened)                   // in place
int n = LabelImages.findAllLabels(opened).length  // exact object count
def keep   = LabelImages.keepLargestLabel(labelImp)
```

| Need | Static call |
|------|-------------|
| Count objects | `LabelImages.findAllLabels(imp).length` |
| Remove small labels | `LabelImages.sizeOpening(imp, minPixels)` → new ImagePlus |
| Remove border labels | `LabelImages.removeBorderLabels(imp)` (void, in place) |
| Renumber 1…N | `LabelImages.remapLabels(imp)` (void, in place) |
| Keep / remove largest | `LabelImages.keepLargestLabel(imp)` / `removeLargestLabel(imp)` |
| Components labelling | `BinaryImages.componentsLabeling(imp, conn, bitDepth)` |
| Distance map | `BinaryImages.distanceMap(ip, ChamferMask2D.BORGEFORS, normalize, false)` |
| Keep largest region | `BinaryImages.keepLargestRegion(imp)` |

---

## K. MORPHOLOGICAL SEGMENTATION (interactive — avoid in no-popup scripts)

This plugin opens an interactive GUI panel. It can be driven by `IJ.call()` but it is
**not** headless-safe and leaves a window open, so prefer §D3 for scripts. If you must:

```groovy
IJ.run("Morphological Segmentation")
IJ.wait(1500)   // mandatory: let the GUI initialise before calling methods
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setInputImageType", "object")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "segment",
        "tolerance=10", "calculateDams=true", "connectivity=4")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setDisplayFormat", "Catchment basins")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "createResultImage")
```
`tolerance` is intensity-scaled (~10 for 8-bit, ~2000 for 16-bit).

---

## L. CONNECTIVITY QUICK REFERENCE

| Value | Dim | Meaning | Effect |
|-------|-----|---------|--------|
| `4`  | 2D | orthogonal neighbours | rounder, more conservative objects |
| `8`  | 2D | + diagonals | merges diagonally touching pixels |
| `6`  | 3D | 6 face neighbours | tighter 3D |
| `26` | 3D | all 26 neighbours | full 3D diagonal |

---

## M. CITATION

Legland, D., Arganda-Carreras, I., & Andrey, P. (2016). *MorphoLibJ: integrated library
and plugins for mathematical morphology with ImageJ.* Bioinformatics 32(22):3532–3534.
DOI: 10.1093/bioinformatics/btw413 · Docs: https://imagej.net/plugins/morpholibj ·
Source: https://github.com/ijpb/MorphoLibJ · JavaDoc: https://ijpb.github.io/MorphoLibJ/javadoc/
