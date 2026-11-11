---
name: micro_sam
description: >-
  micro_sam ("Segment Anything for Microscopy") brings the SAM foundation model to microscopy,
  finetuned for light microscopy (LM), EM, histopathology and medical imaging. Route SEGMENTATION
  here when no StarDist/Cellpose model fits, objects are novel, data are hard (EM, low contrast),
  or the user wants promptable, correctable segmentation. Prefer StarDist/Cellpose for standard
  nuclei and cells. ALSO route here for FINE-TUNING — teaching the model better masks from the
  user's own corrections ("it keeps missing my cells", "learn what I mean", "train on my data"):
  the user fixes a few small tiles, never whole images, and the gain is measured before use. AND
  for OBJECT CLASSIFICATION — sorting ALREADY-segmented objects into classes (live/dead,
  infected/uninfected) from a few marked examples. Installed in the `napari-mcp` conda env; ALL
  of it, interactive annotator sessions included, runs as python_data_analyst scripts whose first
  line is `# imagentj-env: napari-mcp`.
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

import torch
# Pick the backbone from the hardware, don't hard-code it: vit_b_lm is ~9x larger
# and far slower to embed on CPU. See "Model selection" below.
MODEL = "vit_b_lm" if torch.cuda.is_available() else "vit_t_lm"

