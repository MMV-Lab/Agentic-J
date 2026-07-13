# TurboReg — Groovy Scripting API

## Critical Architecture Notes

**TurboReg is NOT macro-recordable.** The parameter string must be written
manually following the syntax documented here or on the official EPFL page:
https://bigwww.epfl.ch/thevenaz/turboreg/

**Two top-level operations:**
- `-align` — automatic registration: refines landmarks then warps the source
- `-transform` — applies a fixed set of landmarks without refinement (manual mode)

---

## Two Invocation Patterns (pick by what you need back)

TurboReg can be called from Groovy in two ways. They take the **same** parameter
string but use **different class names** and return **different** things.

### Pattern A — `IJ.run("TurboReg ", "...")` (warp only)

Returns `void`. Use when you only need the registered image and you will pick
it up from the front window.

```groovy
IJ.run("TurboReg ", "-align ... -showOutput")   // trailing space MANDATORY
def registered = IJ.getImage()                  // requires -showOutput
```

Pitfall: writing `"TurboReg"` (no trailing space) silently does nothing.

### Pattern B — `IJ.runPlugIn("TurboReg_", "...")` (warp + refined landmarks)

Returns a `TurboReg_` instance exposing `getSourcePoints()`,
`getTargetPoints()`, `getTransformedImage()`. Use this when you need to
**reuse the same transform** on additional channels (see Recipe 7).

```groovy
def tr = IJ.runPlugIn("TurboReg_", "-align ... -hideOutput")  // class name: underscore, no trailing space
if (tr == null) throw new RuntimeException("TurboReg plugin not found")
def registered  = tr.getTransformedImage()
double[][] srcP = tr.getSourcePoints()      // refined source landmarks
double[][] tgtP = tr.getTargetPoints()      // refined target landmarks
```

| API | Class string | Returns | Use when |
|---|---|---|---|
| `IJ.run` | `"TurboReg "` (trailing space) | void — fetch front window | warp only |
| `IJ.runPlugIn` | `"TurboReg_"` (underscore, no space) | TurboReg_ instance | need refined landmarks for `-transform` reuse |

The two strings are **not interchangeable**. Mixing them (`runPlugIn` with
`"TurboReg "`, or `run` with `"TurboReg_"`) returns null / fails silently.

---

## Full Parameter String Syntax

### `-align` (Automatic Registration)

```
-align
  <SOURCE_REF> <sourceCropLeft> <sourceCropTop> <sourceCropRight> <sourceCropBottom>
  <TARGET_REF> <targetCropLeft> <targetCropTop> <targetCropRight> <targetCropBottom>
  <TRANSFORMATION> <LANDMARKS>
  [-showOutput]
```

### `-transform` (Apply Fixed Landmarks)

```
-transform
<SOURCE_REF> <outputWidth> <outputHeight>
<TRANSFORMATION> <LANDMARKS>
(-showOutput | -hideOutput)
```

---

## Source and Target References

Two mutually exclusive ways to reference an image:

| Syntax | Meaning |
|---|---|
| `-file "/path/to/image.tif"` | Load from disk |
| `-window "Image Title"` | Reference an already-open ImageJ window by its title |

For Groovy scripting, `-window` is almost always preferable because the images
are already loaded into Fiji. The title must exactly match what appears in the
image window title bar (case-sensitive, including any trailing space or `[1/3]`
slice indicators — use the base title without slice info).

---

## Cropping Parameters

After the source or target reference, four integers define the crop region:

```
cropLeft  cropTop  cropRight  cropBottom
```

For no cropping, use `0 0 (width-1) (height-1)`. These can be computed from
the ImagePlus dimensions at runtime — see the Groovy examples below.

---

## Transformation Types and Landmark Syntax

**Landmark layout — read this first.**
TurboReg's own help text says:
*"FOR RIGID-BODY: 3 BLOCKS OF FOUR COORDINATES"*, and likewise for the other
transformations. Each "block of four" is **one landmark**, in the order
`sourceX sourceY targetX targetY`. Blocks are placed back-to-back, **not**
grouped by axis.

