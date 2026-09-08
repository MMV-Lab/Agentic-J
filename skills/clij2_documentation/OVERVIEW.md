# CLIJ2 / CLIJx — GPU-accelerated image processing in Fiji

> **Documented for: CLIJ2 2.5.3.5, CLIJx 0.32.2.0, CLIJ 1.9.0.1, clij2-fft 2.2.0.15,
> clij2-assistant 2.5.1.6** on Fiji 2.16.0 / ImageJ 1.54p.
> Verified on this container against an **NVIDIA A100-SXM4-40GB (OpenCL 1.2, 40 GB)**.

## What it is

CLIJ2 runs image processing kernels on the **GPU through OpenCL**. It ships ~450 operations
(CLIJ2) plus ~170 experimental ones (CLIJx): filters, binary/morphology, thresholding,
labeling, per-label measurements, projections, transforms, image math and neighbor-graph
analysis. Everything runs on GPU memory buffers (`ClearCLBuffer`), not on `ImagePlus`
objects, so a workflow is: **push once → chain many operations → pull once**.

**OpenCL is not CUDA.** CLIJ2 does not use, need, or benefit from the CUDA/cuDNN stack that
cellpose, StarDist and PyTorch use. The two are independent: a container can have working
CUDA and still run CLIJ2 on the CPU (see *GPU requirements* below).

## When to use it — and when not to

| Situation | Use CLIJ2? |
|---|---|
| 3D neighborhood filters (median/mean/top-hat/DoG on a stack) | **Yes** — the biggest win; ~19x measured here (512×512×64, gaussian σ=4: 1188 ms CPU vs 62 ms GPU incl. transfers) |
| Long chains of operations on the same image | **Yes** — one push/pull amortised over many kernels |
| Batch of many images, same pipeline | **Yes** — but release buffers inside the loop |
| Per-label statistics on thousands of objects | **Yes** — `statisticsOfLabelledPixels` is one kernel |
| A single small 2D filter on one image | **No** — the host↔device transfer costs more than the filter saves |
| Deep-learning segmentation (cellpose, StarDist) | **No** — different stack; those use CUDA |
| Sub-pixel/geometry work needing ImageJ ROIs, overlays, calibration | **No** — CLIJ2 is calibration- and ROI-blind |

Measure before committing: `GROOVY_BENCHMARK_GPU_VS_CPU.groovy` prints the real numbers for
the machine and image at hand.

## GPU requirements in this container (important)

CLIJ2 finds devices through the **OpenCL ICD loader**, which reads `/etc/OpenCL/vendors/*.icd`.
The NVIDIA runtime mounts `libnvidia-opencl.so.1` but does **not** write that registration file,
so unless the image writes it, the only vendor is `pocl.icd` and CLIJ2 silently enumerates the
**CPU only** — every "GPU-accelerated" call then runs on POCL, which for this benchmark was
~8x *slower* than plain ImageJ because transfers are paid with no GPU behind them.

Check at the top of any CLIJ2 script:

```groovy
import net.haesleinhuepf.clij.CLIJ
println CLIJ.getAvailableDeviceNames()   // must list an NVIDIA device, not just "cpu-haswell-…"
```

Expected here: `[NVIDIA A100-SXM4-40GB ×8, cpu-haswell-AMD EPYC 7742 64-Core Processor]`.
If only the CPU is listed, the GPU is not reachable — say so in the report rather than
producing numbers that were computed on POCL. `CLIJ2.getInstance()` picks the fastest
listed device automatically (verified: it selects the A100).

## Inputs and outputs

- **Accepts:** 8-bit, 16-bit and 32-bit single-channel images and stacks. RGB is rejected
  with `RuntimeException: Only 8, 16 and 32-bit supported!` — convert first
  (`IJ.run(imp, "8-bit", "")`).
- **Ignores:** LUTs (including inverting LUTs), spatial calibration, ROIs, overlays.
  CLIJ2 sees raw pixel values in pixel units only. Anisotropic voxels must be handled by
  scaling the z parameters yourself (`sigma_z = sigma_xy / (voxel_depth/voxel_width)`).
- **Binaries are 0/1**, not 0/255 (see the pitfalls in `SKILL.md`).
- **Label maps** come back from `pull()` as 32-bit; label values are `1..N`, background 0.

## The three libraries

| Library | Prefix | Status |
|---|---|---|
| **CLIJ2** (2.5.3.5) | `CLIJ2_…` / `clij2.<op>()` | **Use this.** Stable, documented, ~450 ops |
| CLIJx (0.32.2.0) | `CLIJx_…` / `clijx.<op>()` | Experimental sandbox. Re-exports all CLIJ2 ops plus ~170 of its own; APIs may change |
| CLIJ 1.x (1.9.0.1) | `CLIJ_…` | **Deprecated** — the menu itself says so. Do not write new code against it |

57 CLIJ2/CLIJx ops carry `@Deprecated` (full list in `GROOVY_API.md`); the common traps are
`blur2D`/`blur3D` (→ `gaussianBlur2D`/`gaussianBlur3D`), `connectedComponentsLabeling`
(→ `…LabelingBox`/`…LabelingDiamond`), `detectMaximaBox` (→ `detectMaxima` family in CLIJx or
`voronoiOtsuLabeling` for segmentation), `scale` (→ `scale2D`/`scale3D`), `affineTransform`
(→ `affineTransform2D`/`3D`).

## Also installed here

- **clij2-fft 2.2.0.15** — FFT convolution and Richardson-Lucy deconvolution on GPU
  (`deconvolveRichardsonLucyFFT`, `convolveFFT`).
- **clij2-assistant 2.5.1.6** — the interactive GUI workflow builder (`UI_GUIDE.md`).
- **clijx-assistant** + bridges to MorphoLibJ / BoneJ / SimpleITK / ImageJ3DSuite / imglib2.
- **clijx-weka 0.32.1.1** — GPU pixel classification with a Weka model.
- **TrackMate_clij2 2.5.1.3** — CLIJ2-backed detectors inside TrackMate.

## Limitations

- No sub-pixel ROI/overlay interop — pull the label map and use ImageJ/MorphoLibJ for
  ROI-based work.
- 40 GB device memory here, but nothing is freed automatically: an unreleased buffer in a
  loop ends in `CL_MEM_OBJECT_ALLOCATION_FAILURE`.
- One shared singleton per JVM (`CLIJ2.getInstance()`); `getInstance("<device name>")`
  switches the device **and invalidates every buffer and instance obtained before it**.
- Kernel compilation happens on the first call of a session (~0.5–2 s) — always warm up
  before timing anything.
- OpenCL compiler chatter (`N warnings generated.`) is printed to stderr by some kernels and
  is harmless.

## Further reading

- Reference of all operations with examples: <https://clij.github.io/clij2-docs/reference>
- Main documentation site: <https://clij.github.io/>
- Cite: Haase et al., *CLIJ: GPU-accelerated image processing for everyone*,
  Nat Methods 17, 5–6 (2020).
