# CLIJ2 — Groovy / scripting API

Everything here was executed against CLIJ2 2.5.3.5 on Fiji 2.16.0/1.54p with an NVIDIA A100
in this container. Op names, parameter orders and error strings are taken from the installed
jars, not from the website.

---

## 1. The skeleton every CLIJ2 script follows

```groovy
import net.haesleinhuepf.clij2.CLIJ2
import ij.IJ

def clij2 = CLIJ2.getInstance()          // fastest available OpenCL device
clij2.clear()                            // start from a clean GPU state
IJ.log("GPU: " + clij2.getGPUName())

def imp   = IJ.openImage("/data/image.tif")
def input = clij2.push(imp)                                  // host → device
def output = clij2.create(input)                             // allocate destination

clij2.gaussianBlur2D(input, output, 4, 4)                    // chain as many ops as you like

def result = clij2.pull(output)                              // device → host (ImagePlus)
IJ.saveAs(result, "Tiff", "/data/out.tif")

clij2.release(input); clij2.release(output)                  // free device memory
clij2.clear()
```

**The four structural rules**

1. `push` once, `pull` once — every transfer costs ~50 ms for a 512×512×64 volume here.
2. Every op writes into a **destination you allocate first**; ops do not return images.
   They return `boolean` (or a number / `ResultsTable` for measurements).
3. Everything you `push()` or `create()` must be `release()`d. `clij2.clear()` frees the lot.
4. Do **not** use `#@` SciJava script parameters — they open a dialog that blocks the run.

## 2. Allocating destinations

```groovy
clij2.create(other_buffer)                                   // same size AND same type
clij2.create(other_buffer.getDimensions(), clij2.Float)      // same size, forced 32-bit float
clij2.create([512, 512] as long[], clij2.UnsignedByte)       // explicit 2D
clij2.create([256, 256, 64] as long[], clij2.Float)          // explicit 3D
```

Types: `clij2.UnsignedByte` (8-bit), `clij2.UnsignedShort` (16-bit), `clij2.Float` (32-bit).

Choosing the type matters:

| Destination content | Allocate as |
|---|---|
| Label map | `clij2.Float` — an 8-bit destination silently caps at 255 labels |
| Difference-of-Gaussian, distance map, any signed/fractional result | `clij2.Float` |
| Binary mask | `clij2.UnsignedByte` (values 0/1) |
| Filtered image, same dynamic range as input | `clij2.create(input)` |

**The destination's dimensions define the output size and CLIJ2 does not check them.**
A wrong-size destination produces a silently cropped/scaled result, not an error
(verified: `gaussianBlur2D` from a 256×254 source into a 64×64 destination returned a 64×64
image with no warning).

### A `ClearCLBuffer` is not an `ImagePlus`

The buffer exposes only these accessors — `getWidth()`, `getHeight()`, `getNSlices()`,
`getBitDepth()`, `getProcessor()`, `getStatistics()` **do not exist** and throw
`groovy.lang.MissingMethodException: No signature of method`:

```groovy
long[] dims = buf.getDimensions()   // [x, y] for 2D, [x, y, z] for 3D
buf.getNativeType()                 // UnsignedByte | UnsignedShort | Float
buf.getLength()                     // number of pixels
buf.getSizeInBytes()
buf.getName() / buf.setName(String)
```

So a 2D destination for a Z-projection of a 3D buffer is:

```groovy
def dims = input.getDimensions()
def mip  = clij2.create([dims[0], dims[1]] as long[], clij2.Float)
clij2.maximumZProjection(input, mip)
```

Width/height/bit-depth in the ImageJ sense only exist after `clij2.pull(buf)`.

## 3. Getting data in and out

