# StackReg — Groovy Scripting API

## Key Difference from TurboReg: StackReg IS Recordable

Unlike TurboReg (which is not macro-recordable), **StackReg is fully
macro-recordable**. The parameter string can be captured with the Macro Recorder
(`Plugins › Macros › Record…`) and the result is a clean, portable `IJ.run()`
call that works in Groovy without modification.

The recorded call always looks like:

```groovy
IJ.run("StackReg ", "transformation=[Rigid Body]")
```

---

## Critical: Trailing Space in Command Name

The command name **must include a trailing space**, identical to TurboReg:

```groovy
IJ.run("StackReg ", "...")   // CORRECT
IJ.run("StackReg", "...")    // WRONG — plugin not found, silently does nothing
```

This is the single most common scripting mistake with both StackReg and TurboReg.

---

## Full Syntax

```groovy
IJ.run("StackReg ", "transformation=[<TYPE>]")
```

The `transformation` parameter value must be wrapped in square brackets and
match one of the four valid strings exactly (case-sensitive):

| Transformation | Parameter string |
|---|---|
| Translation | `transformation=[Translation]` |
| Rigid Body | `transformation=[Rigid Body]` |
| Scaled Rotation | `transformation=[Scaled Rotation]` |
| Affine | `transformation=[Affine]` |

Bilinear is not available in StackReg.

---

## What StackReg Does to the Active Image

- Operates on whatever image is **currently active** (frontmost window)
- Uses the **currently displayed slice** as the anchor
- **Replaces the original stack in-place** — no new window is opened
- Always uses **Accurate** quality (cubic-spline interpolation via TurboReg)
- TurboReg is called internally; temporary files are written to the ImageJ
  temp directory during processing

---

## How StackReg Calls TurboReg Internally

Understanding this is important for debugging and for building multi-channel
workflows. From the StackReg source code, for each slice pair it calls:

```java
IJ.runPlugIn("TurboReg_", "-align"
    + " -file " + sourcePathAndFileName
    + " 0 0 " + (width-1) + " " + (height-1)
    + " -file " + targetPathAndFileName
    + " 0 0 " + (width-1) + " " + (height-1)
    + " -" + transformationName
    + " " + landmarkCoordinates
    + " -hideOutput")
```

Key points:
- StackReg uses `-file` references (temp files) not `-window` references
- It uses `-hideOutput` so TurboReg does not open a new window per slice
- The transformation results (landmark coordinates) are retrieved from TurboReg
  via the plugin-to-plugin API and propagated to the next slice

---

## Groovy Recipes

### Recipe 1 — Minimal Registration (active stack)

```groovy
import ij.IJ

// The active stack is registered in-place using Rigid Body
// Make sure the correct stack is frontmost and the correct anchor slice is shown
IJ.run("StackReg ", "transformation=[Rigid Body]")
```

---

### Recipe 2 — Open a Stack, Navigate to Anchor, Register

```groovy
import ij.IJ
import ij.ImagePlus

def stackPath = "/data/timelapse.tif"
def anchorSlice = 30     // 1-based slice index
def transformation = "Rigid Body"   // "Translation", "Rigid Body", "Scaled Rotation", "Affine"

// Open the stack
def imp = IJ.openImage(stackPath)
if (imp == null) {
    IJ.error("StackReg Workflow", "Could not open: " + stackPath)
    return
}
imp.show()

// Navigate to the anchor slice — this is what StackReg will use as its reference
imp.setSlice(anchorSlice)

IJ.log("Registering with " + transformation + ", anchor = slice " + anchorSlice)

// Register in-place
// Note the mandatory trailing space in "StackReg "
IJ.run(imp, "StackReg ", "transformation=[" + transformation + "]")

IJ.log("Registration complete. Slices: " + imp.getNSlices())

// Save result
IJ.saveAsTiff(imp, "/data/timelapse_registered.tif")
IJ.log("Saved: /data/timelapse_registered.tif")
```

---

### Recipe 3 — Protect the Original (Duplicate Before Registering)

Because StackReg modifies the stack in-place, always duplicate if you need
the original data:

```groovy
import ij.IJ
import ij.ImagePlus
import ij.plugin.Duplicator

def stackPath = "/data/timelapse.tif"

def original = IJ.openImage(stackPath)
original.show()

// Duplicate the entire stack before registering
def toRegister = new Duplicator().run(original)
toRegister.setTitle("timelapse_copy")
toRegister.show()

// Set anchor to slice 1 (default — first slice is displayed on open)
toRegister.setSlice(1)

IJ.run(toRegister, "StackReg ", "transformation=[Translation]")

// Original is untouched; toRegister now contains the registered data
IJ.saveAsTiff(toRegister, "/data/timelapse_registered.tif")
original.close()
```

---

### Recipe 4 — Batch Registration of Multiple Stacks

