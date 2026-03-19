---
name: stardists_documentation
description: StarDist is a Fiji/ImageJ plugin for cell and nuclei detection using deep-learning star-convex polygon models. Apply pre-trained or custom models to 2D microscopy images. **2D only** — the Fiji plugin has no 3D stack support. Default models only for NUCLEI in fluorescence or H&E histology images. Custom models must be in CSBDeep `.zip` format and compatible with StarDist 2D. See the full documentation for installation, scripting, parameter tuning, and troubleshooting.Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---

Install via Fiji update sites: **CSBDeep** + **StarDist** + **TensorFlow** (all three required).

---

## Scripting in Groovy — The Only Pattern You Need

StarDist is **not** driven by `IJ.run()` parameter strings.
In Groovy, use the SciJava `command.run()` API with `#@` service injection headers.

### Minimal complete Groovy script

```groovy
#@ CommandService command
#@ UIService uiService

import de.csbdresden.stardist.StarDist2D
import ij.IJ

def imp = IJ.getImage()

def res = command.run(StarDist2D, false,
    "input",               imp,
    "modelChoice",         "Versatile (fluorescent nuclei)",
    "normalizeInput",      true,      // ← boolean, NOT string "true"
    "percentileBottom",    1.0,
    "percentileTop",       99.8,
    "probThresh",          0.5,
    "nmsThresh",           0.4,
    "outputType",          "Both",
    "nTiles",              1,
    "excludeBoundary",     2,
    "roiPosition",         "Automatic",
    "verbose",             false,
    "showCsbdeepProgress", false,
    "showProbAndDist",     false
).get()                              // .get() is REQUIRED — blocks until inference is done

// getOutput("label") returns a SciJava Dataset — must be shown before using as ImagePlus
def labelDataset = res.getOutput("label")
uiService.show(labelDataset)         // register as visible ImagePlus
def labelImp = IJ.getImage()         // now retrieve it
labelImp.setTitle("my-labels")
```

### Count cells after running

```groovy
// From the ROI Manager (requires outputType = "ROI Manager" or "Both"):
import ij.plugin.frame.RoiManager
int cellCount = RoiManager.getInstance().getCount()
IJ.log("Cells: " + cellCount)
```

---

## All Parameters at a Glance

| Parameter | Groovy type | Default | Accepted values |
|-----------|------------|---------|----------------|
| `input` | `ImagePlus` / `Dataset` | — | active image object |
| `modelChoice` | `String` | — | see model table below |
| `modelFile` | `String` | `""` | path to `.zip` or URL (custom model only) |
| `normalizeInput` | `boolean` | `true` | `true` / `false` |
| `percentileBottom` | `double` | `1.0` | 0–100 |
| `percentileTop` | `double` | `99.8` | 0–100 |
| `probThresh` | `double` | `0.5` | 0–1; higher = fewer detections |
| `nmsThresh` | `double` | `0.4` | 0–1; lower = less overlap allowed |
| `outputType` | `String` | — | `"Label Image"` / `"ROI Manager"` / `"Both"` |
| `nTiles` | `int` | `1` | 1, 4, 9, 16 (use square grid values) |
| `excludeBoundary` | `int` | `2` | ≥0 pixels |
| `roiPosition` | `String` | `"Automatic"` | `"Automatic"` / `"Stack"` / `"Hyperstack"` |
| `verbose` | `boolean` | `false` | `true` / `false` |
| `showCsbdeepProgress` | `boolean` | `false` | `true` / `false` |
| `showProbAndDist` | `boolean` | `false` | `true` / `false` |

### Built-in `modelChoice` strings

| String | Best for |
|--------|---------|
| `"Versatile (fluorescent nuclei)"` | Fluorescence DAPI/Hoechst nuclei |
| `"DSB 2018 (from StarDist 2D paper)"` | Alternative fluorescence model |
| `"Versatile (H&E nuclei)"` | Brightfield H&E histology nuclei |
| `"Model (.zip) from File"` | Custom model — set `modelFile` to path |
| `"Model (.zip) from URL"` | Custom model — set `modelFile` to URL |

---

## 5 Critical Pitfalls

### Pitfall 1 — Groovy booleans must be lowercase, not strings
```groovy
// WRONG — string "true" causes a type mismatch; parameter may be silently ignored:
"normalizeInput", "true"

// CORRECT — Groovy boolean:
"normalizeInput", true
```

### Pitfall 2 — `.get()` is required on the command.run() call
```groovy
// WRONG — res is a Future; getOutput() will return null:
def res = command.run(StarDist2D, false, ...).getOutput("label")

// CORRECT — .get() blocks until inference completes:
def res = command.run(StarDist2D, false, ...).get()
def label = res.getOutput("label")
```

### Pitfall 3 — `getOutput("label")` is a Dataset, not an ImagePlus
```groovy
// WRONG — Dataset does not have setTitle(), getProcessor(), etc.:
def labelImp = res.getOutput("label")
labelImp.setTitle("labels")    // ERROR

// CORRECT — show the Dataset first, then get the ImagePlus:
uiService.show(res.getOutput("label"))
def labelImp = IJ.getImage()
labelImp.setTitle("labels")
```

### Pitfall 4 — ROI Manager must be cleared between images in batch
```groovy
// At the start of each image in a loop:
def rm = RoiManager.getInstance() ?: new RoiManager()
rm.reset()
IJ.run("Clear Results", "")
```

### Pitfall 5 — Single channel only
StarDist errors or silently uses the first channel on multi-channel images.
Extract the target channel before running:
```groovy
if (imp.getNChannels() > 1) {
    IJ.run(imp, "Slice Keeper", "first=1 last=1 increment=1")
    imp = IJ.getImage()
}
```

---

## Parameter Tuning Quick Guide

| Observation | Fix |
|-------------|-----|
| Too many small false positives | Raise `probThresh` (e.g. 0.5 → 0.7) |
| Real cells being missed | Lower `probThresh` (e.g. 0.5 → 0.3) |
| Touching nuclei merging into one | Lower `nmsThresh` (e.g. 0.4 → 0.2) |
| Nuclei split into multiple objects | Raise `nmsThresh` (e.g. 0.4 → 0.6) |
| Edge cells missing | Set `excludeBoundary = 0` |
| Out-of-memory crash | Increase `nTiles` (try 4, 9, or 16) |
| Model mismatch for image type | Use `Versatile (H&E nuclei)` for histology |

---

## File Index

| File | Contents |
|------|---------|
| `OVERVIEW.md` | Plugin description, typical inputs and use cases, installation, limitations |
| `UI_GUIDE.md` | GUI reference for the StarDist 2D dialog — all controls explained |
| `UI_WORKFLOW_CELL_SEGMENTATION.md` | **Complete GUI walkthrough**: run → count → measure → compare |
| `SCRIPT_API.md` | All verified scripting commands (Groovy primary, IJ Macro secondary) with full parameter tables |
| `GROOVY_WORKFLOW_CELL_SEGMENTATION.groovy` | **Executable Groovy script**: StarDist → cell count → measurements → optional GT comparison |
| `SKILL.md` | This file — LLM quick-reference card |
