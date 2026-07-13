---
name: morpholibj_documentation
description: MorphoLibJ (IJPB-plugins) is a Fiji/ImageJ library for mathematical morphology — morphological filters, distance transforms, watershed segmentation, connected-components labelling, and 2D/3D region/shape analysis not available in core ImageJ. Read the files listed at the end of this SKILL for commands, parameters, GUI walkthroughs, scripting examples and pitfalls that were VERIFIED against the installed MorphoLibJ 1.6.5 on this system. Use this skill whenever a task involves segmenting touching objects, distance maps, watershed, label-image cleanup/measurement, or morphological filtering.
---

# MorphoLibJ — Quick Reference

> **Documented for: MorphoLibJ v1.6.5** (jar `MorphoLibJ_-1.6.5.jar`) on Fiji / ImageJ
> 2.16.0/1.54p. Every command and parameter below was verified against this exact version.
> If the installed version differs, re-check command/parameter names with the macro recorder.

Menu root: **Plugins ▸ MorphoLibJ**.

## Primary Use Case — Cell / Object Segmentation (touching round objects)

```
Threshold → Chamfer Distance Map → Extended Maxima (seeds)
          → Marker-controlled Watershed → clean up → count → measure
```
Fully scriptable and **popup-free** — see `GROOVY_WORKFLOW_CELL_SEGMENTATION.groovy`
(tested end-to-end) and the GUI walkthrough `UI_WORKFLOW_CELL_SEGMENTATION.md`.
A one-call alternative is **Distance Transform Watershed** (§ below).

---

## ⚠ THE FOUR RULES THAT KEEP SCRIPTS FROM HANGING / GOING WRONG

### Rule 1 — Never pass an empty options string to a plugin that has a dialog
`IJ.run(imp, "Command", "")` makes the dialog **pop up and block, waiting for the user to
click OK**. Always give a complete option string, or use the Java API (`inra.ijpb.*`).
```groovy
IJ.run(labels, "Remove Border Labels", "")                 // ✗ opens a blocking dialog
IJ.run(labels, "Remove Border Labels", "left right top bottom")  // ✓ runs silently
```
Plugins with **no** dialog that accept `""` safely: `Remap Labels`, `Kill Borders`,
`Fill Holes (Binary/Gray)`, `Keep/Remove Largest Label`, `Convexify`.

### Rule 2 — Bracket every multi-word value and every image title with spaces
```groovy
distances=[Borgefors (3,4)]   output=[32 bits]   operation=[White Top Hat]
element=[Horizontal Line]     input=[my image]   colormap=[Golden angle]
```

### Rule 3 — Handle an inverting LUT before thresholding
Images like the Fiji **Blobs** sample have an inverting LUT: objects have HIGH pixel
values but display dark, so a `dark`-background threshold + Convert to Mask comes out
**inverted** and you segment the background. Fix it first:
```groovy
if (imp.getProcessor().isInvertedLut()) IJ.run(imp, "Grays", "")   // normalize, then threshold
```

### Rule 4 — Plugins that take images BY TITLE need those images shown as open windows
`Marker-controlled Watershed`, `Classic Watershed`, `Label Overlap Measures`,
`Intensity Measurements 2D/3D`, `Morphological Reconstruction`, `Impose Min & Max`,
`Geodesic Distance Map` select their inputs by **window title**. Every referenced image
(`input=`, `marker=`, `mask=`, `source=`, `target=`, `image=`) must be an **open, shown
window with that exact title** *before* the call — otherwise the plugin reports
`"<title>" is not a valid choice for "input"` and pops a blocking MessageDialog
(Macro canceled).
```groovy
distInv.setTitle("dist-inv"); distInv.show()      // ← show + title BEFORE referencing it
markers.setTitle("markers");  markers.show()
binary.setTitle("binary");    binary.show()
IJ.run("Marker-controlled Watershed",
    "input=[dist-inv] marker=[markers] mask=[binary] compactness=0 calculate")
```
(Commands that take the active image as their first `IJ.run(imp, …)` argument — Chamfer
Distance Map, Extended Maxima, Connected Components, Analyze Regions, etc. — do not need this.)

---

## Verified Command Quick Reference

### Core segmentation pipeline
| Step | Call |
|------|------|
| Threshold *(std IJ)* | `Prefs.blackBackground=true` ; `IJ.setAutoThreshold(imp,"Otsu dark")` ; `IJ.run(imp,"Convert to Mask","")` |
| Fill holes | `IJ.run(imp,"Fill Holes (Binary/Gray)","")` |
| Chamfer Distance Map | `IJ.run(imp,"Chamfer Distance Map","distances=[Borgefors (3,4)] output=[32 bits] normalize")` *(8-bit binary in)* |
| Extended Maxima (seeds) | `IJ.run(dist,"Extended Min & Max","operation=[Extended Maxima] dynamic=2 connectivity=4")` |
| Label seeds | `IJ.run(maxBin,"Connected Components Labeling","connectivity=4 type=[16 bits]")` |
| Invert dist *(std IJ)* | `IJ.run(dist,"Invert","")` *(reset display range first for 32-bit)* |
| Marker-controlled Watershed | `IJ.run("Marker-controlled Watershed","input=[dist-inv] marker=[seeds] mask=[binary] compactness=0 calculate")` |
| **One-call alternative** | `IJ.run(binary,"Distance Transform Watershed","distances=[Borgefors (3,4)] output=[32 bits] normalize dynamic=1 connectivity=4")` |