| Call | Meaning |
|---|---|
| `clij2.push(imp)` | whole `ImagePlus` (all slices) → device |
| `clij2.pushCurrentZStack(imp)` | only the current channel/frame of a hyperstack |
| `clij2.pushCurrentSlice(imp)` | only the displayed slice |
| `clij2.pull(buffer)` | → `ImagePlus` with the raw values (label maps come back 32-bit) |
| `clij2.pullBinary(buffer)` | → 8-bit `ImagePlus` with 0/**255** (use this for masks) |
| `clij2.pullRAI(buffer)` | → imglib2 `RandomAccessibleInterval` |

RGB input raises `RuntimeException: Only 8, 16 and 32-bit supported!` — convert first.

## 4. Measurements (return values, not images)

```groovy
double n     = clij2.sumOfAllPixels(buffer)
double mx    = clij2.maximumOfAllPixels(labels)     // == number of labels for a 1..N label map
double mean  = clij2.meanOfAllPixels(buffer)
double sd    = clij2.standardDeviationOfAllPixels(buffer)

import ij.measure.ResultsTable
def rt = new ResultsTable()
clij2.statisticsOfLabelledPixels(intensity_buffer, label_buffer, rt)   // one row per label
rt.save("/data/measurements.csv")
```

`statisticsOfLabelledPixels` fills **36 columns** (verified):

```
IDENTIFIER, BOUNDING_BOX_X/Y/Z, BOUNDING_BOX_END_X/Y/Z, BOUNDING_BOX_WIDTH/HEIGHT/DEPTH,
MINIMUM_INTENSITY, MAXIMUM_INTENSITY, MEAN_INTENSITY, SUM_INTENSITY,
STANDARD_DEVIATION_INTENSITY, PIXEL_COUNT, SUM_INTENSITY_TIMES_X/Y/Z, MASS_CENTER_X/Y/Z,
SUM_X/Y/Z, CENTROID_X/Y/Z, SUM_DISTANCE_TO_MASS_CENTER, MEAN_DISTANCE_TO_MASS_CENTER,
MAX_DISTANCE_TO_MASS_CENTER, MAX_MEAN_DISTANCE_TO_MASS_CENTER_RATIO,
SUM_DISTANCE_TO_CENTROID, MEAN_DISTANCE_TO_CENTROID, MAX_DISTANCE_TO_CENTROID,
MAX_MEAN_DISTANCE_TO_CENTROID_RATIO
```

`PIXEL_COUNT` is the area (2D) or volume (3D) **in pixels/voxels** — multiply by the pixel
size yourself if physical units are required. There is no perimeter/circularity/Feret here:
for shape descriptors pull the label map and use MorphoLibJ's `Analyze Regions`.

Other useful table ops: `statisticsOfBackgroundAndLabelledPixels` (adds a background row),
`statisticsOfImage(buffer, rt)` (whole-image stats), `pushResultsTable` / `pullToResultsTable`.

## 5. Memory management

```groovy
println clij2.reportMemory()     // "NVIDIA A100-SXM4-40GB contains 3 images." + per-buffer list
clij2.release(buffer)            // free one
clij2.clear()                    // free everything held by this instance
```

In a loop, release inside the loop body (`try { … } finally { release }`) — see
`GROOVY_WORKFLOW_BATCH_FOLDER.groovy`. Verified behaviour: ten `create()` calls without
release leave "contains 10 images"; `clear()` returns it to "contains 0 images".

## 6. Device selection

```groovy
import net.haesleinhuepf.clij.CLIJ
println CLIJ.getAvailableDeviceNames()          // sanity check — is a GPU even visible?
def clij2 = CLIJ2.getInstance()                 // fastest device (A100 here)
def cpu   = CLIJ2.getInstance("cpu")            // substring match on the device name
```

⚠ `getInstance("<name>")` **rebuilds the singleton**: instances and buffers obtained before
the switch become invalid, and calling `clear()` on the old handle throws
`NullPointerException: … getClearCLContext() is null`. Pick the device once, at the top.

## 7. Timing / benchmarking

The first CLIJ2 call in a JVM compiles OpenCL kernels. Always run the pipeline once as a
warm-up before measuring, and time `push + kernels + pull` — that is the number that decides
whether the GPU is worth it. Measured here (512×512×64 float32, gaussian σ=4):
CPU 1188 ms, GPU total 62 ms (kernel 6 ms, transfers 56 ms) → 19x.

## 8. What NOT to do from Groovy

**Do not drive CLIJ2 through IJ macro extensions from a script.** This pattern —

```groovy
IJ.runMacro('run("CLIJ2 Macro Extensions", "cl_device="); Ext.CLIJ2_push("img"); …')
```

— aborts in this container: `IJ.runMacro` returns `[aborted]`, the interpreter raises
`RuntimeException: Macro canceled`, and a **"Macro Error" dialog opens and blocks**, which
hangs an agent run. Registration and `Ext.CLIJ2_push` alone succeed; the first real op fails.
`Ext.CLIJ2_*` is for `.ijm` macro files run interactively; from Groovy always use the Java API
above.

**Menu commands work but are awkward.** `IJ.run(imp, "Gaussian blur 2D on GPU", "sigma_x=4
sigma_y=4")` does run (verified) but writes its result into a **new window with a generated
title** (`gaussian_blur-1828107390`), so the script cannot reliably find the output. Use the
Java API instead; reach for menu commands only when reproducing a recorded GUI workflow.

## 9. Deprecated ops (57 carry `@Deprecated` in the installed jars)

Replace on sight:

| Deprecated | Use instead |
|---|---|
| `blur2D`, `blur3D`, `blur3DSliceBySlice` | `gaussianBlur2D`, `gaussianBlur3D`, `gaussianBlur3DSliceBySlice` |
| `connectedComponentsLabeling` | `connectedComponentsLabelingBox` / `…Diamond` |
| `detectMaximaBox`, `detectMinimaBox` | CLIJx `detectMaxima…` variants, or `voronoiOtsuLabeling` for segmentation |
| `scale` | `scale2D` / `scale3D` |
| `affineTransform` | `affineTransform2D` / `affineTransform3D` |
| `rotateLeft`, `rotateRight` | `rotate2D` / `rotate3D` (or `transposeXY`) |
| `getSize` | `buffer.getDimensions()` |
| `image2DToResultsTable`, `resultsTableToImage2D` | `pullToResultsTable`, `pushResultsTable` |

Full list (CLIJ2): `affineTransform, blur2D, blur3D, blur3DSliceBySlice,
connectedComponentsLabeling, detectMaximaBox, detectMinimaBox, drawMeshBetweenNClosestLabels,
getSize, image2DToResultsTable, resultsTableToImage2D, rotateLeft, rotateRight, scale`.
The remaining 43 are CLIJx-only (`bilateral`, `seededWatershed`, `skeletonize`,
`subtractBackground2D/3D`, `topHatOctagon`, the `local*Map` family, …) — these still work but
are unstable; prefer a CLIJ2 equivalent where one exists.

## 10. Finding an operation

`OP_REFERENCE.md` lists all 451 CLIJ2 ops with their parameters, grouped by category.
To introspect the installed build directly from a script:

```groovy
def op = new net.haesleinhuepf.clij2.plugins.VoronoiOtsuLabeling()
println op.getName()                 // CLIJ2_voronoiOtsuLabeling
println op.getParameterHelpText()    // Image input, ByRef Image destination, Number spot_sigma, Number outline_sigma
println op.getDescription()
println op.getAvailableForDimensions()
```

The Java method name is the op name without the `CLIJ2_` prefix; parameters follow the same
order, with `ByRef` marking the destination you must allocate.
