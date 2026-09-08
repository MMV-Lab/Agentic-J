# CLIJ2 — GUI reference (Fiji menus)

Menu roots (verified from the installed `plugins.config` files):

- **Plugins ▸ ImageJ on GPU (CLIJ2)** — the stable operations, grouped by category
- **Plugins ▸ ImageJ on GPU (CLIJx)** — experimental operations (labelled *(experimental)*)
- **Plugins ▸ ImageJ on GPU (CLIJ2) ▸ CLIJ Version 1.9.0.1 (deprecated)** — CLIJ1, do not use

Every command applies to the **active image window**, pushes it to the GPU, runs, and opens
the result as a **new window**. The GUI is therefore fine for exploring parameters, but for
anything reproducible use a Groovy script (`GROOVY_API.md`) or record the workflow with the
Assistant (below).

## CLIJ2 submenus and what lives in them

| Submenu | Contents (examples) |
|---|---|
| **Filter** (52 entries) | Gaussian blur 2D/3D, mean/median/minimum/maximum box & sphere, variance, standard deviation, top-hat, bottom-hat, difference of Gaussian, Laplace, Sobel, gradient X/Y/Z, entropy, non-local means (CLIJx) |
| **Filter ▸ Neighbors** | mean/median/mode/min/max of touching neighbors |
| **Binary** (46) | binary AND/OR/XOR/NOT/subtract/union/intersection, erode/dilate (box, sphere, slice-by-slice), opening/closing, fill holes, Voronoi (octagon), mask image, binary edge detection |
| **Threshold** (20) | Otsu, and the classic ImageJ auto-threshold family (Huang, Li, Mean, Triangle, Yen, …) each "on GPU", plus greater/smaller/equal-constant |
| **Labeling** (14) | Connected components (box/diamond), **Voronoi-Otsu-Labeling**, label spots, close index gaps, merge touching labels, extend labels via Voronoi |
| **Labeling ▸ Processing** (11) | label→mask, label surface, dilate/erode labels, **exclude labels touching image edges / outside size range / with values out of range** |
| **Measure** (35) | Statistics of label map (with/without background), sum/mean/min/max/std of all pixels, histogram, bounding box, center of mass, label pixel count map, mean intensity map |
| **Measure ▸ Neighbor graph** (27) | touch matrix, touch count matrix, adjacency matrix, count touching neighbors, average distance of n closest neighbors, proximal neighbor maps |
| **Measure ▸ Mesh** (22) | draw mesh between touching/proximal/n-closest labels, distance mesh |
| **Projections** (28) | maximum/minimum/mean/median/sum/standard-deviation Z projection, bounded variants, arg-maximum Z projection, X/Y projections |
| **Transform** (42) | affine 2D/3D, scale 2D/3D, rotate 2D/3D, translate, flip, transpose, resample, crop, paste, sub-stack, reslice (radial, top, left), rigid transform |
| **Image calculation** (44) | add/subtract/multiply/divide images and scalars, weighted sums, power, exponential, logarithm, absolute, min/max of two images, binary/greyscale masking |
| **Detection** (6) | detect maxima/minima (box, sphere), detect label edges, local extrema |
| **Drawing** (5) | draw sphere, box, line, distance-mesh overlays |
| **Table** / **IO** | push/pull results tables, save/load buffers |
| **Macro tools** (10) | CLIJ2 Macro Extensions registration, CLIJ2 ClInfo (device list), debug toggle |

Also directly under **Plugins ▸ ImageJ on GPU (CLIJ2)**:

| Command | What it does |
|---|---|
| **Start CLIJ2-Assistant** | opens the interactive workflow builder (see `UI_WORKFLOW_ASSISTANT.md`) |
| **GPU Memory Display** | live list of buffers on the device — the GUI form of `reportMemory()` |
| **Change OpenCL device** | pick which device CLIJ2 uses; also invalidates existing buffers |
| **Save / Load Image Data Flow** | store an Assistant workflow (also under File ▸ Save As / File ▸ Import) |
| **Interoperability ▸ Generate Icy Protocol** | export the workflow for Icy |

## Checking the GPU from the GUI

**Plugins ▸ ImageJ on GPU (CLIJ2) ▸ Macro tools ▸ CLIJ2 ClInfo** prints the full OpenCL
device list to the Log. If it shows only `cpu-haswell-AMD EPYC …` and no NVIDIA device, CLIJ2
is running on POCL (CPU) — see `OVERVIEW.md`, *GPU requirements*.

**Plugins ▸ ImageJ on GPU (CLIJ2) ▸ GPU Memory Display** is the quickest way to spot a leak
after a long GUI session: it should be empty when nothing is being processed.

## Known GUI annoyance in this container

Clicking the **documentation / "?" button** in a CLIJ2-Assistant dialog throws
`UnsupportedOperationException: Desktop API is not supported on the current platform` in the
Log. It is harmless — the container has no browser for `java.awt.Desktop` to hand the URL to.
Processing is unaffected; the online reference is at
<https://clij.github.io/clij2-docs/reference>.
