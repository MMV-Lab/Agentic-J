---
name: clij2_documentation
description: >-
  CLIJ2 runs classical image processing on the GPU via OpenCL inside Fiji — ~450 operations
  for filtering, binary/morphology, thresholding, labeling, per-label measurements,
  projections, transforms and image math, all on GPU buffers. Use it when a workflow is
  heavy (3D neighborhood filters, long operation chains, large batches, thousands of labels)
  and a plain ImageJ or MorphoLibJ implementation would be too slow. Not for deep-learning
  segmentation (cellpose/StarDist use CUDA, a different stack) and not worth it for a single
  small 2D filter, where host-device transfers dominate. Read the files listed at the end for
  the verified scripting API, the full operation catalogue, GUI walkthroughs and tested
  workflow scripts.
---

# CLIJ2 — GPU image processing, quick reference

> **Documented for: CLIJ2 2.5.3.5** (`clij2_-2.5.3.5.jar`), CLIJx 0.32.2.0, clij2-fft
> 2.2.0.15, clij2-assistant 2.5.1.6, on Fiji 2.16.0/ImageJ 1.54p.
> Every command, parameter, number and error message below was verified in this container
> against an **NVIDIA A100-SXM4-40GB** (OpenCL 1.2).

Menu root: **Plugins ▸ ImageJ on GPU (CLIJ2)** · Scripting: `net.haesleinhuepf.clij2.CLIJ2`

## Decide first: is the GPU worth it here?

| | |
|---|---|
| **Yes** | 3D filters on stacks · long chains of ops on one image · big batches · per-label statistics on many objects |
| **No** | one small 2D filter (transfer > saving) · deep learning (that is CUDA: cellpose, StarDist) · anything needing ROIs, overlays or calibrated units |

Measured here, 512×512×64 float32, gaussian σ=4: **CPU 1188 ms → GPU 62 ms end-to-end
(19x)**, of which only 6 ms is the kernel and 56 ms the transfers. Run
`GROOVY_BENCHMARK_GPU_VS_CPU.groovy` to get the number for the actual data before committing.

---

## ⚠ THE FIVE RULES

### Rule 1 — Verify a GPU is actually there
```groovy
import net.haesleinhuepf.clij.CLIJ
println CLIJ.getAvailableDeviceNames()   // must contain an NVIDIA device
```
CLIJ2 reaches the GPU through the **OpenCL ICD** (`/etc/OpenCL/vendors/*.icd`), which is
independent of CUDA. If only `cpu-haswell-AMD EPYC …` is listed, every "GPU" call silently
runs on POCL (CPU) — **slower than plain ImageJ**, because transfers are paid for nothing.
Report that instead of publishing POCL numbers as GPU results.

**A CUDA check does not answer this question.** `check_environment` / `nvidia-smi` /
`torch.cuda.is_available()` describe the *CUDA* stack used by cellpose and StarDist. CLIJ2
can run fine on the GPU when they report nothing, and can be stuck on the CPU when they look
healthy. The line above is the only valid test — never decline a CLIJ2 task on CUDA evidence.

### Rule 2 — Allocate every destination, and get its size and type right
Ops do not return images; they write into a buffer you create first.
```groovy
def output = clij2.create(input)                            // same size + type
def labels = clij2.create(input.getDimensions(), clij2.Float)   // label maps: ALWAYS Float
```
A wrong-size destination is **not** an error — CLIJ2 silently returns that size (verified:
256×254 blurred into a 64×64 destination gives a 64×64 image). An 8-bit label destination
silently caps at 255 objects.

⚠ **A GPU buffer is not an `ImagePlus`.** `ClearCLBuffer` has **no `getWidth()`,
`getHeight()`, `getNSlices()` or `getBitDepth()`** — calling them throws
`groovy.lang.MissingMethodException`. The only accessors are:
```groovy
long[] dims = buf.getDimensions()      // [x, y] or [x, y, z]
buf.getNativeType()                    // UnsignedByte | UnsignedShort | Float
buf.getLength(); buf.getSizeInBytes(); buf.getName()
def mip = clij2.create([dims[0], dims[1]] as long[], clij2.Float)   // ✓ 2D destination for a projection
```