predictor, segmenter = get_predictor_and_segmenter(
    model_type=MODEL,             # vit_t_lm on CPU builds, vit_b_lm on GPU
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

> **Scope note.** This backend is for putting a finished result in front of the user, and for
> the small click-prompt session in Pattern 2. A napari session the user WORKS in for minutes —
> the object classifier (Pattern 3) and the whole fine-tuning workflow (`FINETUNING.md`) —
> belongs in a `python_data_analyst` script that opens its own window and blocks on
> `napari.run()`, not here. Those scripts are listed under Files.

> ### THE ONE RULE: never compute inside `mcp__napari_mcp__execute_code`
>
> That tool runs your code **on napari's main Qt thread**, wrapped in a hard
> `IMAGENTJ_MCP_TOOL_TIMEOUT_SECONDS` timeout (**90 s** default). So anything slow —
> model build, embeddings, segmentation — has two failure modes at once:
> the event loop stalls (viewer + whole VNC desktop freeze, no progress bar), AND the
> call dies with `TimeoutError` while the work keeps running invisibly in the server.
>
> Meanwhile `python_data_analyst` with `# imagentj-env: napari-mcp` runs in a
> supervised subprocess with a **7200 s** limit (`IMAGENTJ_SCRIPT_HARD_TIMEOUT`),
> covered by the stop button and the memory watchdog — **80x the headroom, and
> interruptible**. It is the same conda env, so the model and results are identical.
>
> **Route every heavy step there, and let MCP do only what is instant: adding a layer.**

### Pattern 1 — automatic segmentation (two steps)

**Step 1 — compute in `python_data_analyst`** (supervised, not the viewer):
```python
# imagentj-env: napari-mcp
import tifffile, torch, numpy as np
from micro_sam.automatic_segmentation import get_predictor_and_segmenter, automatic_instance_segmentation

IMG  = "/app/data/projects/demo/raw_images/cells.tif"
MASK = "/app/data/projects/demo/processed/cells_masks.tif"
MODEL = "vit_b_lm" if torch.cuda.is_available() else "vit_t_lm"

img = tifffile.imread(IMG)
predictor, segmenter = get_predictor_and_segmenter(model_type=MODEL, device=None, segmentation_mode="ais")
labels = automatic_instance_segmentation(
    predictor=predictor, segmenter=segmenter, input_path=img, ndim=2,
    output_path=MASK, verbose=False,
)
print("objects:", len(np.unique(labels)) - 1)
```

**Step 2 — display it via MCP** (a file read + a layer add; milliseconds):
```python
# code passed to mcp__napari_mcp__execute_code
import tifffile
img    = tifffile.imread("/app/data/projects/demo/raw_images/cells.tif")
labels = tifffile.imread("/app/data/projects/demo/processed/cells_masks.tif")
viewer.add_image(img, name="raw")
viewer.add_labels(labels.astype("uint32"), name="micro_sam")   # user can now correct it
```
(`viewer` is pre-bound inside napari-mcp's execute_code.)

### Pattern 2 — click-prompted annotator (human corrects with points/boxes)

The annotator cannot compute embeddings on the Qt thread without freezing — so
**precompute them to disk first**, then point the annotator at that cache.

**Step 1 — precompute embeddings in `python_data_analyst`:**
```python
# imagentj-env: napari-mcp
import torch
from micro_sam.precompute_state import precompute_state

MODEL = "vit_b_lm" if torch.cuda.is_available() else "vit_t_lm"
precompute_state(
    input_path="/app/data/projects/demo/raw_images/cells.tif",
    output_path="/app/data/projects/demo/processed/embed.zarr",   # the embedding cache
    model_type=MODEL,
    ndim=2,
)
```

**Step 2 — open the annotator against that cache via MCP** (loads, does not compute):
```python
from micro_sam.sam_annotator import annotator_2d
import tifffile, torch
img = tifffile.imread("/app/data/projects/demo/raw_images/cells.tif")
MODEL = "vit_b_lm" if torch.cuda.is_available() else "vit_t_lm"
annotator_2d(img, model_type=MODEL, viewer=viewer,
             embedding_path="/app/data/projects/demo/processed/embed.zarr",
             return_viewer=True)
```

`embedding_path` is **required practice here, not an optimisation** — without it the
annotator recomputes embeddings on the Qt thread and you are back to a frozen viewer.
Reuse the same path across sessions on the same image and startup is near-instant.

`precompute_state` also takes `precompute_amg_state=True`, which additionally caches the AMG/AIS
**decoder** state (speeds up a later "Automatic Segmentation" click in-session) — it does **NOT**
touch the ~60 s model-weight loading below, so it does not help with the 90 s MCP timeout risk.
Embeddings + a raised timeout are the only fix for that.

`return_viewer=True` is **mandatory over MCP**. Without it `annotator_2d` ends by calling
`napari.run()`, which blocks until the user closes the annotator window — so the tool call
can never return while annotation is in progress. No timeout value fixes that; the call is
designed never to return. Worse, the resulting bare `TimeoutError` kills the entire agent
turn, so you get no usable error back — just a blank "Agent error".
With `return_viewer=True` the annotator docks into the viewer `init_viewer` already created
and the call returns, leaving the widget live for the user to annotate in VNC. A second
`napari.run()` event loop would be wrong here in any case.

**Budget ~85 s for the launch, and raise the MCP cap before calling.** `return_viewer=True`
alone is not enough: `initialize_predictor` always rebuilds the model via `util.get_sam_model`
(there is no way to inject a cached predictor), and that call alone measures **~60 s for
`vit_t_lm`** — on GPU *and* CPU; it is state-dict loading, not device transfer. Measured
end-to-end through MCP with embeddings precomputed, the full `annotator_2d` launch took
**83.9 s** — inside the 90 s default by ~6 s, i.e. it straddles the limit and fails on a
slow run. Set `IMAGENTJ_MCP_TOOL_TIMEOUT_SECONDS=300` (the adapter hard-clamps to 600)
before launching an annotator. A larger backbone such as `vit_b_lm` will exceed 90 s outright.

The plugin is also in the napari GUI: **Plugins → Segment Anything for Microscopy**. After the user
finishes, save the committed label layer to a TIFF so the next pipeline step can read it.

**Guiding a human through the UI → read `UI_GUIDE.md`.** It covers the annotator end-to-end for a
napari beginner: Compute Embeddings first (nothing works before it), click a point → `S` to segment →
`T` to toggle negative prompts for corrections → `C` to commit each object into `committed_objects`
(the only permanent layer), `Shift+S` to propagate through a 3D volume, plus shortcuts and embedding
caching.

### Pattern 3 — object classifier (learn classes on image 1, apply to the rest)

Use when objects are **already segmented** and the user wants them sorted into classes —
live/dead, infected/uninfected, phenotype A/B, debris vs real. Not for producing masks.

Run **`WORKFLOW_OBJECT_CLASSIFIER.py`** via `python_data_analyst` (never over MCP — it blocks
on `napari.run()` until the user closes the window, and the Qt-thread timeout would kill it).
Point `IMAGE_DIR` at the images and `SEG_DIR` at the label masks from a prior segmentation step.

The loop the user sees: paint a dot on a few objects of each class in the `annotations` layer →
**"Train and predict"** → **`N`** → the next image comes up **already classified** → correct
whatever is wrong and press "Train and predict" again to fold the corrections in. Accumulated
features/labels and `rf.joblib` are written to the output folder, so the classifier is reusable.

> **`WORKFLOW_OBJECT_CLASSIFIER.py` is required — do not call `image_series_object_classifier`
> directly.** Stock micro_sam trains the forest and keeps it in `AnnotatorState().object_rf`, but
> its `next_image()` never applies it: it ends with `_update_image()`, which zeroes the `prediction`
> layer. Image 2 therefore comes up blank, and the following `N` *saves that blank* — images 2..N
> land on disk as all-zero label TIFFs. (micro_sam flags the gap itself: `# TODO handle cases where
> rf for the image was not trained` sits directly above `next_image`.) The workflow file patches
> `ObjectClassifier._update_image` to re-run the retained forest on each new image. Verified on
> micro_sam 1.8.2: without the patch image 2 is empty; with it, images 2 and 3 classify correctly
> and non-empty masks are saved.

**Going automatic after the first image** — the user annotates image 1 in the UI, then asks for the
rest to run hands-off. That works: the interactive session exports `rf.joblib`, and
**`WORKFLOW_OBJECT_CLASSIFIER_BATCH.py`** applies it to the remaining images headlessly via
micro_sam's own `run_prediction_with_object_classifier`. No viewer, no further clicking. Verified:
a forest trained on one image, reloaded in a fresh process, classified 12/12 objects correctly
across two unseen images. The batch script skips images the interactive session already wrote, so
hand-corrected results are never overwritten.

> **Two things to get right before promising the user an automatic run:**
> 1. **The classifier needs masks as INPUT — it never creates them.** "Segment the rest
>    automatically" is two stages: `WORKFLOW_AUTOMATIC_SEGMENTATION.py` (or StarDist/Cellpose)
>    produces the label masks, *then* the batch classifier assigns classes. If the user has no
>    masks for images 2..N, the classifier has nothing to classify.
> 2. **Use the SAME `model_type` that trained the forest.** Features are `area` + one mean per
>    SAM embedding channel, and every backbone emits 256 channels — so a forest trained with
>    `vit_t_lm` accepts `vit_b_lm` features with **no shape error** and silently predicts nonsense.
>    `WORKFLOW_OBJECT_CLASSIFIER.py` records the backbone in `classifier_meta.json` and the batch
>    script refuses a mismatch; do not bypass that check.

> **SAM point prompts do NOT transfer — do not offer this for them.** Clicking a point in
> `annotator_2d` and pressing `S` is inference-time conditioning for that ONE image: nothing is
> learned, no weights change, so there is nothing to carry to image 2. If the user says "I prompted
> the first image, now do the rest automatically", they need automatic instance segmentation
> (`WORKFLOW_AUTOMATIC_SEGMENTATION.py`), which ignores image 1's prompts entirely. Only the object
> **classifier** learns something reusable. Say so plainly rather than implying the clicks carried over.

## Model selection

`model_type` = a SAM backbone (`vit_t` < `vit_b` < `vit_l` < `vit_h`, bigger = slower + more accurate)
optionally suffixed with a domain finetune:

| Suffix | Domain | `vit_t`? | Use for |
|---|---|---|---|
| `_lm` | Light microscopy | ✅ **baked** | Fluorescence / brightfield cells & nuclei — **the default** |
| `_em_organelles` | Electron microscopy | ✅ **baked** | Organelles / structures in EM |
| `_histopathology` | H&E histopathology | ❌ none — `vit_b` is the floor (~419 MB) | Stained tissue sections |
| `_medical_imaging` | Medical | ❌ none — `vit_b` is the floor (~772 MB) | CT / MRI-style data |
| *(none)* | Natural-image SAM | ✅ but **no AIS decoder** | Non-microscopy fallback only |

**`vit_t` does not exist for every domain.** LM and EM have a tiny variant (both pre-baked);
histopathology and medical imaging start at `vit_b` and must be downloaded before use.

`segmentation_mode`: `"ais"` (decoder-based Automatic Instance Segmentation — recommended, uses the
`*_lm`/`*_em` finetuned decoder) · `"amg"` (Automatic Mask Generation — original SAM, slower, no
finetuned decoder) · `"apg"`. Default picks AIS when a decoder model is available.

> **Model choice and `segmentation_mode` are coupled — the un-suffixed models have NO decoder.**
> With a generic `vit_t`/`vit_b`/`vit_l`/`vit_h`, `segmentation_mode="ais"` raises
> `RuntimeError: ...your model does not contain a decoder`, and `segmentation_mode=None` silently
> falls back to `"amg"`. That fallback is the usual cause of an automatic run blowing past the
> 90 s MCP timeout: AIS is ~one decoder pass per image, while AMG runs the mask decoder over a
> dense grid of point prompts — hundreds to thousands of passes. If automatic segmentation is
> mysteriously slow, check you are on a `_lm`/`_em`-suffixed model, not a generic one.
>
> Interactive point/box prompting works on **every** model, decoder or not — the decoder gap only
> affects automatic mode.

**Fine-tuned / custom weights instead of a stock model:** `get_predictor_and_segmenter(checkpoint=...)`
(batch) or `checkpoint_path=`/`decoder_path=` (interactive annotators — see `SCRIPT_API.md` for the
per-function asymmetry, e.g. `image_series_annotator` has no `decoder_path`).

**PRODUCING such a checkpoint from the user's own annotations → `FINETUNING.md` and the four
`WORKFLOW_FINETUNE_*.py` scripts.** That is the route for "teach it what I mean", "it keeps missing
my cells", "train it on my data". It is a guided human-in-the-loop procedure, not a research project:
the user clicks where the tiles should sit (one field per well/condition, ~2 min) and then corrects
~8 small tiles (~20 min, and they never annotate a whole image), training takes 10-20 min on a GPU,
and the result is measured against the stock model on held-out tiles before anything downstream
uses it. Reach for it when no stock `*_lm`/`*_em`/`*_histopathology` model is
good enough on this data — not before; try the stock model first and look at the overlay.

> **A fine-tuned SAM checkpoint never reaches "the rest of the folder" on its own.**
> - **Automatic/batch** (`WORKFLOW_AUTOMATIC_SEGMENTATION.py`): the model is built ONCE, before the
>   per-image loop, from whatever `CHECKPOINT_PATH`/`checkpoint=` was passed at that call. If you
>   fine-tuned on image 1's corrected labels and want images 2..N segmented with the new weights,
>   the fine-tuning **must finish first**, then the script is (re-)run with `CHECKPOINT_PATH` set to
>   the new checkpoint. There is no auto-detection of "a newer checkpoint appeared" — verified from
>   `get_predictor_and_segmenter`'s source: it takes `checkpoint` once, at construction, full stop.
> - **Interactive** (`image_series_annotator`, the "Next Image [N]" workflow): verified from
>   `image_series_annotator.py` — the `predictor`/`decoder` are also built ONCE, before the image
>   loop starts, and `next_image()` closes over those exact same objects for every subsequent image.
>   The SAM annotator panel has no train control, so there is no way to retrain SAM mid-session:
>   finish annotating the current image (saved to `output_folder` immediately), fine-tune offline,
>   then **restart** `image_series_annotator(..., checkpoint_path=<new checkpoint>)`. The default
>   `skip_segmented=True` resumes at the first *un*-annotated image, so you don't lose that work.

**"Learn from what I mark, then do the rest" — TWO different features. Pick by what the user wants:**
- *Categorising objects that are already segmented* (live/dead, infected/uninfected, phenotype A/B)
  → the object CLASSIFIER, **Pattern 3** above. A random forest on SAM features, trained in seconds,
  no GPU hours. This is the cheap one; prefer it whenever it fits.
- *Producing better masks* (it misses cells, splits them, outlines debris) → **fine-tuning**,
  `FINETUNING.md`. ~20 min of the user's time + 10-20 min on a GPU.

Do not tell the user "micro_sam cannot learn from your annotations and apply them to the next
images" — it can, both ways, and both are implemented here as verified workflow scripts.

**Before a heavy run, a free sanity check:** the `napari-mcp` env installs `micro_sam.info` as a CLI
command — run it by **full path** (its `bin/` is not on PATH just from the `# imagentj-env` header) in
a `python_data_analyst` script:
`subprocess.run(["/opt/conda/envs/napari-mcp/bin/micro_sam.info"], capture_output=True, text=True)`.
~2 s, prints the installed version, cache directory, every supported model with its checkpoint version
tag, and whether this process actually sees a GPU. Cheaper than finding out 60 s into a launch.

## Pitfalls that actually bite

1. **`vit_t` / `vit_t_lm` (tiny) needs `mobile_sam`.** Without it: `RuntimeError: 'mobile_sam' is
   required for the vit-tiny`. It is installed in this env; if a rebuild drops it, `vit_b_lm` is the
   safe default. Tiny is the **fastest on CPU** — prefer it there once mobile_sam is present.
2. **Two models are PRE-BAKED into the image; everything else downloads on first use.**
   Baked (no download, works offline): **`vit_t_lm`** and **`vit_t_em_organelles`**, each with its AIS
   decoder — the tiny tier, ~162 MB, in `$MICROSAM_CACHEDIR` (`/home/imagentj/.cache/micro_sam`).
   These run on GPU too, so the same cache serves the CPU and GPU builds.

   Any OTHER model downloads on first use (`vit_b_*` ≈ 375 MB + decoder; `vit_b_medical_imaging`'s
   decoder is a 397 MB outlier). **Never let that first call be an interactive one** — a download
   inside `annotator_2d` freezes the viewer with no progress indicator, and an interrupted one leaves
   a partial temp file that never resumes. Warm it from a `# imagentj-env: napari-mcp` script first
   (see THE ONE RULE box under Backend B), then work on the verification image.
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
| `SCRIPT_API.md` | Verified signatures (`get_predictor_and_segmenter`, `automatic_instance_segmentation`, `precompute_state`, all four annotator widgets incl. `checkpoint_path`/`decoder_path`), the full model-name list, mode semantics, the `micro_sam.info` CLI check, and CLI entry points |
| `WORKFLOW_AUTOMATIC_SEGMENTATION.py` | Batch script (`# imagentj-env: napari-mcp`): folder → per-image label TIFF + object counts CSV, model built once, GPU/CPU auto-select |
| `WORKFLOW_OBJECT_CLASSIFIER.py` | Interactive object classifier over an image series (`# imagentj-env: napari-mcp`): annotate classes on image 1, "Train and predict", then `N` classifies each subsequent image automatically. Patches the stock `next_image()`, which otherwise leaves images 2..N blank and saves them as all-zero masks. **Use this instead of calling `image_series_object_classifier` directly.** Exports `rf.joblib` + `classifier_meta.json` |
| `FINETUNING.md` | **Teaching the model on the user's own annotations**, end to end: why the user annotates small tiles instead of whole images, the four stages, the exact words to guide the human through the napari annotator, and the verified pitfalls (SAM's 1024 px resize and why inference must be tiled at the annotation tile size; 16-bit input failing micro_sam's own loader check; commit refusing to overwrite an existing object; the broken `T` shortcut in 1.8.2) |
| `WORKFLOW_FINETUNE_1_PREPARE.py` | Stage 1: **the user clicks the tiles** in a napari picker that walks one field per group (`GROUP_REGEX` — per well, per condition, per sub-folder) **with the stock model's current segmentation painted on it, so they can aim at what it gets wrong**; the tile size is MEASURED from object density, not fixed. Then pre-segment each tile and write `manifest.json` + generated human instructions. `PICK_MODE="auto"` falls back to a content heuristic for unattended runs |
| `WORKFLOW_FINETUNE_2_ANNOTATE.py` | Stage 2: the annotator with an ADD/DRAW/DELETE helper panel docked in, plus a switch that commits drawn shapes as outlines without micro_sam; logs every commit's prompts to `prompt_log/`; blocks until the user closes it, then prints a per-tile status table. Resumes an interrupted session |
| `WORKFLOW_FINETUNE_3_TRAIN.py` | Stage 3: validate the annotations, split by source image, train (encoder + AIS decoder), export, then measure **stock vs fine-tuned on held-out tiles** and name the winner in `evaluation.json` |
| `WORKFLOW_FINETUNE_4_APPLY.py` | Stage 4: segment the whole folder with whichever model stage 3 measured as better, tiled at the training scale so the fine-tuning actually applies |
| `WORKFLOW_OBJECT_CLASSIFIER_BATCH.py` | Headless counterpart: applies the `rf.joblib` from an interactive session to the rest of the folder with no viewer. Requires label masks as input (it classifies, never segments) and pins the backbone to the one that trained the forest — a mismatch misclassifies silently instead of erroring |
