---
name: cellpose_documentation
description: Cellpose (BIOP wrapper) is a Fiji/ImageJ plugin for deep-learning instance segmentation of cells and nuclei in 2D — cytoplasm, whole cells, bright-field, and non-star-convex objects where StarDist is weak. It runs Cellpose DIRECTLY (ch.epfl.biop.wrappers.cellpose) and returns the label image in-process as `cp.cellpose_imp`, with NO TrackMate and NO scraping of masks from /tmp. Use the pre-downloaded models in ~/.cellpose/models (cyto3, nuclei, cyto2, tissuenet, livecell, bact_*, cpsam, ...) or your own custom model file. Tune segmentation with `--cellprob_threshold` and `--flow_threshold`, which are NOT settable fields — they are passed through `additional_flags` as a COMMA-separated list of flags AND values (a space-separated string silently breaks the run and returns null labels). For bright-field images with a BRIGHT background (dark cells), invert in ImageJ first — Cellpose expects objects brighter than their background, and `--invert` is a no-op in Cellpose 4/cpsam. Use this skill for single-image (or per-frame) Cellpose segmentation. For linking objects across TIME (tracking), use TrackMate-Cellpose instead. Read the files listed at the end for the verified API, models, flags, and pitfalls.
---

# Cellpose (BIOP wrapper) — Documentation Index

The **direct** Cellpose path: the BIOP wrapper (`ch.epfl.biop.wrappers.cellpose`) runs Cellpose and hands you the label image **in-process** as `cp.cellpose_imp` — no TrackMate, no scraping masks from `/tmp`.

**When to use this vs. alternatives**
- **Cellpose (this skill)** — cytoplasm / whole cells / bright-field / irregular (non-star-convex) 2D objects, single image.
- **StarDist** — star-convex **nuclei** (fluorescence / H&E); faster, no conda subprocess.
- **TrackMate-Cellpose** — only to **link objects across time** (tracking), not for a still image.

## Which model — decide by GPU first

Check the GPU state (`check_environment`, query `"cuda"` → the **CUDA** row), then choose:

- **GPU active → prefer `cpsam` (Cellpose-SAM / Cellpose 4).** It is the most accurate, most general model. Use the **`CellposeSAM` command + `cellpose4` env** (see the Cellpose-SAM section).
- **CPU only → prefer a v3 model (`cyto3`, `nuclei`, …).** cpsam is far too slow on CPU. Use the **`Cellpose` command + `cellpose` env** (the main template below).

In one line: **cpsam is the default whenever the GPU is on; v3 (cyto3/nuclei) is the fallback** — and the preferred choice on CPU-only deployments.

## The one pattern you need — copy it, keep it linear

> **DO NOT** wrap the cellpose call in a helper method, add GPU→CPU fallback branches, or depend on a pre-opened window. Every past failure came from exactly these. `--use_gpu` already falls back to CPU on its own. Keep the call in the **main script body**; if a run fails, simplify *toward* this template — don't add structure.

```groovy
#@ Context ctx

import ch.epfl.biop.wrappers.cellpose.ij2commands.Cellpose
import ij.IJ
import ij.process.ImageConverter

def imp = IJ.openImage("/app/data/your_image.tif")   // robust for scripts; use IJ.getImage() only for the active window
if (imp == null) { println("FINAL STATUS: FAILURE - could not open image"); return }

def cp = new Cellpose()
ctx.inject(cp)                                        // REQUIRED — injects LogService/PlatformService
cp.imp              = imp
cp.env_path         = new File("/opt/conda/envs/cellpose")  // cellpose 3.1.1.2 (v3 models: cyto3, nuclei, ...)
cp.env_type         = "conda"
cp.model            = "cyto3"                          // v3 model (CPU-preferred). On GPU, prefer cpsam — see Cellpose-SAM below
cp.diameter         = 30f                              // px; 0f = auto-estimate (cyto* only)
cp.ch1              = 0                                // channel to segment (0 = grayscale)
cp.ch2              = 0                                // optional nucleus channel (0 = none)
cp.additional_flags = "--use_gpu"                     // COMMA-separated flags AND values, never spaces (see SCRIPT_API.md)
cp.verbose          = Boolean.TRUE                    // MUST set (nullable → NPE); also logs the exact cellpose command
cp.run()

def labels = cp.cellpose_imp
if (labels == null) {                                 // cellpose subprocess failed — read the verbose log above
    println("FINAL STATUS: FAILURE - cellpose returned null (see cellpose log)")
    return
}
if (labels.getBitDepth() == 32) {                     // 32-bit float labels → 16-bit WITHOUT scaling,
    ImageConverter.setDoScaling(false)                // else IDs are remapped to 0..65535 and destroyed
    IJ.run(labels, "16-bit", "")
    ImageConverter.setDoScaling(true)
}
labels.setCalibration(imp.getCalibration())           // cellpose drops calibration
labels.show()
println("FINAL STATUS: SUCCESS")
```