### Label cleanup — prefer the Java API (no dialogs, deterministic)
```groovy
import inra.ijpb.label.LabelImages
LabelImages.removeBorderLabels(lbl)            // in place
def kept = LabelImages.sizeOpening(lbl, 50)    // returns new ImagePlus, drops labels < 50 px
LabelImages.remapLabels(kept)                  // renumber 1..N
int n = LabelImages.findAllLabels(kept).length // exact object count
```
IJ.run equivalents (need full options): `Remove Border Labels` → `"left right top bottom"`;
`Label Size Filtering` → `"operation=Greater_Than size=50"` (creates `<t>-sizeFilt`);
`Remap Labels` → `""`.

### Analysis
| Purpose | Call |
|---------|------|
| Shape measurements | `IJ.run(lbl,"Analyze Regions","area perimeter circularity equivalent_ellipse convexity max._feret_diameter geodesic_diameter")` → table `<t>-Morphometry` |
| Intensity per label | `IJ.run("Intensity Measurements 2D/3D","input=[gray] labels=[lbl] mean stddev max min median")` |
| Compare vs ground truth | `IJ.run("Label Overlap Measures","source=[result] target=[gt] overlap jaccard dice volume")` → table `<src>-all-labels-overlap-measurements` |
| Count (Java) | `LabelImages.findAllLabels(lbl).length` |

### Colour / display
```groovy
IJ.run(lbl,"Labels To RGB","colormap=[Golden angle] background=Black shuffle")   // -> <t>-rgb
IJ.run(lbl,"Set Label Map","colormap=[Glasbey] background=Black shuffle")
```

### Other frequently used commands
| Purpose | Call |
|---------|------|
| Morphological gradient | `IJ.run(imp,"Morphological Filters","operation=Gradient element=Disk radius=2")` |
| Opening / closing | `IJ.run(imp,"Morphological Filters","operation=Opening element=Disk radius=3")` |
| Grayscale attribute filter | `IJ.run(imp,"Gray Scale Attribute Filtering","operation=[Opening] attribute=[Area] minimum=100 connectivity=4")` |
| Classic watershed | `IJ.run("Classic Watershed","input=[grad] mask=[None] use min=0 max=255")` |
| Euclidean distance map *(1.6.5)* | `IJ.run(imp,"Euclidean Distance Map","output=[32 bits] normalize")` |
| 3D distance watershed | `IJ.run(imp,"Distance Transform Watershed 3D","distances=[Borgefors (3,4,5)] output=[16 bits] normalize dynamic=2 connectivity=6")` |

---

## 5 Critical Pitfalls (all verified on 1.6.5)

1. **Empty options → blocking dialog.** See Rule 1.
2. **Inverting LUT → inverted mask.** See Rule 3 (Blobs sample, some microscope exports).
3. **`Connected Components Labeling` 32-bit output is `type=float`, NOT `type=[32 bits]`.**
   Accepted values: `[8 bits]`, `[16 bits]`, `float`.
4. **Renamed commands** — use the current names: `Equivalent Ellipse` (was *Inertia Ellipse*),
   `Equivalent Ellipsoid` (was *Inertia Ellipsoid*), `Label Size Filtering` (was *Label Size
   Opening*). The old names survive only under a "_Deprecated" submenu.
5. **Result tables are not the default "Results" table.** Analyze Regions writes to
   `<image>-Morphometry`; Label Overlap to `<source>-all-labels-overlap-measurements`.
   Retrieve by window title (see the workflow script).

Also: distance transforms need **8-bit binary (0/255)** input; `dynamic`/tolerance scales with
intensity (~1–3 on a normalized distance map, ~10 for raw 8-bit, ~2000 for 16-bit);
`Morphological Segmentation`, `Interactive *`, and `Label Edition` are **interactive GUIs —
avoid them in scripts**.

## Connectivity
| Value | Dim | Meaning |
|-------|-----|---------|
| `4` / `8` | 2D | orthogonal / +diagonal |
| `6` / `26` | 3D | 6-face / all-26 |

---

## File Index
| File | Contents |
|------|----------|
| `OVERVIEW.md` | Capabilities, inputs/outputs, installation, 1.4→1.6.5 changes, limitations |
| `GROOVY_API.md` | **Every verified `IJ.run()` command + parameters, plus the `inra.ijpb` Java API** |
| `GROOVY_WORKFLOW_CELL_SEGMENTATION.groovy` | **Tested, popup-free** segmentation script (count + measure + optional GT) |
| `UI_GUIDE.md` | Menu-by-menu GUI reference for all plugin groups |
| `UI_WORKFLOW_CELL_SEGMENTATION.md` | Click-by-click GUI walkthrough of the segmentation pipeline |
| `SKILL.md` | This quick-reference card |