Correct rigid-body example (N=3):
```
-rigidBody  sx1 sy1 tx1 ty1   sx2 sy2 tx2 ty2   sx3 sy3 tx3 ty3
```

A common mistake is to "group axes": writing all source-X's, then all
source-Y's, then all target-X's, then all target-Y's. That form has the same
12 numbers but in the wrong slots — TurboReg parses it without erroring and
returns a near-identity / garbled transform, which is hard to debug. Do not
do this.

### Translation (1 block of four)

```
-translation  sourceX1 sourceY1  targetX1 targetY1
```

### Rigid Body (3 blocks of four)

```
-rigidBody
  sourceX1 sourceY1  targetX1 targetY1
  sourceX2 sourceY2  targetX2 targetY2
  sourceX3 sourceY3  targetX3 targetY3
```

The first block gives the overall translation. Blocks 2 and 3 determine the
rotation angle only — their distance from block 1 does not matter for the
computation, but blocks 1/2/3 must be **non-collinear** (do not place all on
the same vertical or horizontal line).

### Scaled Rotation (2 blocks of four)

```
-scaledRotation
  sourceX1 sourceY1  targetX1 targetY1
  sourceX2 sourceY2  targetX2 targetY2
```

### Affine (3 blocks of four)

```
-affine
  sourceX1 sourceY1  targetX1 targetY1
  sourceX2 sourceY2  targetX2 targetY2
  sourceX3 sourceY3  targetX3 targetY3
```

### Bilinear (4 blocks of four)

```
-bilinear
  sourceX1 sourceY1  targetX1 targetY1
  sourceX2 sourceY2  targetX2 targetY2
  sourceX3 sourceY3  targetX3 targetY3
  sourceX4 sourceY4  targetX4 targetY4
```

---

## Output Flag

| Flag | Effect |
|---|---|
| `-showOutput` | The registered (warped) image is displayed in a new window |
| `-hideOutput` | Registration runs without showing the result window |
| *(omitted)* | INVALID SYNTAX on many TurboReg builds ? always provide -showOutput or -hideOutput |

When using `-showOutput`, the result appears as the frontmost window immediately
after `IJ.run()` returns. Retrieve it with `IJ.getImage()` or
`WindowManager.getCurrentImage()`.

---

## Default Landmark Positions

When placing initial landmarks for automatic registration, centre-of-image
defaults work well for most datasets. The formulas below compute sensible
default positions from image dimensions:

| Transformation | Landmark positions |
|---|---|
| Translation | centre of image |
| Rigid Body | centre; centre ± 1/4 height above and below centre |
| Scaled Rotation | left-centre; right-centre |
| Affine | top-left third; top-right third; bottom-centre |
| Bilinear | four corners offset inward by 1/4 of each dimension |

---

## Groovy Recipes

### Recipe 1 — Minimal Translation Registration (windows)

```groovy
import ij.IJ
import ij.WindowManager

// Images must already be open
def source = WindowManager.getImage("source.tif")
def target = WindowManager.getImage("target.tif")

def sw = source.getWidth()
def sh = source.getHeight()
def tw = target.getWidth()
def th = target.getHeight()

// Centre landmark for translation
def sx = (sw / 2) as int
def sy = (sh / 2) as int
def tx = (tw / 2) as int
def ty = (th / 2) as int

IJ.run("TurboReg ",
    "-align " +
    "-window \"" + source.getTitle() + "\" 0 0 " + (sw-1) + " " + (sh-1) + " " +
    "-window \"" + target.getTitle() + "\" 0 0 " + (tw-1) + " " + (th-1) + " " +
    "-translation " + sx + " " + sy + " " + tx + " " + ty + " " +
    "-showOutput")

def result = IJ.getImage()   // registered image is now the frontmost window
IJ.log("Registered: " + result.getTitle())
```

---

### Recipe 2 — Rigid Body Registration (windows)

