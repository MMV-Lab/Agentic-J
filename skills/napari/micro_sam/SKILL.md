---
name: micro_sam
description: >-
  micro_sam ("Segment Anything for Microscopy") is a napari plugin + Python API that brings the SAM
  foundation model to microscopy, with models finetuned for light microscopy (LM), electron microscopy
  (EM), histopathology and medical imaging. Route a SEGMENTATION step here when there is NO trained
  StarDist/Cellpose model for the object, when objects are arbitrary/novel, when the data are difficult
  (EM, low contrast), or when the user wants promptable, human-in-the-loop, correctable segmentation.
  Prefer StarDist/Cellpose for standard nuclei and cells (faster, often better) — micro_sam is the
  specialist for the hard, novel or interactive cases. Installed in the `napari-mcp` conda env. TWO
  backends: interactive in the live napari viewer (backend "napari"), or headless batch (backend
  "python_data_analyst", first line `# imagentj-env: napari-mcp`). The model table, the annotator
  commands and the batch API are in the files listed at the end.
---

# micro_sam — Segment Anything for Microscopy

`micro_sam` wraps Meta's **Segment Anything (SAM)** with microscopy-finetuned models and a napari
annotation UI. It does **instance segmentation**: interactively (click a point / draw a box → mask,
then correct), or automatically over the whole image. Installed in the **`napari-mcp`** env.

**When the plugin_manager should route here** (see also `../napari_general/SKILL.md`):
- No pretrained StarDist/Cellpose model fits the object (novel/arbitrary structures).
- Difficult data where StarDist/Cellpose underperform (EM, low SNR, unusual textures).
- The user wants **promptable** or **human-in-the-loop, correctable** segmentation.
- **Do NOT** default here for ordinary fluorescence nuclei or cells — StarDist / Cellpose (BIOP)
  via `imagej_coder` are faster and usually more accurate for those.

## Backend A — headless / batch (python_data_analyst, env `napari-mcp`)

The analyst writes a script whose FIRST line selects the env. `get_predictor_and_segmenter` builds the
model once; `automatic_instance_segmentation` returns a label image (and can save it).

```python
# imagentj-env: napari-mcp
import numpy as np, tifffile
from micro_sam.automatic_segmentation import (
    get_predictor_and_segmenter, automatic_instance_segmentation,
)

image = tifffile.imread("/app/data/projects/demo/raw_images/cells.tif")   # 2D grayscale or RGB

predictor, segmenter = get_predictor_and_segmenter(
    model_type="vit_b_lm",        # LM default; see model table below
    device=None,                  # None auto-selects the GPU when available, else CPU.
                                   # Do NOT hard-code "cuda" — it crashes on the CPU-only image.
    segmentation_mode="ais",      # decoder-based Automatic Instance Segmentation (recommended)
)
labels = automatic_instance_segmentation(
    predictor=predictor, segmenter=segmenter,
    input_path=image,             # a numpy array OR a file path
    ndim=2,                       # REQUIRED when input_path is an array
    output_path="/app/data/projects/demo/processed/cells_masks.tif",  # optional: also writes the mask
    verbose=False,
)
print("objects:", len(np.unique(labels)) - 1)
```

The returned `labels` is a standard integer label image — feed it straight to `python_data_analyst`
Stage 0 measurement (`skimage.measure.regionprops_table` or `cp_measure`) exactly like a StarDist/
Cellpose mask.

## Backend B — interactive in the live napari viewer (supervisor via napari MCP)

The supervisor drives it with `mcp__napari_mcp__execute_code`. Two patterns:

**Automatic seg, then hand the user a correctable label layer:**
```python
# code passed to mcp__napari_mcp__execute_code
import numpy as np, tifffile
from micro_sam.automatic_segmentation import get_predictor_and_segmenter, automatic_instance_segmentation
img = tifffile.imread("/app/data/projects/demo/raw_images/cells.tif")
predictor, segmenter = get_predictor_and_segmenter(model_type="vit_b_lm", device=None, segmentation_mode="ais")  # device=None → GPU if available, else CPU
labels = automatic_instance_segmentation(predictor=predictor, segmenter=segmenter, input_path=img, ndim=2, verbose=False)
viewer.add_image(img, name="raw"); viewer.add_labels(labels.astype("uint32"), name="micro_sam")
```
(`viewer` is pre-bound inside napari-mcp's execute_code.)

**Full click-prompted annotator (human corrects with points/boxes):**
```python
from micro_sam.sam_annotator import annotator_2d
import tifffile
img = tifffile.imread("/app/data/projects/demo/raw_images/cells.tif")
annotator_2d(img, model_type="vit_b_lm", viewer=viewer)   # opens the micro_sam widgets in the running viewer
```
The plugin is also in the napari GUI: **Plugins → Segment Anything for Microscopy**. After the user
finishes, save the committed label layer to a TIFF so the next pipeline step can read it.

**Guiding a human through the UI → read `UI_GUIDE.md`.** It covers the annotator end-to-end for a
napari beginner: Compute Embeddings first (nothing works before it), click a point → `S` to segment →
`T` to toggle negative prompts for corrections → `C` to commit each object into `committed_objects`
(the only permanent layer), `Shift+S` to propagate through a 3D volume, plus shortcuts and embedding
caching.

## Model selection

`model_type` = a SAM backbone (`vit_t` < `vit_b` < `vit_l` < `vit_h`, bigger = slower + more accurate)
optionally suffixed with a domain finetune:

| Suffix | Domain | Use for |
|---|---|---|
| `_lm` | Light microscopy | Fluorescence / brightfield cells & nuclei — **the default (`vit_b_lm`)** |
| `_em_organelles` | Electron microscopy | Organelles / structures in EM |
| `_histopathology` | H&E histopathology | Stained tissue sections |
| `_medical_imaging` | Medical | CT / MRI-style data |
| *(none)* | Natural-image SAM | Non-microscopy fallback (`vit_b`, `vit_l`, `vit_h`) |

`segmentation_mode`: `"ais"` (decoder-based Automatic Instance Segmentation — recommended, uses the
`*_lm`/`*_em` finetuned decoder) · `"amg"` (Automatic Mask Generation — original SAM, slower, no
finetuned decoder) · `"apg"`. Default picks AIS when a decoder model is available.

## Pitfalls that actually bite

1. **`vit_t` / `vit_t_lm` (tiny) needs `mobile_sam`.** Without it: `RuntimeError: 'mobile_sam' is
   required for the vit-tiny`. It is installed in this env; if a rebuild drops it, `vit_b_lm` is the
   safe default. Tiny is the **fastest on CPU** — prefer it there once mobile_sam is present.
2. **First use downloads the checkpoint** (`vit_b_lm` ≈ 375 MB; `vit_t_lm` ≈ 40 MB) to the micro_sam
   cache. The first call is slow; later calls reuse the cache. Do this on the verification image first.
3. **GPU vs CPU — pass `device=None` and let it auto-select** (`"cuda"` if a GPU is present, else
   `"cpu"`). GPU acceleration is available only in the **GPU image build** (`USE_GPU=true`, which ships
   a CUDA torch); the default CPU image runs micro_sam on CPU. Never hard-code `device="cuda"` — it
   raises `Torch not compiled with CUDA enabled` on the CPU image. CPU is slow, so on CPU prefer the
   tiny `vit_t_lm`; on GPU `vit_b_lm`/`vit_l_lm` are fine. Confirm with `torch.cuda.is_available()`.
4. **`ndim` is REQUIRED when `input_path` is a numpy array** (2 for a plane, 3 for a z-stack). Omitting
   it on an array raises or mis-segments. For a file path it can infer.
5. **Build the model ONCE.** `get_predictor_and_segmenter` loads weights — call it once and reuse
   `(predictor, segmenter)` across a folder, never per image.
6. **The mask is a label image**, not a binary — background is 0, each object a unique integer. Cast to
   `uint32` before `viewer.add_labels`.
7. **Env is `napari-mcp`, not `main`.** A micro_sam script MUST start with `# imagentj-env: napari-mcp`;
   the main env has no micro_sam/torch. Interactive code runs in the same env via napari's execute_code.

## Files

| File | What it covers |
|---|---|
| `UI_GUIDE.md` | **Operating the interactive napari annotator**, written for someone who has never used napari: window/layer orientation, the micro_sam layers (`point_prompts`, `prompts`, `current_object`, `committed_objects`, `auto_segmentation`), the click→`S`→correct→`C` workflow, positive/negative prompts (`T`), 3D `Shift+S` propagation, tracking, keyboard shortcuts, embedding caching, saving results |
| `SCRIPT_API.md` | Verified signatures (`get_predictor_and_segmenter`, `automatic_instance_segmentation`, the annotator widgets), the full model-name list, and mode semantics |
| `WORKFLOW_AUTOMATIC_SEGMENTATION.py` | Batch script (`# imagentj-env: napari-mcp`): folder → per-image label TIFF + object counts CSV, model built once, GPU/CPU auto-select |
