# TurboReg — Groovy Scripting API

## Critical Architecture Notes

**TurboReg is NOT macro-recordable.** The parameter string must be written
manually following the syntax documented here or on the official EPFL page:
https://bigwww.epfl.ch/thevenaz/turboreg/

**The command name has a mandatory trailing space:**
```groovy
IJ.run("TurboReg ", "...")   // correct — note the space after TurboReg
IJ.run("TurboReg", "...")    // WRONG — plugin not found, call silently fails
```

**Two top-level operations:**
- `-align` — automatic registration: refines landmarks then warps the source
- `-transform` — applies a fixed set of landmarks without refinement (manual mode)

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

### Translation (1 landmark pair)

```
-translation  sourceX1 sourceY1  targetX1 targetY1
```



### Rigid Body (3 landmark pairs)

```
-rigidBody
  sourceX1 sourceY1  targetX1 targetY1
  sourceX2 sourceY2  targetX2 targetY2
  sourceX3 sourceY3  targetX3 targetY3
```

The first pair gives the overall translation. The second and third pairs
determine the rotation angle only — their distance from landmark 1 does not
matter for the computation.

### Scaled Rotation (2 landmark pairs)

```
-scaledRotation
  sourceX1 sourceY1  targetX1 targetY1
  sourceX2 sourceY2  targetX2 targetY2
```

### Affine (3 landmark pairs)

```
-affine
  sourceX1 sourceY1  targetX1 targetY1
  sourceX2 sourceY2  targetX2 targetY2
  sourceX3 sourceY3  targetX3 targetY3
```

### Bilinear (4 landmark pairs)

```
-bilinear
  sourceX1 sourceY1  targetX1 targetY1
  sourceX2 sourceY2  targetX2 targetY2
  sourceX3 sourceY3  targetX3 targetY3
  sourceX4 sourceY4  targetX4 targetY4
```

Landmark ordering note:
TurboReg's parser expects the landmark coordinates as grouped axis arrays:
`sourcePointsX[...] sourcePointsY[...] targetPointsX[...] targetPointsY[...]`.
For Translation (1 point), the common interleaved form looks identical.
For multi-point transforms (Rigid Body, Affine, Bilinear), prefer grouped ordering:
`srcX1 srcX2 srcX3 srcY1 srcY2 srcY3 tgtX1 tgtX2 tgtX3 tgtY1 tgtY2 tgtY3`

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
| Missing trailing space: `"TurboReg"` instead of `"TurboReg "` | Plugin not found; call silently does nothing | Always include the trailing space |
| Using window title with slice info e.g. `"image.tif [1/10]"` | Window not found | Use base title without slice indicator |
| Wrong landmark count for transformation type | Registration produces garbage or error | Translation=1, RigidBody=3, ScaledRot=2, Affine=3, Bilinear=4 |
| Using `-align` with no overlap between source and target | Optimisation diverges | Crop both images to the overlap region first |
| Calling `IJ.getImage()` without `-showOutput` | Returns wrong or null image | Always include `-showOutput` when you need the result |
| RGB stack with batch mode | Batch mode unavailable | Convert to grayscale or use Automatic mode instead |
| Source/target image title contains special characters | String parsing errors | Rename the image first: `imp.setTitle("clean_name")` |
