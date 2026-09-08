---
name: cellpose
description: >-
  Cellpose deep-learning instance segmentation of cells and nuclei via the PYTHON API, in the
  `cellpose` conda env (v3.1.1.2 + CUDA). THIS IS THE ROUTE FOR A FOLDER OF IMAGES — the model
  loads ONCE and stays resident, while the Fiji/BIOP wrapper respawns bash+conda+python and
  reloads it every call. Send batch segmentation to Python and leave only single still images
  or in-GUI work to the Fiji cellpose skill. COPY WORKFLOW_BATCH_SEGMENTATION.py and edit its
  CONFIG block — do NOT hand-write your own loop. Scripts MUST start with
  `# imagentj-env: cellpose` or they run in the main env, where cellpose is absent.
  Build models.Cellpose() ONCE outside the loop, and PASS eval() A LIST of images so it
  batches on the GPU — never call eval() once per image. Models are pre-downloaded (cyto3,
  nuclei, cyto2, tissuenet_cp3, livecell_cp3, bact_*); cpsam needs the `cellpose4` env. See
  SCRIPT_API.md for eval(), channels, thresholds and pitfalls.
---

# Cellpose (Python API) — Documentation Index

Deep-learning instance segmentation for cells and nuclei. This skill is the **Python** route.
There is also a Fiji/BIOP route (`cellpose_documentation`) — see *Which route* below.

## Non-negotiable rules for a batch

These three are the difference between a 5-minute run and a 35-minute one. All three are
**instructions, not suggestions** — a benchmark run that read this file and then hand-wrote
its own loop took 7× longer than it needed to, at 44% GPU utilisation.

1. **Copy `WORKFLOW_BATCH_SEGMENTATION.py` and edit its CONFIG block.** Do not hand-write a
   batch script. The workflow already has the model construction, batching, ragged-size
   handling and validation guards right. (cpsam → `WORKFLOW_CPSAM_BATCH_SEGMENTATION.py`.)
2. **Build the model ONCE, outside the loop.**
3. **Pass `eval()` a LIST of images — never one image at a time.** `eval()` batches
   internally and accepts a ragged list, so one call handles the whole folder:

```python
imgs = [tifffile.imread(p) for p in paths]     # ragged list is fine
masks, flows, styles = model.eval(imgs, diameter=30, channels=[0, 0])
```

   Calling `model.eval(img)` inside a `for` loop pays the tiling and flow-dynamics setup on
   every image and leaves the GPU half idle. If memory forces you to split, chunk the list
   (e.g. 32 images per call) — do not fall back to one-at-a-time.

Same rule downstream: when you relabel or match masks, build one lookup table and index it
(`lut[labels]`). Never loop over label ids doing `labels == i` — that rescans the whole array
once per object.

## Env — not optional

Every script from this skill **must** begin with:

```python
# imagentj-env: cellpose
```

Without it the script runs in the main env, where cellpose is **not installed**, and you get
`ModuleNotFoundError: No module named 'cellpose'`. Set `env: "cellpose"` on the step when you
recommend it.

The env is self-sufficient for a whole pipeline — numpy, tifffile, scikit-image, scipy, pandas,
matplotlib, opencv are all present. Only **seaborn** is missing; use matplotlib, or hand the
measurement/plot step to the main env as a separate script.

### cpsam (Cellpose-SAM) — same batching, different env and class

For **cpsam** use `# imagentj-env: cellpose4` (cellpose 4.1.1). `models.Cellpose` does not
exist there at all, and `model_type=` is accepted but silently ignored:

```python
# imagentj-env: cellpose4
from cellpose import models
model = models.CellposeModel(gpu=True)      # cpsam is the default weight
masks, flows, styles = model.eval(imgs)     # 3-tuple; imgs may be a LIST, so it still batches
```

**No diameter and no channels needed** — that is cpsam's main advantage, and it is
channel-agnostic. It is *not* ignored if you pass one, though: the default behaves like
`diameter=30` and a different value changes the result, so simply leave it out.

**Don't hand-convert the v3 workflow — copy `WORKFLOW_CPSAM_BATCH_SEGMENTATION.py`**, which
is the cpsam twin of `WORKFLOW_BATCH_SEGMENTATION.py` (same CONFIG-block structure, same
guards, already on the v4 API). Details → `SCRIPT_API.md`.

### Picking the class in this env (v3)

`models.Cellpose` bundles a size model for auto-diameter, but **only `cyto`, `cyto2`, `cyto3`
and `nuclei` ship one** — everything else raises `FileNotFoundError` on construction and needs
`models.CellposeModel` with an explicit diameter. And note a wrong model name does **not**
raise: cellpose falls back to the default model silently. The workflow script validates both.

## Which route: Python here, or the Fiji cellpose skill