```groovy
import ij.IJ
import ij.WindowManager

def source = WindowManager.getImage("moving.tif")
def target = WindowManager.getImage("reference.tif")

def sw = source.getWidth();  def sh = source.getHeight()
def tw = target.getWidth();  def th = target.getHeight()

// Default rigid body landmarks: centre + two rotation guides
def cx = sw / 2 as int;  def cy = sh / 2 as int  // translation landmark
def rx = tw / 2 as int;  def ry = th / 2 as int

IJ.run("TurboReg ",
    "-align " +
    "-window \"" + source.getTitle() + "\" 0 0 " + (sw-1) + " " + (sh-1) + " " +
    "-window \"" + target.getTitle() + "\" 0 0 " + (tw-1) + " " + (th-1) + " " +
    "-rigidBody " +
    // landmark 1: translation (source centre → target centre)
    cx + " " + cy + " " + rx + " " + ry + " " +
    // landmark 2: rotation top guide
    cx + " " + (cy - sh/4 as int) + " " + rx + " " + (ry - th/4 as int) + " " +
    // landmark 3: rotation bottom guide
    cx + " " + (cy + sh/4 as int) + " " + rx + " " + (ry + th/4 as int) + " " +
    "-showOutput")

def registered = IJ.getImage()
```

---

### Recipe 3 — Affine Registration (windows)

```groovy
import ij.IJ
import ij.WindowManager

def source = WindowManager.getImage("source.tif")
def target = WindowManager.getImage("target.tif")

def sw = source.getWidth();  def sh = source.getHeight()
def tw = target.getWidth();  def th = target.getHeight()

// Three landmarks: top-left, top-right, bottom-centre
IJ.run("TurboReg ",
    "-align " +
    "-window \"" + source.getTitle() + "\" 0 0 " + (sw-1) + " " + (sh-1) + " " +
    "-window \"" + target.getTitle() + "\" 0 0 " + (tw-1) + " " + (th-1) + " " +
    "-affine " +
    // landmark 1: top-left region
    (sw/4 as int) + " " + (sh/4 as int) + " " + (tw/4 as int) + " " + (th/4 as int) + " " +
    // landmark 2: top-right region
    (3*sw/4 as int) + " " + (sh/4 as int) + " " + (3*tw/4 as int) + " " + (th/4 as int) + " " +
    // landmark 3: bottom-centre
    (sw/2 as int) + " " + (3*sh/4 as int) + " " + (tw/2 as int) + " " + (3*th/4 as int) + " " +
    "-showOutput")
```

---

### Recipe 4 — Batch Stack Registration (all slices to one target)

```groovy
import ij.IJ
import ij.ImagePlus
import ij.WindowManager

// Source must be a grayscale stack; target is a single image
def source = WindowManager.getImage("timelapse.tif")   // stack
def target = WindowManager.getImage("reference.tif")   // single frame

def sw = source.getWidth();  def sh = source.getHeight()
def tw = target.getWidth();  def th = target.getHeight()

def cx = sw / 2 as int;  def cy = sh / 2 as int
def rx = tw / 2 as int;  def ry = th / 2 as int

// Batch mode: registers all slices sequentially
IJ.run("TurboReg ",
    "-align " +
    "-window \"" + source.getTitle() + "\" 0 0 " + (sw-1) + " " + (sh-1) + " " +
    "-window \"" + target.getTitle() + "\" 0 0 " + (tw-1) + " " + (th-1) + " " +
    "-translation " + cx + " " + cy + " " + rx + " " + ry + " " +
    "-showOutput")

// Result is a float 32-bit stack
def registeredStack = IJ.getImage()
IJ.log("Registered stack: " + registeredStack.getNSlices() + " slices")
```

---

### Recipe 5 — Apply Known Landmarks Without Refinement (`-transform`)

Use `-transform` to apply a fixed transformation (e.g. loaded from a saved
landmarks file, or computed from a reference channel and re-applied to another).