```groovy
import ij.IJ
import ij.ImagePlus
import java.io.File

def INPUT_DIR  = "/data/experiments/"
def OUTPUT_DIR = "/data/registered/"
def TRANSFORMATION = "Rigid Body"
def ANCHOR_SLICE = 1    // use first slice as anchor for all stacks

new File(OUTPUT_DIR).mkdirs()

def files = new File(INPUT_DIR).listFiles()
    .findAll { it.name.endsWith(".tif") || it.name.endsWith(".tiff") }
    .sort { it.name }

IJ.log("Found " + files.size() + " stacks to register")

files.each { file ->
    IJ.log("\nProcessing: " + file.name)

    def imp = IJ.openImage(file.absolutePath)
    if (imp == null) {
        IJ.log("  SKIP — could not open file")
        return
    }

    if (imp.getNSlices() < 2) {
        IJ.log("  SKIP — fewer than 2 slices")
        imp.close()
        return
    }

    imp.show()
    imp.setSlice(ANCHOR_SLICE)

    IJ.run(imp, "StackReg ", "transformation=[" + TRANSFORMATION + "]")

    def outPath = OUTPUT_DIR + file.name.replaceAll(/\.tiff?$/, "_registered.tif")
    IJ.saveAsTiff(imp, outPath)
    IJ.log("  Saved: " + outPath)

    imp.close()
}

IJ.log("\nDone. " + files.size() + " stacks processed.")
```

---

### Recipe 5 — Multi-Channel: Register on One Channel, Apply to Another

This pattern uses StackReg on a single channel for registration computation,
then uses TurboReg's `-transform` mode to apply the same landmarks to other
channels. This requires reading back the TurboReg result landmarks — which is
the most advanced use case.

The simpler approach is to use **MultiStackReg** (a separate plugin):

```groovy
import ij.IJ
import ij.ImagePlus
import ij.plugin.Duplicator

def hyperstackPath = "/data/multichannel_timelapse.tif"

// Open the hyperstack
def hyperstack = IJ.openImage(hyperstackPath)
hyperstack.show()

// Split into individual channel stacks
IJ.run(hyperstack, "Split Channels", "")
// After Split Channels, separate windows exist named "C1-...", "C2-...", etc.

def c1 = IJ.getImage()   // C1 is now frontmost — adjust if needed
def c1Title = c1.getTitle()

// Register C1 (the reference channel) in-place
c1.setSlice(c1.getNSlices() / 2 as int)   // anchor at midpoint
IJ.run(c1, "StackReg ", "transformation=[Rigid Body]")

IJ.log("C1 registered. Now apply same registration to C2 using MultiStackReg.")
// From here, use MultiStackReg plugin manually or via its own IJ.run() call:
// IJ.run("MultiStackReg", "stack_1=" + c1Title + " action_1=[Use as Reference] ...")
// (MultiStackReg parameter strings must be captured via Macro Recorder)
```

---

### Recipe 6 — Check ImageJ Temp Directory

If StackReg fails or produces unexpected results, inspect the temp files:

```groovy
import ij.IJ

def tempDir = IJ.getDirectory("temp")
IJ.log("ImageJ temp directory: " + tempDir)

// List StackReg temp files
["StackRegSource", "StackRegTarget",
 "StackRegSourceR", "StackRegSourceG", "StackRegSourceB"].each { name ->
    def f = new java.io.File(tempDir + name)
    if (f.exists()) {
        IJ.log("  Found: " + f.absolutePath + " (" + f.length() + " bytes)")
    } else {
        IJ.log("  Not found: " + name)
    }
}
```

---

## Relationship to TurboReg in Scripting

You will encounter workflows that use both StackReg and TurboReg together.
The key distinction:

| Task | Use |
|---|---|
| Align all slices of a stack sequentially | `IJ.run("StackReg ", ...)` |
| Align one specific image to another | `IJ.run("TurboReg ", ...)` |
| Apply a known transform to every slice individually | `IJ.run("TurboReg ", "-transform ...")` in a loop |
| Register multi-channel stacks | StackReg on one channel + MultiStackReg for others |

When StackReg is all you need, always prefer it over manually looping TurboReg —
StackReg handles the propagation, temp files, colour conversion, and PCA
internally.

---

## Critical Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Missing trailing space: `"StackReg"` | Plugin not found; call silently does nothing | Always `"StackReg "` with a trailing space |
| Not duplicating before registering | Original stack permanently overwritten | Use `new Duplicator().run(imp)` before calling StackReg |
| Wrong anchor slice | All slices registered from the wrong reference | Set `imp.setSlice(n)` before `IJ.run(...)` |
| TurboReg not installed | StackReg launches but fails silently mid-stack | Install via BIG-EPFL update site |
| Using `"Affine"` on featureless images | Overfitting; registration diverges | Use `"Translation"` or `"Rigid Body"` instead |
| Temp directory full | StackReg fails partway through large stacks | Free space in the ImageJ temp directory |
| `transformation=[bilinear]` | Parameter not recognised | Bilinear is unavailable in StackReg; use TurboReg directly |
