# micro_sam — Interactive napari UI Guide (micro_sam 1.8.2)

How to actually *operate* the micro_sam annotator in the live napari viewer, **written for
someone who has never used napari**. For the Python/headless API see `SCRIPT_API.md`; for
routing / when-to-use-micro_sam see `SKILL.md`.

Layer names, button labels and keyboard shortcuts below were read from the installed
`micro_sam/sam_annotator` source, so they match this container exactly.

What micro_sam does interactively: you **click on one object**, SAM produces a mask for it,
you **correct** it with more clicks, then you **commit** it. Repeat per object. It segments
**one object at a time** (plus a whole-image "automatic" button).

---

## 1. napari in 60 seconds (read this first)

The napari window has four parts:

```
┌─────────────┬──────────────────────────────┐
│ LAYER       │                              │
│ CONTROLS    │                              │
│ (top-left)  │        CANVAS                │
├─────────────┤        (your image)          │
│ LAYER LIST  │                              │
│ (bottom-left)                              │
└─────────────┴──────────────────────────────┘
              [ dimension slider — only for 3D/time ]
```

- **Layer list** (bottom-left): every piece of data is a *layer* — the image, your clicks,
  the masks. Click a layer name to **select** it.
- **Layer controls** (top-left): the tools for **whichever layer is selected**. The buttons
  change depending on the layer type. This is where you pick "add points", "draw rectangle", etc.
- **Canvas**: the image. **Mouse wheel = zoom**, **click-drag = pan** (in pan/zoom mode).
  Hold **`Space`** to temporarily pan/zoom no matter which tool is active.
- **Dimension slider** (bottom): appears only for 3D/time data — drags through z-slices or frames.

**The single most important rule:** a click only does what you want if **the right layer is
selected AND the right tool mode is active**. If clicking seems to do nothing, you almost
certainly have the wrong layer selected. This is the #1 beginner mistake.

- The **eye icon** next to a layer toggles its visibility.
- To save a layer: select it → `File → Save Selected Layers…`.

---

## 2. Launch it

- **From the napari GUI:** `Plugins → Segment Anything for Microscopy`, then choose the tool
  (2D, 3D, tracking, or image series).
- **Programmatically** (what the supervisor does via `mcp__napari_mcp__execute_code`, where
  `viewer` is already bound):
  ```python
  from micro_sam.sam_annotator import annotator_2d   # or annotator_3d / annotator_tracking
  import tifffile
  img = tifffile.imread("/app/data/projects/demo/raw_images/cells.tif")
  annotator_2d(img, model_type="vit_b_lm", viewer=viewer,
               embedding_path="/app/data/projects/demo/processed/embed.zarr")  # optional cache
  ```

The micro_sam panel appears on the right; its layers appear in the layer list.

---

## 3. The layers micro_sam creates

| Layer | Type | What it's for |
|---|---|---|
| `point_prompts` | Points | Your clicks. **Green = positive** (include this), **red = negative** (exclude this). |
| `prompts` | Shapes | **Box prompts** — draw a rectangle around an object (ellipse/polygon also work). |
| `current_object` | Labels | The mask SAM just made from your prompts — your *work in progress*, one object. |
| `auto_segmentation` | Labels | Result of the **Automatic Segmentation** button (whole image at once). |
| `committed_objects` | Labels | **Finished** objects. This is the one you save to disk (0 = background, one integer per object). |

---

## 4. Your first segmentation (2D), step by step

