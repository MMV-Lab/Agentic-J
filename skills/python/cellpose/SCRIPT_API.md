# Cellpose Python API — verified reference

Verified against the installed package in the `cellpose` conda env on this deployment:
**cellpose 3.1.1.2**, torch **2.11.0+cu126**, CUDA available. All identifiers below were
checked by importing them, not from upstream docs.

Every script using this API must start with `# imagentj-env: cellpose`.

## Constructing a model

```python
from cellpose import models

model = models.Cellpose(gpu=True, model_type="cyto3")
```

- **Build it ONCE**, outside any loop. Construction reloads weights from disk.
- `models.Cellpose` bundles a size model (diameter estimation) with the segmentation model.
  `models.CellposeModel` is the segmentation model alone — use it when you always pass an
  explicit `diameter` and don't need auto-estimation.
- `gpu=True` falls back to CPU if no GPU is present; it does not raise.

### Model names

`models.MODEL_NAMES` on this install:

```
cyto3, nuclei, cyto2_cp3, tissuenet_cp3, livecell_cp3, yeast_PhC_cp3, yeast_BF_cp3,
bact_phase_cp3, bact_fluor_cp3, deepbacs_cp3, cyto2, cyto, CPx, transformer_cp3,
neurips_cellpose_default, neurips_cellpose_transformer, neurips_grayscale_cyto2,
CP, TN1, TN2, TN3, LC1, LC2, LC3, LC4
```

Common choices: `cyto3` (general cells/cytoplasm, current default), `nuclei` (fluorescent
nuclei), `cyto2` (previous generation), `tissuenet_cp3` (tissue/multiplexed),
`livecell_cp3` (label-free/phase), `bact_*` (bacteria).

**`"nuclei"` is the correct id for nuclei.** It resolves to
`/home/imagentj/.cellpose/models/nucleitorch_0` plus the size model `size_nucleitorch_0.npy`,
and sets `diam_mean=17.0`. Passing the weight filename `"nucleitorch_0"` instead raises:

```
FileNotFoundError: size model not found (nucleitorch_0_size.npy)
```

Weights are pre-downloaded in `/home/imagentj/.cellpose/models` — no network needed.

### Which class — this decides whether your script runs at all

`models.Cellpose` needs a bundled size model, and **only four models ship one**:
`cyto`, `cyto2`, `cyto3`, `nuclei`. For every other model it raises
`FileNotFoundError: size model not found` on construction. Use `models.CellposeModel`
(segmentation net alone, explicit `diameter`) for all the rest — verified working with
`cyto2_cp3`, `tissuenet_cp3`, `livecell_cp3`, `yeast_PhC_cp3`, `yeast_BF_cp3`,
`bact_phase_cp3`, `bact_fluor_cp3`, `deepbacs_cp3`, `neurips_grayscale_cyto2`,
`CP`, `CPx`, `TN1`–`TN3`, `LC1`–`LC4`, and `nucleitorch_0`.

So: **`diameter=None` (auto-estimate) is only possible on those four models.** Any other
model requires an explicit diameter.

**Broken on this install** — listed by `models.MODEL_NAMES` but failing to load under
either class with a state-dict/weight error: `neurips_cellpose_default`,
`neurips_cellpose_transformer`, `transformer_cp3`. Don't use them.

### A wrong model name does NOT raise

Passing a name cellpose doesn't know prints `model_type does not exist, using default
model` to stdout and **silently segments with the default model instead**. You get
plausible masks from the wrong network. `tissuenet` and `livecell` (the bare names, without
the `_cp3` suffix) are exactly this trap. Validate the name against the list above before
constructing — `WORKFLOW_BATCH_SEGMENTATION.py` does.

### cpsam (Cellpose-SAM) — different env, different API

**cpsam is not in this env.** It needs `# imagentj-env: cellpose4` (cellpose 4.1.1), where
`models.Cellpose` **does not exist at all** and `model_type=` is accepted but ignored with a
warning. It is the default weight, so you need no model argument, and no diameter:

```python
# imagentj-env: cellpose4
from cellpose import models

model = models.CellposeModel(gpu=True)      # pretrained_model="cpsam" is the default
masks, flows, styles = model.eval(imgs)     # 3-tuple; imgs may be a LIST (batches like v3)
```

- **No `diameter` needed** — omitting it is the intended use, and cpsam is channel-agnostic
  so `channels=` is unnecessary too.
- **But `diameter` is not ignored if you pass one.** The default behaves like `diameter=30`;
  passing a different value changes the segmentation. Leave it out unless you mean it.
- `eval()` takes a list and batches internally, so the batch structure of
  `WORKFLOW_BATCH_SEGMENTATION.py` carries over — swap the class, drop `diameter`/`channels`,
  and take a 3-tuple instead of 4.

## `eval()`

```python
masks, flows, styles, diams = model.eval(
    x,                          # 2D array, or a LIST of 2D arrays
    channels=[0, 0],
    diameter=30.0,              # PIXELS; None = auto-estimate
    flow_threshold=0.4,
    cellprob_threshold=0.0,
)
```

Returns a 4-tuple. With a list input, `masks` is a list in the same order.
(`models.CellposeModel.eval` returns a 3-tuple — no `diams`.)

### `channels`

`[cytoplasm_channel, nucleus_channel]`, **1-based**, `0` meaning grayscale:

- `[0, 0]` — the array passed is already a single 2D plane. **Use this**, having extracted the
  channel yourself. Clearest and least error-prone.
- `[1, 3]` — a 3-channel array: segment channel 1 (red) using channel 3 (blue) as the nuclear
  channel.

Passing a raw RGB array with `[0, 0]` does **not** error — it segments a grayscale reduction of
it, silently giving the wrong result. Extract the plane explicitly.

### `diameter`

The single most result-changing parameter, in **pixels**.

- A number: used as-is.
- `None`: auto-estimated by the size model. Only available for models that ship one — for others
  it fails or falls back to `diam_mean`.

Ask the user for an estimate, or measure it, rather than accepting a default.

### Thresholds

- `cellprob_threshold` (default `0.0`, range ~-6..6) — **lower = more and larger masks.** Raise
  it if background is being segmented; lower it if objects are missed.
- `flow_threshold` (default `0.4`) — flow-error QC. **Higher = looser = more masks kept.** Lower
  it to discard ill-formed masks.

A legitimately dim or empty field returns **0 objects**; that is not an error.

## Output handling

`masks` is an integer array: `0` = background, `1..N` = object instances, so `masks.max()` is
the object count.

**Save as `uint16`.** `uint8` truncates at 255 objects, silently.

```python
import numpy as np, tifffile
tifffile.imwrite(path, np.asarray(masks).astype(np.uint16))
```

To measure, hand the label image to `skimage.measure.regionprops_table` — note `regionprops`
raises on a boolean mask, and its areas are in pixels unless you pass `spacing=`.

## Performance

Ranked best to worst, for the same folder:

1. **built once, `eval(list)`** — model resident, batching handled internally. Use this.
2. **built once, `eval()` per image** — nearly as good; the list form adds only a small gain.
3. **`models.Cellpose()` inside the loop** — reloads the weights every iteration, roughly doubling
   the run for no benefit. This is the mistake to avoid.

All three still beat the Fiji/BIOP wrapper, whose cost is process spawning and disk round-trips
rather than the model itself.

`eval(list)` batches internally and tolerates images of **differing sizes** — the Fiji T-stack
route requires uniform dimensions.

## Env contents

`numpy` 2.0.2 · `tifffile` 2025.5.10 · `scikit-image` 0.25.2 · `scipy` 1.15.3 · `pandas` 2.3.3 ·
`matplotlib` 3.10.9 · `opencv` 5.0.0 · `torch` 2.11.0+cu126. **No seaborn** — use matplotlib, or
run the plotting step in the main env.