```groovy
import ij.IJ
import ij.WindowManager

def source = WindowManager.getImage("channel2.tif")
def target = WindowManager.getImage("reference.tif")

def sw = source.getWidth();  def sh = source.getHeight()
def tw = target.getWidth();  def th = target.getHeight()

// Known translation from a previous registration: source must shift by -12, +5
def sx = sw / 2 as int;  def sy = sh / 2 as int       // source landmark
def tx = sx + 12 as int; def ty = sy - 5 as int        // target landmark (refined)

IJ.run("TurboReg ",
    "-transform " +                                     // no automatic refinement
    "-window \"" + source.getTitle() + "\" 0 0 " + (sw-1) + " " + (sh-1) + " " +
    "-window \"" + target.getTitle() + "\" 0 0 " + (tw-1) + " " + (th-1) + " " +
    "-translation " + sx + " " + sy + " " + tx + " " + ty + " " +
    "-showOutput")
```

---

### Recipe 7 — Reuse a TurboReg Alignment Across Channels

This is the canonical pattern when you have multiple channels of the same
scene (e.g. fixed phase / TUNEL / DAPI) and need them all aligned to a live
reference using the **same** transform.

Step 1: register channel A automatically and capture the refined landmarks
with `IJ.runPlugIn("TurboReg_", ...)` (Pattern B).
Step 2: feed those landmarks into `-transform` for each other channel — no
re-refinement, so all channels share identical geometry.

```groovy
import ij.IJ
import ij.WindowManager

def target  = WindowManager.getImage("live_phase.tif")    // reference
def srcA    = WindowManager.getImage("fixed_phase.tif")   // channel used to compute the transform
def srcB    = WindowManager.getImage("fixed_TUNEL.tif")   // additional channel, same FOV as srcA
def srcC    = WindowManager.getImage("fixed_DAPI.tif")

def sw = srcA.getWidth();  def sh = srcA.getHeight()
def tw = target.getWidth(); def th = target.getHeight()

// Non-collinear seed triangle (centre + two off-axis corners). Avoid placing
// all three seed points on one vertical or horizontal line.
def sx0 = (sw*0.50) as int;  def sy0 = (sh*0.50) as int
def sx1 = (sw*0.25) as int;  def sy1 = (sh*0.25) as int
def sx2 = (sw*0.75) as int;  def sy2 = (sh*0.75) as int
def tx0 = (tw*0.50) as int;  def ty0 = (th*0.50) as int
def tx1 = (tw*0.25) as int;  def ty1 = (th*0.25) as int
def tx2 = (tw*0.75) as int;  def ty2 = (th*0.75) as int

// Step 1: align channel A and capture refined landmarks
def tr = IJ.runPlugIn("TurboReg_",
    "-align " +
    "-window \"" + srcA.getTitle() + "\" 0 0 " + (sw-1) + " " + (sh-1) + " " +
    "-window \"" + target.getTitle() + "\" 0 0 " + (tw-1) + " " + (th-1) + " " +
    "-rigidBody " +
    sx0 + " " + sy0 + " " + tx0 + " " + ty0 + " " +
    sx1 + " " + sy1 + " " + tx1 + " " + ty1 + " " +
    sx2 + " " + sy2 + " " + tx2 + " " + ty2 + " " +
    "-hideOutput")

if (tr == null) throw new RuntimeException("TurboReg_ not found — install BIG-EPFL update site")

double[][] srcP = tr.getSourcePoints()   // refined landmarks, shape [N][2] with [i][0]=x, [i][1]=y
double[][] tgtP = tr.getTargetPoints()
def registeredA = tr.getTransformedImage()
registeredA.setTitle("registered_A")

// Step 2: build the BLOCKS-OF-FOUR landmark string from refined points
def lm = ""
for (int i = 0; i < 3; i++) {
    lm += (srcP[i][0] as int) + " " + (srcP[i][1] as int) + " " +
          (tgtP[i][0] as int) + " " + (tgtP[i][1] as int) + " "
}

def applySame = { src, outTitle ->
    def tr2 = IJ.runPlugIn("TurboReg_",
        "-transform " +
        "-window \"" + src.getTitle() + "\" " + tw + " " + th + " " +
        "-rigidBody " + lm +
        "-hideOutput")
    if (tr2 == null) throw new RuntimeException("TurboReg_ transform call failed for " + src.getTitle())
    def out = tr2.getTransformedImage()
    out.setTitle(outTitle)
    return out
}

def registeredB = applySame(srcB, "registered_B")
def registeredC = applySame(srcC, "registered_C")
```