| Situation | Route |
|---|---|
| **A folder / batch of images** | **HERE** (Python) |
| Images of differing sizes | **HERE** — `eval()` takes a ragged list; the Fiji T-stack route cannot |
| Segmentation feeding measurement, stats or plots | **HERE** — stays in Python end-to-end |
| ONE still image, or a mask needed live in the Fiji GUI | `cellpose_documentation` (Groovy/BIOP) |
| Linking objects across TIME (tracking) | TrackMate-Cellpose, not this |

The gap versus the Fiji/BIOP route is process overhead, not model speed: that wrapper writes
every frame to disk, spawns `bash -c "conda activate && python -m cellpose"`, re-imports torch and
reloads the weights, then reads masks back — on every call. Python does none of that. Even the
**worst** Python variant (model rebuilt inside the loop) still beats the **best** Fiji variant,
which is why folder work belongs here even if the script is imperfect.

## The one rule

**Build `models.Cellpose(...)` ONCE, outside the loop.** Each construction reloads the weights.

```python
# imagentj-env: cellpose
from cellpose import models

model = models.Cellpose(gpu=True, model_type="cyto3")   # ONCE
for img in images:                                       # then reuse
    masks, flows, styles, diams = model.eval(img, channels=[0, 0], diameter=30.0)
```

Rebuilding it per image roughly doubles the run time for no benefit.

`eval()` also accepts a **list** of images and batches internally — a small extra gain over a
per-image loop once the model is resident, and it tolerates differing image sizes.
`WORKFLOW_BATCH_SEGMENTATION.py` uses the list form.

## Workflow

`WORKFLOW_BATCH_SEGMENTATION.py` — **copy this for any folder-scale job** and edit the CONFIG
block. Folder in → one uint16 instance-label TIF per input (`<stem><suffix>.tif`) + a summary CSV
of per-image object counts. Handles multi-channel input (picks the channel axis rather than
assuming), runs one pass per compartment (nuclei + cytoplasm = two model loads total, not two per
image), chunks the list so RAM stays bounded, and fails loudly if the mask count doesn't match
the input count.

Verified end-to-end on 30 real HeLa images, two channels: 60 masks in 21.9 s wall including both
model loads and all I/O.

## Pitfalls

- **No `# imagentj-env: cellpose` header** → runs in main → `ModuleNotFoundError`. Most common
  failure by far.
- **Model built inside the loop** → reloads weights every image. The whole point of this skill.
- **`uint8` masks truncate at 255 objects.** Save labels as **uint16**. A dense field can exceed
  255, and the loss is silent.
- **`diameter` is in PIXELS and is the most result-changing parameter.** `None` auto-estimates
  (cyto* models only; the size model is not available for every model). Ask the user, or measure
  it, before accepting a default. **Two tools measure it for you — use them instead of guessing:**
  `estimate_cellpose_diameter_auto(image_paths=[<one image>], model=...)` runs the same size
  model once and reports whether it actually measured anything or silently fell back to the
  built-in default (check `reliable`); `estimate_cellpose_diameter_manual()` derives it from
  ROIs the user draws in Fiji and is the only route that detects a mixed size population and
  recommends two runs. **Unattended runs must use the automatic one** — nobody can draw ROIs.
  Estimate ONCE on a representative image and pass that fixed number for the whole folder;
  leaving `diameter=None` re-estimates on every image (a full extra inference pass each) and
  hides the fallback. Full guidance → `cellpose_documentation/SKILL.md` → *"Setting `diameter`"*.
- **A dim or empty field legitimately returns 0 objects** — verified on a real image whose blue
  channel maxed at 117. That is not a failure; lower `cellprob_threshold` if you expect objects.
- **`channels=[0, 0]`** means "the plane I passed is already single-channel". If you hand
  `eval()` a 3-channel array instead, you must use the `[cytoplasm, nucleus]` 1-based convention
  — passing a raw RGB array with `[0,0]` silently segments the wrong thing.
- **`model_type="nuclei"` is correct** — it is cellpose's official model id and resolves to the
  `nucleitorch_0` weights plus its size model. Do **not** pass `"nucleitorch_0"`; that is an
  internal weight filename and raises `FileNotFoundError: size model not found`.
- Cellpose expects objects **brighter** than background. Invert bright-field before segmenting.

## Files

| File | What it covers |
|------|---------------|
| `WORKFLOW_BATCH_SEGMENTATION.py` | **Copy this for a folder, v3 models** (cyto3, nuclei, tissuenet_cp3, …). Model loaded once, `eval(list)`, per-image uint16 masks + summary CSV. Env `cellpose` |
| `WORKFLOW_CPSAM_BATCH_SEGMENTATION.py` | **Copy this for a folder when the model is cpsam.** Same structure, but `CellposeModel`, no diameter, no channels, 3-tuple. Env `cellpose4` |
| `SCRIPT_API.md` | `eval()` signature and returns, channel conventions, model list, threshold tuning, env details |
