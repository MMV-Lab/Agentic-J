---
name: turboreg_documentation
description: An ImageJ plugin for Registration from EPFL BIG that automatically aligns a **source** image
 or stack to a fixed **target** image using intensity-based pyramid optimisation.
 Achieves sub-pixel accuracy via cubic-spline interpolation. Standard tool for
 motion correction, channel alignment, and time-lapse stabilisation in Fiji.
 Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---


## Automation via Groovy?

**YES — but there are TWO call patterns with different class strings.**
TurboReg is NOT macro-recordable, so the string cannot be captured by the
Macro Recorder. It must be written following the documented syntax.

| API | Class string | Returns | Use when |
|---|---|---|---|
| `IJ.run` | `"TurboReg "` (trailing space) | void — fetch front window | warp only |
| `IJ.runPlugIn` | `"TurboReg_"` (underscore, no space) | `TurboReg_` instance | need `getSourcePoints/getTargetPoints/getTransformedImage` for `-transform` reuse |

The two strings are **not interchangeable**. Mixing them returns null /
silently does nothing. See `GROOVY_SCRIPT_API.md` for the full pattern table.

```groovy
// Pattern A — warp only
IJ.run("TurboReg ", "...")               // CORRECT (trailing space)
IJ.run("TurboReg", "...")                // WRONG — silently does nothing

// Pattern B — warp + refined landmarks for cross-channel reuse
def tr = IJ.runPlugIn("TurboReg_", "...") // CORRECT (underscore, no space)
IJ.runPlugIn("TurboReg ", "...")          // WRONG — returns null
```

---

## Command Structure

```
"-align <SOURCE> <CROP> <TARGET> <CROP> <TRANSFORMATION> <LANDMARKS> (-showOutput | -hideOutput)"
"-transform <SOURCE> <OUT_W> <OUT_H> <TRANSFORMATION> <LANDMARKS> (-showOutput | -hideOutput)"
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
| Translation | `-translation` | 1 block | 2 |
| Rigid Body | `-rigidBody` | 3 blocks | 3 |
| Scaled Rotation | `-scaledRotation` | 2 blocks | 4 |
| Affine | `-affine` | 3 blocks | 6 |
| Bilinear | `-bilinear` | 4 blocks | 8 |

**Each block is four numbers in this order:** `sourceX sourceY targetX targetY`.
Blocks are concatenated back-to-back (one full block per landmark). Do **not**
"group by axis" (all source-Xs, then all source-Ys, etc.) — that form parses
without error but produces a garbled / near-identity transform.

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

**Rigid Body** (3 non-collinear blocks of 4):
```groovy
IJ.run("TurboReg ",
    "-align " +
    "-window \"source.tif\" 0 0 511 511 " +
    "-window \"target.tif\" 0 0 511 511 " +
    "-rigidBody " +
    "256 256 256 256 " +   // block 1: sx sy tx ty (translation seed)
    "128 128 128 128 " +   // block 2: sx sy tx ty (off-axis, NOT same column as block 1)
    "384 384 384 384 " +   // block 3: sx sy tx ty (off-axis, forms a triangle with 1 & 2)
    "-showOutput")
```

Bad rigid-body seed (collinear — all on the centre column):
```
256 256 256 256   256 128 256 128   256 384 256 384    // sx is 256 for all → triangle is a line
```
This fails or produces near-identity. Spread the three blocks into a proper
triangle (different sx and different sy across the three blocks).

---

## Getting the Result

```groovy
// Pattern A — only need the warped image
IJ.run("TurboReg ", "... -showOutput")
def result = IJ.getImage()        // registered image = frontmost window
IJ.saveAsTiff(result, "/out.tif")

// Pattern B — also need refined landmarks (to apply same transform to other channels)
def tr = IJ.runPlugIn("TurboReg_", "... -hideOutput")     // class name: underscore
def warped     = tr.getTransformedImage()
double[][] srcP = tr.getSourcePoints()
double[][] tgtP = tr.getTargetPoints()
```

For the multi-channel pattern (register channel A, then apply that exact
transform to channels B and C via `-transform`), see Recipe 7 in
`GROOVY_SCRIPT_API.md`.

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

1. **Wrong class string for the API** — `IJ.run` uses `"TurboReg "` (trailing
   space); `IJ.runPlugIn` uses `"TurboReg_"` (underscore, no space). Swapping
   them silently returns null / does nothing.
2. **Landmark format = blocks of four** — each landmark is `sx sy tx ty` and
   blocks are placed back-to-back. "Grouping by axis" (all sx, then all sy,
   then all tx, then all ty) parses without error but produces a garbled
   near-identity transform — a particularly nasty silent-failure mode.
3. **Collinear rigid-body seed** — placing all three seed points on the same
   vertical or horizontal line gives an unstable / no-movement fit. Use a
   triangle (e.g. centre + two off-axis points).
4. **NOT recordable** — Macro Recorder does not capture TurboReg calls; write
   the string manually.
5. **Wrong landmark count** — each transformation type requires a fixed number;
   wrong count fails silently or produces garbage.
6. **Image title with slice indicator** — use base title, not `"img.tif [1/5]"`.
7. **RGB stack + batch mode** — not supported; convert to grayscale first.
8. **No `-showOutput` / `-hideOutput`** — must end with exactly one. With
   `IJ.run` + `-showOutput`, `IJ.getImage()` returns the warped image.

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
