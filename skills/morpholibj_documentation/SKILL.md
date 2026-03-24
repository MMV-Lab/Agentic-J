---
name: morpholibj_documentation
description: MorphoLibJ is a Fiji/ImageJ plugin for mathematical morphology. It adds morphological filtering, watershed segmentation, and quantitative region analysis not available in core ImageJ. Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---

## Primary Use Case in This Skill Set
**Cell segmentation via distance-transform watershed** — the four-step pipeline:

```
Binary mask  →  Chamfer Distance Map  →  Regional Maxima  →  Marker-controlled Watershed
```

Each step uses a separate, verified MorphoLibJ command. This pipeline is fully scriptable
(see `GROOVY_WORKFLOW_CELL_SEGMENTATION.groovy`) and has a GUI walkthrough
(see `UI_WORKFLOW_CELL_SEGMENTATION.md`).

---

## Verified Command Quick Reference

> **These are the only commands confirmed from the official manual and source code.**
> Do not invent variant names; use macro recording for new commands.

### Core Pipeline Commands

| Step | IJ.run() command string | Notes |
|------|------------------------|-------|
| Threshold (Standard IJ) | `IJ.setAutoThreshold(imp, "Default dark")` then `IJ.run(imp, "Convert to Mask", "")` | Standard ImageJ; not MorphoLibJ |
| Chamfer Distance Map | `"Chamfer Distance Map", "distances=[Borgefors (3,4)] output=[32 bits] normalize"` | Input must be 8-bit binary |
| Regional Maxima | `"Regional Min & Max", "operation=[Regional Maxima] connectivity=4"` | Output: binary image |
| Connected Components | `"Connected Components Labeling", "connectivity=4 type=[16 bits]"` | Labels the maxima as seeds |
| Invert (Standard IJ) | `IJ.run(distImp, "Invert", "")` | Converts distance map to watershed landscape; standard ImageJ |
| Marker-controlled Watershed | `"Marker-controlled Watershed", "input=[dist-inv] marker=[maxima-lbl] mask=[binary] calculate"` | `calculate` = include dams; omit `use` for 4-connectivity |
| One-step alternative | `"Distance Transform Watershed", "distances=[Borgefors (3,4)] output=[32 bits] normalize dynamic=1.00 connectivity=4"` | Combines steps 2–4 in one call; input must be 8-bit binary |

### Post-processing Commands

| Purpose | Command |
|---------|---------|
| Remove border objects | `IJ.run(imp, "Remove Border Labels", "")` |
| Remove small objects | `IJ.run(imp, "Label Size Opening", "min=50")` |
| Renumber labels 1…N | `IJ.run(imp, "Remap Labels", "")` |

### Analysis Commands

| Purpose | Command |
|---------|---------|
| Count cells (Groovy) | `LabelImages.findAllLabels(imp).length` — import inra.ijpb.label.LabelImages |
| Measure shape | `IJ.run(imp, "Analyze Regions", "area perimeter circularity inertia_ellipse convexity max_feret")` |
| Compare vs ground truth | `IJ.run("Label Overlap Measures", "source=[result] target=[gt] overlap jaccard dice")` |
| Intensity stats per cell | `IJ.run("Intensity Measurements 2D/3D", "input=[gray] labels=[lbl] mean stddev max min")` |

### Other Frequently Used Commands

| Purpose | Command |
|---------|---------|
| Morphological gradient | `IJ.run(imp, "Morphological Filters", "operation=Gradient element=Disk radius=2")` |
| Morphological opening | `IJ.run(imp, "Morphological Filters", "operation=Opening element=Disk radius=3")` |
| Classic watershed | `IJ.run(imp, "Classic Watershed", "input=<T> mask=None use min=0 max=255")` |
| Morphological segmentation | `IJ.run("Morphological Segmentation")` + `IJ.wait(1000)` + `IJ.call(...)` — see GROOVY_API.md §D3 |
| Kill borders | `IJ.run(imp, "Kill Borders", "")` |
| Fill holes | `IJ.run(imp, "Fill Holes (Binary/Gray)", "")` |
| Attribute size filter | `IJ.run(imp, "Grayscale Attribute Filtering", "operation=Opening attribute=Area minimum=100 connectivity=4")` |
| Region adjacency graph | `IJ.run(imp, "Region Adjacency Graph", "")` |
| 3D distance watershed | `IJ.run(imp, "Distance Transform Watershed 3D", "distances=[Borgefors (3,4,5)] output=[16 bits] normalize dynamic=2.00 connectivity=6")` |

---

## 3 Critical Pitfalls

### Pitfall 1 — Morphological Segmentation requires `IJ.wait(1000)`
```groovy
IJ.run("Morphological Segmentation")
IJ.wait(1000)   // ← mandatory; GUI must load before IJ.call() works
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "setInputImageType", "object")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "segment",
    "tolerance=10", "calculateDams=true", "connectivity=4")
IJ.call("inra.ijpb.plugins.MorphologicalSegmentation", "createResultImage")
```

### Pitfall 2 — Image titles with spaces must be wrapped in brackets
```groovy
// Wrong:
IJ.run("Marker-controlled Watershed",
    "input=my image marker=my markers mask=None calculate")

// Correct:
IJ.run("Marker-controlled Watershed",
    "input=[my image] marker=[my markers] mask=None calculate")
```

### Pitfall 3 — Distance transform inputs must be 8-bit binary
Both `Chamfer Distance Map` and `Distance Transform Watershed` require:
- 8-bit image type
- Pixel values of exactly 0 (background) and 255 (foreground)

Convert before using:
```groovy
IJ.run(imp, "8-bit", "")
IJ.setAutoThreshold(imp, "Default dark")
IJ.run(imp, "Convert to Mask", "")
```

---

## Connectivity Guide

| Value | 2D meaning | 3D meaning | Object shape effect |
|-------|-----------|-----------|-------------------|
| `4` | orthogonal neighbours only | — | rounder, more conservative |
| `8` | orthogonal + diagonal | — | includes diagonal connections |
| `6` | — | face-adjacent (6 faces) | tighter 3D |
| `26` | — | all 26 neighbours | full 3D diagonal |

---

## File Index

| File | Contents |
|------|---------|
| `OVERVIEW.md` | Plugin capabilities, typical inputs, use cases, installation, limitations |
| `UI_GUIDE.md` | Step-by-step GUI reference for all 19 plugin groups |
| `UI_WORKFLOW_CELL_SEGMENTATION.md` | **Complete GUI walkthrough**: threshold → distance map → maxima → watershed → count → compare |
| `GROOVY_API.md` | Every verified `IJ.run()` command with parameter tables and pitfalls |
| `GROOVY_WORKFLOW_CELL_SEGMENTATION.groovy` | **Executable script**: full 4-step pipeline with cell counting and optional GT comparison |
| `SKILL.md` | This file — LLM quick-reference card |
