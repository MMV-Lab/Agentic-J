---
name: turboreg_documentation
description: An ImageJ plugin for Registration from EPFL BIG that automatically aligns a **source** image
 or stack to a fixed **target** image using intensity-based pyramid optimisation.
 Achieves sub-pixel accuracy via cubic-spline interpolation. Standard tool for
 motion correction, channel alignment, and time-lapse stabilisation in Fiji.
 Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---


## Automation via Groovy?

**YES — via `IJ.run()` with a manually constructed parameter string.**
TurboReg is NOT macro-recordable, so the string cannot be captured by the
Macro Recorder. It must be written following the documented syntax.

**The single most common error:**

```groovy
IJ.run("TurboReg", "...")   // WRONG — missing trailing space, plugin not found
IJ.run("TurboReg ", "...")  // CORRECT — trailing space is mandatory
```

---

## Command Structure

```
IJ.run("TurboReg ", "-align <SOURCE> <CROP> <TARGET> <CROP> <TRANSFORMATION> <LANDMARKS> (-showOutput | -hideOutput)")
IJ.run("TurboReg ", "-transform <SOURCE> <OUT_W> <OUT_H> <TRANSFORMATION> <LANDMARKS> (-showOutput | -hideOutput)")
```

| Token | Options |
|---|---|
| Operation | `-align` (automatic) or `-transform` (fixed landmarks, no refinement) |
| Source/Target | `-window "Title"` (open image) or `-file "/path/file.tif"` |
| Crop | `left top right bottom` — use `0 0 (W-1) (H-1)` for no crop |
| Transformation | `-translation` · `-rigidBody` · `-scaledRotation` · `-affine` · `-bilinear` |
|Output | MUST end with exactly one: -showOutput OR -hideOutput
---

## Transformations and Landmark Counts

| Type | Flag | Landmarks | Degrees of freedom |
|---|---|---|---|
| Translation | `-translation` | 1 pair | 2 |
| Rigid Body | `-rigidBody` | 3 pairs | 3 |
| Scaled Rotation | `-scaledRotation` | 2 pairs | 4 |
| Affine | `-affine` | 3 pairs | 6 |
| Bilinear | `-bilinear` | 4 pairs | 8 |

Each landmark pair: `sourceX sourceY  targetX targetY`

---

## Minimal Working Examples

**Translation:**
```groovy
IJ.run("TurboReg ",
    "-align " +
    "-window \"source.tif\" 0 0 511 511 " +
    "-window \"target.tif\" 0 0 511 511 " +
    "-translation 256 256 256 256 " +
    "-showOutput")
```

**Rigid Body:**
```groovy
IJ.run("TurboReg ",
    "-align " +
    "-window \"source.tif\" 0 0 511 511 " +
    "-window \"target.tif\" 0 0 511 511 " +
    "-rigidBody " +
    "256 256 256 256 " +   // translation landmark
    "256 128 256 128 " +   // rotation guide 1
    "256 384 256 384 " +   // rotation guide 2
    "-showOutput")
```

---

## Getting the Result

```groovy
IJ.run("TurboReg ", "... -showOutput")
def result = IJ.getImage()        // registered image is the frontmost window
IJ.saveAsTiff(result, "/out.tif")
```

---

## Processing Modes

| Mode | How to invoke | Source requirement |
|---|---|---|
| Automatic | `-align` + `IJ.run(...)` | Single image or stack |
| Manual (no refinement) | `-transform` | Single image or stack |
| Batch (all slices) | `-align` with a stack as source | Grayscale stack only (not RGB) |

---

## Output

- Always **float 32-bit** from automatic/batch mode
- Always the **same dimensions** as the target
- Displayed as a new window when `-showOutput` is used
- Contains a second slice (mask) if source had a mask slice

---

## Critical Pitfalls

1. **Missing trailing space** in `"TurboReg "` — most common error, silently
   does nothing
2. **NOT recordable** — Macro Recorder does not capture TurboReg calls; write
   the string manually
3. **Wrong landmark count** — each transformation type requires a fixed number;
   wrong count causes registration to fail silently or produce garbage
4. **Image title with slice indicator** — use base title, not `"img.tif [1/5]"`
5. **RGB stack + batch mode** — not supported; convert to grayscale first
6. **No `-showOutput`** — if omitted, `IJ.getImage()` returns the wrong window

---

## When registration fails (no movement) or the sample is at the image edge

If the sample occupies only a border region, the default centred landmarks and raw intensities can cause TurboReg to converge to the **identity** (i.e. "no movement"). Two practical fixes:

1) **Edge-enhanced registration image (recommended)**
- Create a temporary copy for registration only (keep the original for output)
- Convert to 8-bit
- Apply a *Difference-of-Gaussians* (DoG) style filter (or *Find Edges*) to emphasise structure at borders
- Optionally enhance contrast

2) **Landmarks near borders/corners (rigidBody/affine)**
- Place landmarks near high-contrast features at the edges (e.g., ~10% inset from corners)
- Avoid placing all landmarks on the same line (e.g. all on the centre column)

These two changes together often fix "only corner preserved" / "did not move" outcomes for phase-contrast images with edge-localised tissue.

---

## File Inventory

| File | Contents |
|---|---|
| `OVERVIEW.md` | Plugin description, transformation types, modes, installation |
| `UI_GUIDE.md` | Every dialog control and parameter |
| `UI_WORKFLOW_REGISTRATION.md` | Step-by-step GUI walkthroughs (single, batch, manual, RGB) |
| `GROOVY_SCRIPT_API.md` | Full parameter syntax + 6 Groovy recipes |
| `WORKFLOW_BATCH_REGISTRATION.groovy` | Ready-to-run batch registration script |
| `SKILL.md` | This quick-reference card |
