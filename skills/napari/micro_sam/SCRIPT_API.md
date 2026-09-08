# micro_sam — verified API (micro_sam 1.8.2, env `napari-mcp`)

All signatures below were introspected from the installed package. Import from
`micro_sam.automatic_segmentation` (batch) and `micro_sam.sam_annotator` (interactive napari widgets).

## Batch / headless — `micro_sam.automatic_segmentation`

```python
get_predictor_and_segmenter(
    model_type: str,                         # e.g. "vit_b_lm" (see MODELS)
    checkpoint: str | os.PathLike | None = None,   # custom finetuned weights
    device: str = None,                      # "cuda" | "cpu"; None auto-selects
    segmentation_mode: Literal["amg","ais","apg"] | None = None,   # None → AIS if a decoder exists
    is_tiled: bool = False,                   # tile very large images (pair with tile_shape/halo)
    predictor=None, state=None, **kwargs,
) -> (SamPredictor, AMGBase | InstanceSegmentationWithDecoder)

automatic_instance_segmentation(
    predictor,                                # from get_predictor_and_segmenter
    segmenter,                                # from get_predictor_and_segmenter
    input_path: os.PathLike | str | np.ndarray,   # array OR image path
    output_path: str | os.PathLike | None = None, # if given, writes the label image
    embedding_path: str | os.PathLike | None = None,  # cache SAM embeddings (speeds re-runs)
    mask_path=None, key=None, mask_key=None,
    ndim: int | None = None,                  # REQUIRED for array input: 2 (plane) or 3 (z-stack)
    tile_shape: tuple[int,int] | None = None,
    halo: tuple[int,int] | None = None,
    verbose: bool = True,
    return_embeddings: bool = False,
    annotate: bool = False,
    batch_size: int = 1,
    **generate_kwargs,                        # forwarded to the mask generator
) -> np.ndarray                               # integer label image (0 = background)
```

## Interactive napari widgets — `micro_sam.sam_annotator`

Call these inside napari (via `mcp__napari_mcp__execute_code`), passing the running `viewer`:

```python
annotator_2d(image: np.ndarray, model_type="vit_b_lm", embedding_path=None,
             segmentation_result=None, tile_shape=None, halo=None,
             viewer=None, return_viewer=False, device=None, prefer_decoder=True, ...)
annotator_3d(image, model_type="vit_b_lm", viewer=None, ...)          # z-stack
annotator_tracking(image, model_type="vit_b_lm", viewer=None, ...)    # 2d + time tracking
image_series_annotator(images: list, output_folder: str, model_type="vit_b_lm",
                       is_volumetric=False, skip_segmented=True, ...)  # annotate a folder in sequence
```

The napari plugin manifest is registered as **`micro-sam`** → GUI menu **Plugins → Segment Anything for
Microscopy** (opens the same annotator widgets).

## Models — `micro_sam.util.get_model_names()`

Default = **`vit_b_lm`**. Backbone size: `vit_t` (tiny, fastest; needs `mobile_sam`) < `vit_b` (base)
< `vit_l` (large) < `vit_h` (huge; base SAM only). Domain finetunes:

```
Light microscopy (LM):     vit_t_lm  vit_b_lm  vit_l_lm         (+ *_lm_decoder for AIS)
Electron microscopy (EM):  vit_t_em_organelles  vit_b_em_organelles  vit_l_em_organelles  (+ *_decoder)
Histopathology (H&E):      vit_b_histopathology  vit_l_histopathology  vit_h_histopathology (+ *_decoder)
Medical imaging:           vit_b_medical_imaging                                            (+ _decoder)
Natural-image SAM:         vit_t  vit_b  vit_l  vit_h
```

The `*_decoder` names are the instance-segmentation decoders used by `segmentation_mode="ais"`; you
pass the plain name (e.g. `vit_b_lm`) and micro_sam loads the matching decoder automatically.

## Modes

- **`ais`** — Automatic Instance Segmentation via the finetuned decoder. Fast, recommended for LM/EM
  where a `*_lm` / `*_em` model exists.
- **`amg`** — Automatic Mask Generation (original SAM grid-of-points). Works with any backbone but is
  slower and less microscopy-aware.
- **`apg`** — Automatic Prompt Generation.