### Rule 3 — Release everything, especially inside loops
```groovy
try   { input = clij2.push(imp); … }
finally { [input, mask, labels].each { if (it) clij2.release(it) } }
clij2.clear()                    // frees all buffers of this instance
println clij2.reportMemory()     // "… contains 0 images." when clean
```
Nothing is freed automatically; a forgotten `release()` in a batch loop ends in
`CL_MEM_OBJECT_ALLOCATION_FAILURE` partway through.

### Rule 4 — CLIJ2 binaries are 0/1, not 0/255
`thresholdOtsu` and friends produce **1** for foreground. `clij2.pull()` of such a mask is an
8-bit image with max = 1 and a 0–255 display range, i.e. **it looks completely black** and
`Analyze Particles` on it behaves oddly. Fix on the way out:
```groovy
def mask = clij2.pullBinary(binary)                         // → 0/255 ImagePlus
// or on the GPU:  clij2.multiplyImageAndScalar(binary, binary255, 255)
```

### Rule 5 — Script the Java API; never wrap `Ext.CLIJ2_*` in `IJ.runMacro`
```groovy
IJ.runMacro('run("CLIJ2 Macro Extensions", …); Ext.CLIJ2_gaussianBlur2D(…)')  // ✗ aborts
clij2.gaussianBlur2D(input, output, 4, 4)                                     // ✓
```
Verified: the macro-extension route returns `[aborted]`, raises `Macro canceled` and opens a
**blocking "Macro Error" dialog** — an agent run hangs there. Also avoid `#@` script
parameters (they open a dialog) and prefer the Java API over `IJ.run(imp, "… on GPU", …)`,
whose result lands in a window with an unpredictable generated title.

---

## Verified pipeline patterns

### 2D object segmentation, counting, measuring
```groovy
import net.haesleinhuepf.clij2.CLIJ2
import ij.measure.ResultsTable
def clij2 = CLIJ2.getInstance(); clij2.clear()

def input = clij2.push(IJ.openImage(path))
def bg = clij2.create(input);  clij2.topHatBox(input, bg, 15, 15, 0)          // flatten background
def labels = clij2.create(input.getDimensions(), clij2.Float)
clij2.voronoiOtsuLabeling(bg, labels, 3, 1)                                   // spot_sigma, outline_sigma
def clean = clij2.create(labels); clij2.excludeLabelsOnEdges(labels, clean)
def kept  = clij2.create(labels); clij2.excludeLabelsOutsideSizeRange(clean, kept, 50, 1e9)

int count = (int) clij2.maximumOfAllPixels(kept)      // labels are 1..N → max == count
def rt = new ResultsTable(); clij2.statisticsOfLabelledPixels(input, kept, rt)
rt.save(out + "/measurements.csv")
```
`voronoiOtsuLabeling` replaces the whole threshold → distance map → maxima → watershed chain.
Tuning: **larger `spot_sigma` = fewer objects**. (Blobs sample, σ=3/1: 73 labels, 54 after
edge removal and size filtering.)

### 3D
```groovy
clij2.median3DSphere(input, denoised, 1, 1, 1)
clij2.differenceOfGaussian3D(denoised, dog, 2, 2, 2/zRatio, 6, 6, 6/zRatio)
clij2.thresholdOtsu(dog, binary)                        // binary is UnsignedByte 0/1
clij2.connectedComponentsLabelingBox(binary, labels)    // Box = 26-connected, Diamond = 6
clij2.excludeLabelsOnEdges(labels, clean)
clij2.maximumZProjection(input, mip)                    // QC projection
```
CLIJ2 works in **pixels and ignores calibration** — divide z sigmas/radii by
`voxel_depth/voxel_width` yourself for anisotropic stacks.