`cp.cellpose_imp` is a label image: background = 0, each object a unique integer 1..N (max pixel value = object count). For ROIs: `IJ.run(labels, "Label image to ROIs", "")` (same BIOP jar).

## Flags (`additional_flags`) — comma-separated, always

**This is the single most common way to break a Cellpose script.** The wrapper does
`additional_flags.split(",")` and passes the trimmed tokens to the cellpose CLI as argv. It
splits on **commas only, never on whitespace**. Every flag *and every value* is its own token:

```groovy
cp.additional_flags = "--use_gpu, --cellprob_threshold, -1.0, --flow_threshold, 0.4"  // CORRECT
cp.additional_flags = "--use_gpu --cellprob_threshold -1.0 --flow_threshold 0.4"      // WRONG
```

The wrong form does not report a flag error. cellpose's argparse rejects the whole blob with
`error: unrecognized arguments` and exits, so no masks are written, `cp.cellpose_imp` is
**null**, and the next access throws `NullPointerException ... "cellpose_t_imp" is null`. A
lone `"--use_gpu"` works only because it contains no spaces — scripts look fine until a second
flag is added.

`flow_threshold` and `cellprob_threshold` are **not fields**; `cp.flow_threshold = 0.6` throws
`MissingPropertyException`. They exist only as flags.

**Tuning (the directions are not symmetric):**

| Flag | Default | Effect |
|------|---------|--------|
| `--cellprob_threshold` | `0` (range ~ −6…6) | **lower → more and larger masks**; higher → fewer, smaller |
| `--flow_threshold` | `0.4` (range 0…~1) | flow-error QC. **higher → *more* masks pass (looser)**; lower → stricter; `0` disables |

Too many spurious background objects → raise `cellprob_threshold`, lower `flow_threshold`.
Cells split or clipped → lower `cellprob_threshold`. Raising both is the classic mistake:
raising `flow_threshold` *loosens*, it does not tighten. Full details → `SCRIPT_API.md`.

## Bright-field with a bright background (dark cells)

Cellpose expects objects **brighter** than their background. On bright-background data it will
happily segment the background instead of the cells. Invert before segmenting:

```groovy
IJ.run(imp, "Invert", "")    // then assign cp.imp = imp
```

With the v3 `Cellpose` command you may instead pass `--invert` in `additional_flags`. With
`CellposeSAM`/`cpsam` you **cannot** — `--invert` is deprecated and silently ignored in
cellpose ≥ 4.0.1, so the ImageJ-side invert is the only option.

Related: ImageJ's `Subtract Background...` assumes a *dark* background unless you pass the
`light` option. Omitting it on bright-background data estimates the background envelope from
the cells themselves and destroys them.

## GPU vs CPU

`additional_flags` selects it: `"--use_gpu"` (default) uses the GPU when present and **falls back to CPU automatically**; `""` forces CPU (use to avoid GPU contention on a shared node). Safe to leave `--use_gpu` on everywhere. To confirm the container's actual state, call `check_environment` (query `"cuda"`) and read the **CUDA** row. On GPU, cellpose logs `>>>> using GPU (CUDA)`.

**Speed & model choice:** GPU ≈ seconds → **prefer cpsam** there. On CPU, cyto3 is ~minutes per ~1 MP image (flow-dynamics dominates) and **cpsam is far too slow** (many minutes even for a small crop) → **prefer `cyto3`/`nuclei`** on CPU.

## Custom / pre-downloaded models

Set `model_path`, leave `model` empty:
```groovy
cp.model = ""
cp.model_path = new File("/home/imagentj/.cellpose/models/my_model")
```
Built-ins live in `/home/imagentj/.cellpose/models`: `cyto3`, `cyto2`, `nuclei`, `tissuenet_cp3`, `livecell_cp3`, `bact_*`, `cpsam`, … (full list + which env each needs → `SCRIPT_API.md`). Note: cyto3/nuclei expect microscopy images — on a non-cell image (e.g. a photo) they legitimately find ~0 objects; that is not a failure.

