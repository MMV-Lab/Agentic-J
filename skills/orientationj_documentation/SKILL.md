---
name: orientationj_documentation
description: OrientationJ is a Fiji/ImageJ plugin for local orientation and coherency analysis in grayscale images, based on the structure tensor. This skill documents the validated Groovy automation path — macro-recorded `IJ.run(...)` calls for Analysis, Distribution, Vector Field, Corner Harris, and Dominant Direction — plus a runnable export workflow for the image and table outputs those commands produce. Read the files listed at the end of this SKILL for full parameter keys, menu paths, workflow steps, and scope limits.
---

Install via the Fiji update site **BIG-EPFL**, then restart Fiji.

---

## Primary Use Case in This Skill Set

Open a grayscale 2D image → run one OrientationJ mode → save the produced
images, tables, and overlays.

The most common path is `Analysis` for per-pixel maps plus `Distribution` for a
global orientation histogram. `Vector Field`, `Corner Harris`, and
`Dominant Direction` are additional validated modes.

---

## Minimal Groovy Script — Analysis Mode

```groovy
import ij.IJ
import ij.ImagePlus

def imp = IJ.getImage()   // must be 8/16/32-bit grayscale

IJ.run(imp, "OrientationJ Analysis",
    "tensor=1.0 gradient=0 " +
    "hsb=on hue=Orientation sat=Coherency bri=Original-Image " +
    "color-survey=on orientation=on coherency=on energy=on radian=off ")

// Four new windows appear:
//   OJ-Energy-1, OJ-Orientation-1, OJ-Coherency-1, OJ-Color-survey-1
def orientation = ij.WindowManager.getImage("OJ-Orientation-1")
IJ.saveAsTiff(orientation, "/tmp/orientation.tif")
```

See [GROOVY_WORKFLOW_DIRECTIONAL_ANALYSIS.groovy](GROOVY_WORKFLOW_DIRECTIONAL_ANALYSIS.groovy)
for a parameterised multi-mode script that also saves tables and overlays.

---

## Command Quick Reference

| Mode | `IJ.run()` command (key args only) | Key outputs |
|------|-----------------------------------|-------------|
| Analysis | `"OrientationJ Analysis", "tensor=1.0 gradient=0 hsb=on hue=Orientation sat=Coherency bri=Original-Image color-survey=on orientation=on coherency=on energy=on radian=off"` | 4 images: `OJ-Orientation-1`, `OJ-Coherency-1`, `OJ-Energy-1`, `OJ-Color-survey-1` |
| Distribution | `"OrientationJ Distribution", "tensor=1.0 gradient=0 histogram=on table=on min-coherency=10.0 min-energy=5.0 radian=off"` | Histogram plot (`OJ-Histogram-1-slice-1`) + table (`OJ-Distribution-1`) |
| Vector Field | `"OrientationJ Vector Field", "tensor=1.0 gradient=0 vectorgrid=24 vectorscale=100 vectortype=0 vectoroverlay=on vectortable=on"` | Vector table + overlay on the **active source image** |
| Corner Harris | `"OrientationJ Corner Harris", "tensor=1.0 gradient=0 harris-index=on harrisk=0.05 harrisl=3 harrismin=10.0 harrisoverlay=on harristable=on"` | Harris index image + corner table + overlay on the source |
| Dominant Direction | `"OrientationJ Dominant Direction", ""` | Table with `Slice`, `Orientation [Degrees]`, `Coherency [%]` |

### Gradient index mapping

| Index | Gradient |
|-------|----------|
| `0` | `Cubic Spline` (default) |
| `1` | `Finite Difference` |
| `2` | `Fourier` |
| `3` | `Riesz Filters` |
| `4` | `Gaussian` |

### Vector length mode mapping (`vectortype`)

| Index | Meaning |
|-------|---------|
| `0` | Maximum |
| `1` | Energy |
| `2` | Coherency |
| `3` | Energy × Coherency |

---

## 5 Critical Pitfalls

### Pitfall 1 — RGB inputs are rejected
OrientationJ's main analysis path accepts **8-bit, 16-bit, or 32-bit grayscale
only**. Convert RGB images before running:
```groovy
if (imp.getType() == ImagePlus.COLOR_RGB) {
    IJ.run(imp, "8-bit", "")
}
```

### Pitfall 2 — `radian` toggles the orientation range, not just the label
With `radian=off`, the orientation image is in degrees (~`-90` to `90`).
With `radian=on`, it is in radians (~`-π/2` to `π/2`). Downstream code that
assumes a fixed range will silently break when the flag is flipped.

### Pitfall 3 — Vector Field and Corner Harris draw on the source image
These two modes attach the vector field or detected corners as an **overlay on
the active source image**. To save the visualisation, flatten the source:
```groovy
IJ.run(imp, "OrientationJ Vector Field", "...vectoroverlay=on...")
ImagePlus flat = imp.flatten()
IJ.saveAsTiff(flat, "/tmp/vectors.tif")
```
If you close the source window before flattening, the overlay is lost.

### Pitfall 4 — Headless Fiji drops some IJ1 tables
In headless runs, the image outputs from all modes export reliably, but IJ1
`TextWindow` tables from Vector Field, Corner Harris, and Dominant Direction
are not always materialised. Run in GUI-backed Fiji when table capture is
critical, or use the plugin class directly for `Dominant Direction`
(`computeSpline(...)` — see the workflow script).

### Pitfall 5 — Distribution's `binary mask` / `orientation mask` keys don't
### emit separate windows through `IJ.run()`
The Distribution dialog exposes `Binary Mask` and `Orientation Mask`
checkboxes, but setting `binary mask=on` or `orientation mask=on` in a Groovy
`IJ.run(...)` call did not produce separate output windows in the validated
launcher pass. Rely on the histogram plot and distribution table instead.

---

## Parameter Tuning Quick Guide

| Observation | Fix |
|-------------|-----|
| Orientation map looks too noisy | Raise `tensor` (e.g. 1.0 → 2.0 or 3.0) |
| Fine directional structure is being averaged away | Lower `tensor` (e.g. 1.0 → 0.5) |
| Histogram dominated by weakly oriented background | Raise `min-coherency` (10 → 20–30) |
| Histogram dominated by low-signal regions | Raise `min-energy` (5 → 10–20) |
| Histogram is empty / too sparse | Lower `min-coherency` and `min-energy` |
| Too many / too few vectors in the overlay | Change `vectorgrid` (larger = fewer vectors) |
| Vector arrows too short / too long | Change `vectorscale` (percent) |
| Too many false corners | Raise `harrismin` or `harrisk` |
| Real corners missed | Lower `harrismin` |
| Orientation units inconsistent with downstream code | Set `radian=off` for degrees, `radian=on` for radians |

---

## File Index

| File | Contents |
|------|---------|
| `OVERVIEW.md` | Plugin description, typical inputs and scientific use cases, input/output tables, installation, limitations, citation |
| `GROOVY_API.md` | Every verified `IJ.run(...)` command with full parameter tables, output names, and runtime notes |
| `GROOVY_WORKFLOW_DIRECTIONAL_ANALYSIS.groovy` | **Executable Fiji script**: opens an image, runs one OrientationJ mode, saves images, tables, and overlays |
| `UI_GUIDE.md` | GUI reference for each OrientationJ menu entry — controls, choices, and expected outputs |
| `UI_WORKFLOW_ORIENTATION_ANALYSIS.md` | **Complete GUI walkthrough**: Analysis maps → Distribution histogram → interpretation → troubleshooting |
| `SKILL.md` | This file — LLM quick-reference card |
