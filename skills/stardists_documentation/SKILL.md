---
name: stardists_documentation
description: StarDist is a Fiji/ImageJ plugin for cell and nuclei detection using deep-learning star-convex polygon models. Apply pre-trained or custom models to 2D microscopy images. **2D only** — the Fiji plugin has no 3D stack support. Default models only for NUCLEI in fluorescence or H&E histology images. Custom models must be in CSBDeep `.zip` format and compatible with StarDist 2D. See the full documentation for installation, scripting, parameter tuning, and troubleshooting.Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. RGB only for H&E model.
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

// Dynamic nTiles calculation to prevent OOM on large images
// Formula: max(1, ceil(W*H / 10^7))
long w = imp.getWidth()
long h = imp.getHeight()
int calculatedTiles = (int) Math.max(1, Math.ceil((w * h) / 10000000.0))

def res = command.run(StarDist2D, false,
    "input",               imp,
    "modelChoice",         "Versatile (fluorescent nuclei)",
    "normalizeInput",      true,      // ← boolean, NOT string "true"
    "percentileBottom",    1.0,
    "percentileTop",       99.8,
    "probThresh",          0.5,
    "nmsThresh",           0.4,
    "outputType",          "Both",
    "nTiles",              calculatedTiles, // Dynamic tiling
    "excludeBoundary",     2,
    "roiPosition",         "Automatic",
    "verbose",             false,
    "showCsbdeepProgress", false,
    "showProbAndDist",     false
).get()                         // .get() is REQUIRED — blocks until inference is done

// getOutput("label") returns a SciJava Dataset — must be shown before using as ImagePlus
def labelDataset = res.getOutput("label")
uiService.show(labelDataset)         // register as visible ImagePlus
def labelImp = IJ.getImage()         // now retrieve it
labelImp.setTitle("my-labels")
```

### H&E histology — use the H&E model directly on the RGB image

**DO NOT** preprocess H&E with Color Deconvolution → take the haematoxylin
channel → run `Versatile (fluorescent nuclei)`. This is a common mistake but
it is wrong for two reasons:
1. The H&E model `Versatile (H&E nuclei)` was trained directly on raw RGB H&E
   patches; feeding it a deconvolved single channel (or feeding the fluorescence
   model H&E data) gives noticeably worse segmentation.
2. Color Deconvolution depends on the chosen vector matrix and is fragile across
   scanners. The H&E model is robust to staining variation.

The correct H&E pipeline is one step:

```groovy
#@ CommandService command
#@ UIService uiService

import de.csbdresden.stardist.StarDist2D
import ij.IJ

def imp = IJ.openImage("/path/to/he_slide.tif")
imp.show()

// H&E model expects RGB. Do NOT convert to 8-bit, do NOT split channels,
// do NOT run Color Deconvolution. If your image is not RGB, fix that upstream.
assert imp.getType() == ij.ImagePlus.COLOR_RGB :
       "Versatile (H&E nuclei) requires an RGB image"

def res = command.run(StarDist2D, false,
    "input",               imp,
    "modelChoice",         "Versatile (H&E nuclei)",
    "normalizeInput",      true,
    "percentileBottom",    1.0,
    "percentileTop",       99.8,
    "probThresh",          0.692,     // model default for H&E
    "nmsThresh",           0.3,       // model default for H&E
    "outputType",          "Both",
    "nTiles",              1,         // raise to 4/9/16 if OOM on large slides
    "excludeBoundary",     2,
    "roiPosition",         "Automatic",
    "verbose",             false,
    "showCsbdeepProgress", false,
    "showProbAndDist",     false
).get()

uiService.show(res.getOutput("label"))
def labelImp = IJ.getImage()
labelImp.setTitle("he-nuclei-labels")

import ij.plugin.frame.RoiManager
int n = RoiManager.getInstance().getCount()
IJ.log("H&E nuclei found: " + n)
```

Use Color Deconvolution only when you genuinely need a separated stain channel
for downstream measurement (e.g. quantifying DAB intensity per nucleus AFTER
segmentation) — never to preprocess input for StarDist segmentation.

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
| `nTiles` | `int` | `1` | if Image > 5MP, set nTiles>= 4 by default, 1, 4, 9, 16 (use square grid values) |
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
| `"Versatile (H&E nuclei)"` | Brightfield H&E histology nuclei, RGB images|
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

### Pitfall 3 — Out-of-Memory (OOM) on large images

StarDist 2D processes images in the GPU/CPU memory. Large images (e.g., > 10MP) often crash without tiling.

Solution: Always calculate nTiles based on image area. In the StarDist 2D plugin, nTiles refers to the number of tiles per dimension (e.g., nTiles = 2 creates a 2×2 grid). The heuristic max(1, ceil(W*H/10^7)) is a safe baseline for most systems.

Groovy example for dynamic nTiles calculation:

```groovy
long w = imp.getWidth()
long h = imp.getHeight()
int calculatedTiles = (int) Math.max(1, Math.ceil((w * h) / 10000000.0))
```


### Pitfall 4 — `getOutput("label")` is a Dataset, not an ImagePlus
```groovy
// WRONG — Dataset does not have setTitle(), getProcessor(), etc.:
def labelImp = res.getOutput("label")
labelImp.setTitle("labels")    // ERROR

// CORRECT — show the Dataset first, then get the ImagePlus:
uiService.show(res.getOutput("label"))
def labelImp = IJ.getImage()
labelImp.setTitle("labels")
```

### Pitfall 5 — ROI Manager must be cleared between images in batch
```groovy
// At the start of each image in a loop:
def rm = RoiManager.getInstance() ?: new RoiManager()
rm.reset()
IJ.run("Clear Results", "")
```

### Pitfall 6 — Single grayscale channel only for certain models (RGB and multi-channel both fail)

The `Versatile (fluorescent nuclei)` model expects a **single-channel grayscale** image.

For H&E, use `Versatile (H&E nuclei)` instead and DO NOT convert RGB for the H&E nuclei model, it expects RGB input.


Two distinct failure modes for models OTHER than the H&E nuclei model:

1. **RGB images** (`bitDepth == 24`, `type == ImagePlus.COLOR_RGB`) — the detector
   returns a null prediction and the run yields zero ROIs (or throws
   `NullPointerException: prediction is null` when wrapped by TrackMate-StarDist).
   Convert first:
   ```groovy
   if (imp.getType() == ImagePlus.COLOR_RGB) {
       IJ.run(imp, "8-bit", "")    // luminosity → single 8-bit channel
   }
   ```


2. **Multi-channel composites** (`getNChannels() > 1`) — StarDist silently uses
   the first channel. Extract the target channel before running:
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
| Touching nuclei merging into one | Raise `nmsThresh` (e.g. 0.4 → 0.6) — higher IoU threshold = less suppression, so both touching nuclei survive |
| Nuclei split into multiple objects | Lower `nmsThresh` (e.g. 0.4 → 0.2) — lower IoU threshold = more aggressive suppression, so duplicate detections of the same nucleus collapse |
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