### Measurements without images
```groovy
clij2.sumOfAllPixels(buf) · clij2.meanOfAllPixels(buf) · clij2.maximumOfAllPixels(buf)
clij2.standardDeviationOfAllPixels(buf)
clij2.statisticsOfLabelledPixels(intensity, labels, rt)   // 36 columns, one row per label
```
Columns include `PIXEL_COUNT` (area/volume in px), `MEAN_INTENSITY`, `CENTROID_X/Y/Z`,
`BOUNDING_BOX_*`, `MASS_CENTER_*`. **No perimeter, circularity or Feret** — for shape
descriptors pull the label map and use MorphoLibJ `Analyze Regions`.

---

## Six pitfalls that actually bite (all verified)

1. **No GPU registered** → silently runs on POCL CPU, ~8x slower than plain ImageJ. Rule 1.
2. **0/1 binaries** pulled to ImageJ look black and break downstream ImageJ steps. Rule 4.
3. **Wrong destination size/type** is silent: cropped output, or labels wrapping at 255. Rule 2.
4. **RGB input** → `RuntimeException: Only 8, 16 and 32-bit supported!` Convert first:
   `IJ.run(imp, "8-bit", "")`.
5. **`CLIJ2.getInstance("<device>")` rebuilds the singleton** — every buffer and handle
   obtained earlier becomes invalid and `clear()` then throws
   `NullPointerException … getClearCLContext() is null`. Choose the device once, at the top.
6. **Timing without a warm-up** measures OpenCL kernel compilation (~0.5–2 s), not the GPU.

Harmless noise: `N warnings generated.` on stderr from the OpenCL compiler, and
`Desktop API is not supported` when a CLIJ2-Assistant help button is clicked in this
container.

## Deprecated → current

`blur2D/blur3D` → `gaussianBlur2D/3D` · `connectedComponentsLabeling` →
`connectedComponentsLabelingBox/Diamond` · `scale` → `scale2D/3D` · `affineTransform` →
`affineTransform2D/3D` · `rotateLeft/Right` → `rotate2D/3D` · `detectMaximaBox` →
`voronoiOtsuLabeling` (segmentation) or a CLIJx `detectMaxima…`. 57 ops carry `@Deprecated`
in this build — full list in `GROOVY_API.md` §9.

## File Index

| File | Contents |
|------|----------|
| `OVERVIEW.md` | What CLIJ2 is, GPU/OpenCL requirements in this container, when the GPU pays off, CLIJ vs CLIJ2 vs CLIJx, limitations |
| `GROOVY_API.md` | **The scripting API**: push/create/pull/release, types, measurements, device selection, benchmarking, what not to do, deprecations, introspection |
| `OP_REFERENCE.md` | **All 451 CLIJ2 ops** with parameters and dimensionality, grouped by category, plus the 170 CLIJx-only ops |
| `GROOVY_WORKFLOW_NUCLEI_SEGMENTATION.groovy` | Tested 2D: top-hat → Voronoi-Otsu → cleanup → 36-column statistics → CSV + label image |
| `GROOVY_WORKFLOW_3D_SPOTS_AND_PROJECTION.groovy` | Tested 3D: median → DoG → Otsu → connected components → 3D stats → projections (runs stand-alone on a synthetic stack) |
| `GROOVY_WORKFLOW_BATCH_FOLDER.groovy` | Tested batch: folder loop with per-file error handling and correct GPU memory hygiene |
| `GROOVY_BENCHMARK_GPU_VS_CPU.groovy` | Tested: warm-up, CPU vs GPU timing, transfer overhead, verdict on whether the GPU is worth it |
| `UI_GUIDE.md` | Menu-by-menu GUI reference, ClInfo / GPU Memory Display / device switching |
| `UI_WORKFLOW_ASSISTANT.md` | Click-by-click CLIJ2-Assistant walkthrough and script export |
| `SKILL.md` | This card |