## Cellpose-SAM (cpsam) — newest, most general model (prefer this when the GPU is active)

The default choice on a GPU deployment. Use the **`CellposeSAM` command + `cellpose4` env** (cellpose 4.1.1), NOT the v3 `Cellpose`:
```groovy
import ch.epfl.biop.wrappers.cellpose.ij2commands.CellposeSAM
def cp = new CellposeSAM()
ctx.inject(cp)
cp.imp              = imp
cp.env_path         = new File("/opt/conda/envs/cellpose4")
cp.env_type         = "conda"
cp.model            = "cpsam"
cp.additional_flags = "--use_gpu"     // COMMA-separated flags AND values — see the Flags section
cp.verbose          = Boolean.TRUE
cp.run()
def labels = cp.cellpose_imp   // then null-guard + 16-bit convert exactly as in the main template
```
Differences from v3:
- **No `ch1`/`ch2`** — they are declared on the v3 `Cellpose` class only, so setting them on `CellposeSAM` throws `MissingPropertyException`. cpsam is channel-agnostic.
- **`diameter` exists but leave it at the default.** It is inherited from the shared parent class and the wrapper *always* forwards it (`--diameter 30.0`). Cellpose 4 uses it to rescale the image to its 30 px training diameter, so the default is a no-op — but a non-30 value **does** change the result. It is not "ignored".
- **GPU strongly preferred** — cpsam is very slow on CPU.
- **`--invert` does not work** (deprecated in cellpose ≥ 4.0.1). Invert in ImageJ instead.

## Pitfalls (read before generating a script)

- **No helper methods.** In Fiji's SciJava Groovy runner (`#@`-param scripts) a script-level `def`/`final` — even `@Field` — is NOT reliably visible inside a method body: referencing it throws `MissingPropertyException: No such property: X for class: script`, so `cp.run()` never happens and you get a downstream `cellpose_imp is null` NPE. Keep the call in the main body, or pass everything (`env_path`/`model`/`diameter`/`ch1`/`ch2`/flags) as method arguments.
- **`additional_flags` is COMMA-separated, never space-separated** — `"--use_gpu, --cellprob_threshold, -1.0"`, not `"--use_gpu --cellprob_threshold -1.0"`. The space form makes cellpose exit with `unrecognized arguments`, which surfaces only as null labels + `NullPointerException ... "cellpose_t_imp" is null`. Never diagnose that NPE as "bad threshold value" — check the flag string first.
- **`cellprob_threshold` / `flow_threshold` are flags, not fields.** `cp.flow_threshold = 0.6` throws `MissingPropertyException`.
- **Bright background (bright-field) → invert first.** Cellpose segments the background otherwise. `--invert` is a no-op on cpsam.
- **Always null-guard `cp.cellpose_imp`** before `getBitDepth()` (see template) — a null means the cellpose subprocess failed; check the verbose log, don't NPE.
- **`cp.verbose` MUST be set** (`Boolean.TRUE`) — it is nullable and null NPEs in `run()`.
- **32-bit labels → 16-bit WITHOUT scaling** (wrap the conversion in `setDoScaling(false)`/`(true)`), or label IDs are remapped to 0..65535 and destroyed.
- **Calibration is lost** on the output — re-apply `labels.setCalibration(imp.getCalibration())`.
- **conda activation** is handled by `BASH_ENV=/opt/conda/etc/profile.d/conda.sh` (set in `src/imagentj/imagej_context.py`); export it yourself only if running Fiji standalone.
- **Channels** use the wrapper's 1-based convention; `0` = none/grayscale.

## Files

| File | What it covers |
|------|---------------|
| `SCRIPT_API.md` | Full field reference for `Cellpose`/`CellposeSAM`, **flag syntax + threshold tuning**, bright-field handling, env config, the complete pre-downloaded model list, output handling |
| `GROOVY_WORKFLOW_CELLPOSE_SEGMENTATION.groovy` | **v3 models** — verified end-to-end: open → `Cellpose` → 16-bit labels + per-label area/centroid CSV |
| `GROOVY_WORKFLOW_CELLPOSE_SAM_SEGMENTATION.groovy` | **cpsam** — `CellposeSAM` + `cellpose4` env; no `ch1`/`ch2`, leave `diameter` alone |