Notes:
- Use `IJ.runPlugIn("TurboReg_", ...)` (Pattern B) here, **not** `IJ.run`.
  Only `runPlugIn` returns the object with `getSourcePoints/getTargetPoints`.
- The refined landmarks already follow the blocks-of-four convention when
  serialised correctly — iterate `for i: sx sy tx ty` as shown.
- `-transform` does **not** re-optimise — it applies the supplied landmarks
  exactly, so geometry is identical across channels.

---

### Recipe 6 — Load Images from Disk (`-file`)

When images are not already open in Fiji, use `-file` instead of `-window`:

```groovy
import ij.IJ

def sourcePath = "/data/exp01/moving.tif"
def targetPath = "/data/exp01/reference.tif"

// Image dimensions must be known in advance (or open the image briefly to read them)
def w = 1024
def h = 1024

IJ.run("TurboReg ",
    "-align " +
    "-file \"" + sourcePath + "\" 0 0 " + (w-1) + " " + (h-1) + " " +
    "-file \"" + targetPath + "\" 0 0 " + (w-1) + " " + (h-1) + " " +
    "-translation " + (w/2) + " " + (h/2) + " " + (w/2) + " " + (h/2) + " " +
    "-showOutput")

def result = IJ.getImage()
IJ.saveAsTiff(result, "/data/exp01/registered.tif")
result.close()
```

---

## Retrieving the Result

After `IJ.run("TurboReg ", "... -showOutput")` returns:

```groovy
import ij.IJ
import ij.WindowManager

// Get the frontmost window (the registered image)
def result = IJ.getImage()

// Or by title if you know what TurboReg names it
def result2 = WindowManager.getImage("Registered")

// Save
IJ.saveAsTiff(result, "/output/registered.tif")

// Convert from float 32-bit to 16-bit before saving if needed
IJ.run(result, "16-bit", "")
IJ.saveAsTiff(result, "/output/registered_16bit.tif")
```

---

## Critical Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Wrong class string for the API: `IJ.run("TurboReg_", ...)` or `IJ.runPlugIn("TurboReg ", ...)` | Silently does nothing / returns null | `IJ.run` uses `"TurboReg "` (trailing space); `IJ.runPlugIn` uses `"TurboReg_"` (underscore). See "Two Invocation Patterns" above |
| Landmarks "grouped by axis" instead of blocks of four | Parses without error; produces a near-identity / garbled transform | Each landmark = one block of `sx sy tx ty`; blocks back-to-back |
| Collinear rigid-body seed (all three blocks on same vertical or horizontal line) | Unstable fit / no movement | Use a triangle of seed points (different sx **and** different sy across the three blocks) |
| Using window title with slice info e.g. `"image.tif [1/10]"` | Window not found | Use base title without slice indicator |
| Wrong landmark count for transformation type | Registration produces garbage or error | Translation=1, RigidBody=3, ScaledRot=2, Affine=3, Bilinear=4 |
| Using `-align` with no overlap between source and target | Optimisation diverges | Crop both images to the overlap region first |
| Calling `IJ.getImage()` without `-showOutput` | Returns wrong or null image | Always include `-showOutput` when you need the result (Pattern A). Pattern B retrieves via `tr.getTransformedImage()` instead |
| RGB stack with batch mode | Batch mode unavailable | Convert to grayscale or use Automatic mode instead |
| Source/target image title contains special characters | String parsing errors | Rename the image first: `imp.setTitle("clean_name")` |
