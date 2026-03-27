# StarDist — SCRIPTING API REFERENCE

All commands in this file are sourced from:
- The official ImageJ wiki page (https://imagej.net/plugins/stardist)
- The official batch-processing gist by Martin Weigert
  (https://gist.github.com/maweigert/8dd6ef139e1cd37b2307b35fb50dee4a)
- Verified community examples from the image.sc forum

> StarDist is **not** driven by `IJ.run()` parameter strings the way MorphoLibJ is.
> It uses the SciJava `command.run()` API from Groovy scripts, and a special
> `Command From Macro` bridge from IJ Macro `.ijm` files.
> **Groovy is the recommended scripting language in Fiji** and is the primary language
> shown throughout this document.

---

## SCRIPTING APPROACH 1 — Groovy (recommended)

Groovy scripts run in the Fiji Script Editor with **Language: Groovy**.
The image is passed as a live object; outputs are retrieved by name.

### Required header and imports

```groovy
#@ CommandService command
#@ UIService uiService

import de.csbdresden.stardist.StarDist2D
import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.plugin.frame.RoiManager
import ij.measure.ResultsTable
```

### Minimal working example — active image, built-in model

```groovy
#@ CommandService command
#@ UIService uiService

import de.csbdresden.stardist.StarDist2D
import ij.IJ

def imp = IJ.getImage()

def res = command.run(StarDist2D, false,
    "input",               imp,
    "modelChoice",         "Versatile (fluorescent nuclei)",
    "normalizeInput",      true,
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
).get()                                 // .get() blocks until inference is complete

// Show the label output (it arrives as a SciJava Dataset, not an ImagePlus)
def labelDataset = res.getOutput("label")
uiService.show(labelDataset)
def labelImp = IJ.getImage()           // now retrieve it as an ImagePlus
labelImp.setTitle("label-image")
```

### Example with a custom model from a .zip file

```groovy
def res = command.run(StarDist2D, false,
    "input",               imp,
    "modelChoice",         "Model (.zip) from File",
    "modelFile",           "/path/to/my_model.zip",
    "normalizeInput",      true,
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
).get()
```

### Counting cells in Groovy

```groovy
// Option A — from the ROI Manager (requires outputType = "ROI Manager" or "Both")
import ij.plugin.frame.RoiManager
def rm = RoiManager.getInstance()
int cellCount = (rm != null) ? rm.getCount() : 0
IJ.log("Cell count: " + cellCount)

// Option B — from the label image maximum
// The maximum label value = total cell count when labels are assigned 1..N
import ij.measure.Measurements
def stats = labelImp.getStatistics(Measurements.MIN_MAX)
int cellCount = (int) stats.max
IJ.log("Cell count: " + cellCount)
```

### Measuring all ROIs in Groovy

```groovy
import ij.plugin.frame.RoiManager
import ij.measure.ResultsTable

def rm = RoiManager.getInstance()
if (rm != null && rm.getCount() > 0) {
    IJ.run("Set Measurements...", "area mean min center perimeter shape redirect=None decimal=3")
    rm.deselect()                       // ensure all ROIs are measured, not just selected ones
    rm.runCommand(imp, "Measure")       // measure against original intensity image
    def rt = ResultsTable.getResultsTable()
    IJ.log("Rows in Results table: " + rt.size())   // = cell count
    rt.save("/path/to/output/measurements.csv")
}
```

### Batch processing a folder in Groovy

```groovy
#@ File (label = "Input folder", style = "directory") inputDir
#@ File (label = "Output folder", style = "directory") outputDir
#@ CommandService command
#@ UIService uiService

import de.csbdresden.stardist.StarDist2D
import ij.IJ
import ij.plugin.frame.RoiManager
import ij.measure.ResultsTable

def files = inputDir.listFiles().findAll { it.name.endsWith(".tif") }.sort()

files.each { file ->
    IJ.log("Processing: " + file.name)

    def imp = IJ.openImage(file.absolutePath)
    if (imp == null) { IJ.log("  Skipping — could not open."); return }
    imp.show()

    // Clear ROI Manager and Results before each image
    def rm = RoiManager.getInstance() ?: new RoiManager()
    rm.reset()
    IJ.run("Clear Results", "")

    def res = command.run(StarDist2D, false,
        "input",               imp,
        "modelChoice",         "Versatile (fluorescent nuclei)",
        "normalizeInput",      true,
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
    ).get()

    // Get label image
    def labelDataset = res.getOutput("label")
    uiService.show(labelDataset)
    def labelImp = IJ.getImage()

    // Count and measure
    int cellCount = rm.getCount()
    IJ.run("Set Measurements...", "area mean min center perimeter shape redirect=None decimal=3")
    rm.deselect()
    rm.runCommand(imp, "Measure")
    def rt = ResultsTable.getResultsTable()

    // Save outputs
    String base = file.name.replaceAll(/\.[^.]+$/, "")
    IJ.saveAsTiff(labelImp, outputDir.absolutePath + "/" + base + "-labels.tif")
    rt.save(outputDir.absolutePath + "/" + base + "-measurements.csv")
    IJ.log("  Cells: " + cellCount)

    imp.close()
    labelImp.close()
}

IJ.log("Batch complete.")
```

---

## SCRIPTING APPROACH 2 — IJ Macro (`Command From Macro`)

Use this in `.ijm` macro files only. The image is referenced by **window title string**.
All parameter values, including numbers and booleans, are passed as **strings**.

### Full command template

```javascript
run("Command From Macro", "command=[de.csbdresden.stardist.StarDist2D], args=[" +
    "'input':'"               + imageTitle + "', " +
    "'modelChoice':'Versatile (fluorescent nuclei)', " +
    "'normalizeInput':'true', " +
    "'percentileBottom':'1.0', " +
    "'percentileTop':'99.8', " +
    "'probThresh':'0.5', " +
    "'nmsThresh':'0.4', " +
    "'outputType':'Both', " +
    "'nTiles':'1', " +
    "'excludeBoundary':'2', " +
    "'roiPosition':'Automatic', " +
    "'verbose':'false', " +
    "'showCsbdeepProgress':'false', " +
    "'showProbAndDist':'false'" +
    "], process=[false]");
// ↑ process=[false] is REQUIRED — omitting it causes silent failure
```

### Minimal working example

```javascript
rename("input");
run("Command From Macro", "command=[de.csbdresden.stardist.StarDist2D], args=['input':'input', 'modelChoice':'Versatile (fluorescent nuclei)', 'normalizeInput':'true', 'percentileBottom':'1.0', 'percentileTop':'99.8', 'probThresh':'0.5', 'nmsThresh':'0.4', 'outputType':'Both', 'nTiles':'1', 'excludeBoundary':'2', 'roiPosition':'Automatic', 'verbose':'false', 'showCsbdeepProgress':'false', 'showProbAndDist':'false'], process=[false]");
```

### Counting cells in IJ Macro

```javascript
// From ROI Manager (outputType = "ROI Manager" or "Both"):
n_cells = roiManager("count");
print("Cell count: " + n_cells);

// Measure all ROIs:
roiManager("deselect");
run("Set Measurements...", "area mean min center perimeter redirect=None decimal=3");
roiManager("Measure");
print("Measured cells: " + nResults);
```

---

## PARAMETER REFERENCE

### `modelChoice` — accepted strings

| Value | Description |
|-------|-------------|
| `"Versatile (fluorescent nuclei)"` | Built-in fluorescence model (DSB 2018) |
| `"DSB 2018 (from StarDist 2D paper)"` | Built-in alternative fluorescence model |
| `"Versatile (H&E nuclei)"` | Built-in H&E histology model |
| `"Model (.zip) from File"` | Custom model — set `"modelFile"` to local path |
| `"Model (.zip) from URL"` | Custom model — set `"modelFile"` to URL string |

### `outputType` — accepted strings

| Value | Effect |
|-------|--------|
| `"Label Image"` | New image window with integer labels (1 per cell, 0 = background) |
| `"ROI Manager"` | All detections added as polygon ROIs to the ROI Manager |
| `"Both"` | Label image + ROI Manager (recommended for scripting) |

### `roiPosition` — accepted strings

| Value | Use when |
|-------|---------|
| `"Automatic"` | Single 2D image (default) |
| `"Stack"` | Multi-frame stack |
| `"Hyperstack"` | Multi-channel multi-frame hyperstack |

### Numerical and boolean parameters

| Parameter | Groovy type | Default | Notes |
|-----------|------------|---------|-------|
| `percentileBottom` | `double` | `1.0` | Lower normalisation clip percentile |
| `percentileTop` | `double` | `99.8` | Upper normalisation clip percentile |
| `probThresh` | `double` | `0.5` | Detection confidence threshold (0–1) |
| `nmsThresh` | `double` | `0.4` | NMS overlap threshold (0–1) |
| `nTiles` | `int` | `1` | Tiles for inference; increase if OOM |
| `excludeBoundary` | `int` | `2` | Border pixels to suppress detections within |
| `normalizeInput` | `boolean` | `true` | Percentile intensity normalisation |
| `verbose` | `boolean` | `false` | Extra log output |
| `showCsbdeepProgress` | `boolean` | `false` | Show CSBDeep inference progress |
| `showProbAndDist` | `boolean` | `false` | Emit probability + distance images |

> **Groovy type note:** Pass `true`/`false` (lowercase booleans), `1.0` (double), `1` (int).
> **Do not** use `"true"` strings — those are for the IJ Macro approach only.
> Passing a string `"true"` in Groovy causes a type mismatch and the parameter may be ignored.

---

## OUTPUT DETAILS

### Label Image
- Window title: `"Label Image"` (default from StarDist)
- Pixel values: `0` = background, `1 2 3 …` = individual cells
- Arrives from `res.getOutput("label")` as a **SciJava Dataset**, not an ImagePlus
- **Must be shown via `uiService.show()` before calling `IJ.getImage()`**

```groovy
def labelDataset = res.getOutput("label")
uiService.show(labelDataset)         // registers it as a visible ImagePlus
def labelImp = IJ.getImage()         // retrieves the ImagePlus
```

### ROI Manager
- Each polygon ROI corresponds to one detected cell
- `RoiManager.getInstance().getCount()` = cell count
- ROIs can be measured, saved as `.zip`, or exported to the Results table

### Probability / Distance images (optional)
- Created only when `showProbAndDist = true`
- **Probability image:** 32-bit float, per-pixel detection score (0–1)
- **Distance image:** 32-bit float, predicted star-convex radial distances

---

## KNOWN PITFALLS

1. **Groovy booleans must be lowercase** — `true`/`false`, not `"true"`/`"false"` strings.
   Passing string `"true"` in the Groovy `command.run()` API causes a type mismatch
   and the parameter may be silently ignored.

2. **`getOutput("label")` is a Dataset, not an ImagePlus** — always call
   `uiService.show(labelDataset)` before `IJ.getImage()`. Skipping this step
   gives you the wrong ImagePlus.

3. **ROI Manager must be reset before each image in batch** — call `rm.reset()` and
   `IJ.run("Clear Results", "")` at the start of each file loop iteration.

4. **Single channel only** — multi-channel images must have the target channel
   extracted before running. StarDist will error or silently use only the first channel.

5. **`process=[false]` is mandatory in IJ Macro** — its absence causes silent failure.
   This pitfall applies to IJ Macro only, not to Groovy `command.run()`.

6. **nTiles must form a valid grid** — use values like `1`, `4` (2×2), `9` (3×3),
   `16` (4×4). Arbitrary values may cause incorrect tiling.

7. **`.get()` is required** — `command.run(...).get()` blocks until inference is done.
   Without `.get()` the result object is a Future and `getOutput()` will return null.