1. **Click "Compute Embeddings"** (in the micro_sam panel). Nothing else works until you do —
   until then you'll see *"Image embeddings are not yet computed"*. This is the slow step
   (on the `gpu-local` image it uses the A100; on the CPU image it's slow).
   *First ever run also downloads the model (~375 MB for `vit_b_lm`), so be patient once.*

2. **Select the `point_prompts` layer** in the layer list (bottom-left). Then in **layer
   controls** (top-left) click the **"Add points"** tool (the `+` icon).

3. **Click once on the object** you want. A **green** point appears = "include this".

4. **Press `S`** (or click **"Segment Object"**). A mask appears in `current_object`.

5. **Correct it if it's wrong:**
   - Mask **leaked** into neighbouring stuff → press **`T`** to switch to **negative** points
     (they turn **red**), then click on the area that should be excluded. Press **`S`** again.
   - Mask **missed** part of the object → press **`T`** back to positive (green) and click the
     missing part. Press **`S`** again.
   - Prefer a box instead? Select the **`prompts`** layer, choose the **rectangle** tool in
     layer controls, drag a box around the object, press **`S`**.
   - Want to start this object over → **`Shift + C`** ("Clear Annotations").

6. **Press `C`** ("Commit") when the object looks right. It moves into `committed_objects`
   with its own label id, and the prompts clear automatically.

7. **Repeat 3–6** for the next object. Each commit adds one more object.

8. **Save** when done — see §8.

---

## 5. Automatic segmentation (whole image at once)

Click **"Automatic Segmentation"** to segment everything in one go → fills the
`auto_segmentation` layer. Tune it under **"Automatic Segmentation Settings"**. This is the
same engine as the headless `automatic_instance_segmentation` in `SKILL.md`.

Typical combo: run **Automatic Segmentation** first, then hand-fix the objects it got wrong
using the click workflow above. Good when there are many objects.

---

## 6. 3D, tracking, and image series

**3D (`annotator_3d`)** — embeddings are computed for the whole volume:
- Use the **dimension slider** at the bottom to find a good slice.
- Prompt on that slice → **`S`** (*Segment Slice*) segments it on **that slice only**.
- **`Shift + S`** (*Segment All Slices*) **propagates the object through the volume** — it
  projects your prompt across slices and merges the per-slice masks into one 3D object.
- **`C`** to commit the 3D object.

**Tracking (`annotator_tracking`)** — 2D + time:
- Prompt on a frame → **`S`** (*Segment Frame*), then **`Shift + S`** (*Track object*) to
  follow it through time. Cell divisions are supported via the tracking settings.

**Image series (`image_series_annotator`)** — a folder, one image at a time:
- Annotate + commit, then press **`N`** (*Next Image*) to advance. Masks are written to the
  output folder as you go.

---

## 7. Keyboard shortcuts

| Key | 2D | 3D | Tracking |
|---|---|---|---|
| **`S`** | Segment Object | Segment Slice | Segment Frame |
| **`Shift + S`** | — | Segment All Slices (through volume) | Track object (through time) |
| **`C`** | Commit | Commit | Commit |
| **`Shift + C`** | Clear Annotations | Clear Annotations | Clear Annotations |
| **`T`** | Toggle point prompt **positive ↔ negative** | same | same |
| **`N`** | *(image-series only)* Next Image | | |

Plus napari's own: **`Space`** (hold) = pan/zoom, **mouse wheel** = zoom.

---

## 8. Embedding Settings (collapsible panel)

- **Model family / size** — the `vit_*` backbone + domain finetune (model table in `SKILL.md`).
- **Tiling** (`tile_shape` + `halo`) — for images too big to embed in one go; embeds in
  overlapping tiles.
- **Embeddings save path** — compute once, **reuse next session**. Reopening the same image
  then *loads* embeddings instead of recomputing the expensive step. Strongly recommended on
  the CPU image and for large/3D data.

---

## 9. Saving your results

`committed_objects` is a plain integer label image (0 = background, one integer per object).

- **In the GUI:** select the `committed_objects` layer → `File → Save Selected Layers…` → TIFF.
- **Programmatically:**
  ```python
  import tifffile
  tifffile.imwrite("/app/data/projects/demo/processed/masks.tif",
                   viewer.layers["committed_objects"].data.astype("uint32"))
  ```

Feed it straight into `python_data_analyst` measurement (`regionprops_table` / `cp_measure`) —
it behaves exactly like a StarDist/Cellpose mask.

---

## 10. Pitfalls that actually bite

1. **Nothing happens when you click.** Wrong layer selected, or wrong tool mode. Select
   `point_prompts` and activate the **"Add points"** tool. (See §1.)
2. **"Segment Object" does nothing / complains.** You skipped **Compute Embeddings** — it's
   always the first step.
3. **Only positive points used.** Beginners click green everywhere. Use **`T`** → red negative
   points to carve away leaks; that's how you fix over-segmentation.
4. **Forgetting to Commit.** `current_object` is temporary — if you prompt the next object
   without pressing **`C`**, you lose the previous one. Only `committed_objects` is permanent.
5. **Committing straight to a *file*** needs `z5py` (conda-only). The in-viewer commit always
   works — just save the `committed_objects` layer as TIFF (§9).
6. **Device:** on the `gpu-local` image it uses the A100 automatically. On the CPU image,
   prefer `vit_t_lm` and a saved `embedding_path` — `vit_b_lm` embedding is slow on CPU.
7. **Re-computing embeddings every session** is wasted time — set an **embeddings save path**.
