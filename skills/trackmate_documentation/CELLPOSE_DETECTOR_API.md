# TrackMate-Cellpose — SCRIPTING API REFERENCE (Groovy)

All patterns here are verified from:
- https://imagej.net/plugins/trackmate/detectors/trackmate-cellpose
- https://imagej.net/plugins/trackmate/detectors/trackmate-cellpose-advanced
- https://imagej.net/plugins/trackmate/detectors/trackmate-cellpose-sam
- https://github.com/trackmate-sc/TrackMate-Cellpose

> Requires the **TrackMate-Cellpose** Fiji update site and the `cellpose` conda
> environment at `/opt/conda/envs/cellpose` (baked into the image via Dockerfile).

---

## ANTI-HALLUCINATION RULE

Settings key names below are derived from the upstream source and documentation.
**If a parameter is not listed here, do not guess it.** Use the Fiji macro recorder:
`Plugins › Macros › Record…` → run the Cellpose detector once via GUI → copy the key verbatim.

---

## Detector Imports

```groovy
// Cellpose basic (cyto3, nuclei, cyto2, cyto models)
import fiji.plugin.trackmate.cellpose.CellposeDetectorFactory

// Cellpose advanced (adds flow/probability threshold controls)
import fiji.plugin.trackmate.cellpose.advanced.CellposeAdvancedDetectorFactory

// Cellpose-SAM (cpsam model — Cellpose 4.x)
import fiji.plugin.trackmate.cellpose.CellposeSAMDetectorFactory
```

---

## CellposeDetectorFactory — Settings Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `CELLPOSE_PYTHON_FILEPATH` | String | `/opt/conda/envs/cellpose/bin/python` | Path to the **Python interpreter** inside the cellpose env (preferred), or to the `conda` binary (requires knowing the env name separately) |
| `CELLPOSE_CUSTOM_MODEL_FILEPATH` | String | `""` | Absolute path to a custom `.pth` model; set to `""` to use a pretrained model |
| `CELLPOSE_MODEL` | String | `cyto3` | Pretrained model string — see **Available Models** section below |
| `CELLPOSE_MODEL_NAME` | String | `""` | Conda environment name — only relevant when `CELLPOSE_PYTHON_FILEPATH` points to the `conda` binary rather than a Python interpreter |
| `TARGET_CHANNEL` | **String** | `"0"` | Cellpose CLI channel selector (NOT 1-based ImageJ index). Values: `"0"`=grayscale, `"1"`=red, `"2"`=green, `"3"`=blue. **Must be a String** — `int` is silently rejected at `checkSettings`. |
| `OPTIONAL_CHANNEL_2` | **String** | `"0"` | Second Cellpose channel for two-channel models like `cyto3`. Values: `"0"`=don't use, `"1"`=red, `"2"`=green, `"3"`=blue. **Must be a String.** |
| `CELL_DIAMETER` | double | `30.0` | Expected cell diameter **in physical units** (µm if calibrated) |
| `USE_GPU` | boolean | `false` | Enable GPU; falls back to CPU silently if unavailable |
| `SIMPLIFY_CONTOURS` | boolean | `true` | Smooth/simplify mask outlines |

### Minimal Groovy example

```groovy
import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.Logger
import fiji.plugin.trackmate.cellpose.CellposeDetectorFactory
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory
import fiji.plugin.trackmate.features.FeatureFilter
import ij.IJ

def imp = IJ.getImage()
def model = new Model()
model.setLogger(Logger.IJ_LOGGER)

def settings = new Settings(imp)
settings.detectorFactory = new CellposeDetectorFactory()
settings.detectorSettings = [
    'CELLPOSE_PYTHON_FILEPATH'       : '/opt/conda/envs/cellpose/bin/python',
    'CELLPOSE_MODEL_NAME'            : 'cellpose',   // conda env name (safety net if plugin falls back to conda)
    'CELLPOSE_MODEL'                 : 'cyto3',
    'CELLPOSE_CUSTOM_MODEL_FILEPATH' : '',
    'TARGET_CHANNEL'                 : '0',    // STRING — Cellpose CLI: 0=gray, 1=R, 2=G, 3=B
    'OPTIONAL_CHANNEL_2'             : '0',    // STRING — 0=don't use
    'CELL_DIAMETER'                  : 30.0,   // physical units (µm)
    'USE_GPU'                        : false,
    'SIMPLIFY_CONTOURS'              : true,
]
settings.initialSpotFilterValue = 0.0
settings.addAllAnalyzers()

settings.trackerFactory = new SparseLAPTrackerFactory()
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
settings.trackerSettings['LINKING_MAX_DISTANCE']     = 40.0
settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = 40.0
settings.trackerSettings['MAX_FRAME_GAP']            = 2

def trackmate = new TrackMate(model, settings)
if (!trackmate.checkInput() || !trackmate.process()) {
    IJ.log("ERROR: " + trackmate.getErrorMessage()); return
}
IJ.log("Tracks: " + model.getTrackModel().nTracks(true))
```

---

## Available Models (Cellpose 3.1.x)

All model name strings are valid values for `CELLPOSE_MODEL`. Models are downloaded on
first use to `/home/imagentj/.cellpose/models/` (persisted via the `cellpose_models` volume).

To pre-download a model without running a full segmentation:
```bash
docker exec -it <container> /opt/conda/envs/cellpose/bin/python -c \
  "from cellpose import models; models.Cellpose(model_type='nuclei')"
```

### General-purpose models

| Model string | Best used for |
|---|---|
| `cyto3` | **Default. Super-generalist cytoplasm model.** Trained on all 9 Cellpose3 datasets. Best first choice for mammalian cell cytoplasm in fluorescence or brightfield. |
| `cyto2` | Cytoplasm model trained on user-submitted images (Cellpose 2). More diverse than `cyto` but less powerful than `cyto3`. Good fallback if `cyto3` over-segments. |
| `cyto` | Original cytoplasm model (Cellpose 1), trained only on the original Cellpose dataset. Legacy option — prefer `cyto3`. |
| `nuclei` | Nuclear segmentation. Use when staining/channel targets the nucleus (DAPI, Hoechst, H2B-GFP). Set `OPTIONAL_CHANNEL_2 = 0`. |

### Dataset-specific models (Cellpose 3)

These are fine-tuned on specific imaging modalities. Use when `cyto3` underperforms on your data type.

| Model string | Best used for |
|---|---|
| `tissuenet_cp3` | Multiplexed tissue imaging (e.g. CODEX, CyCIF). Trained on TissueNet dataset — diverse tissue types, nuclear + cytoplasm channels. |
| `livecell_cp3` | Phase-contrast live-cell imaging of cell lines. Trained on LIVECell — 8 cell lines, label-free. |
| `yeast_PhC_cp3` | Yeast cells imaged with phase-contrast microscopy. |
| `yeast_BF_cp3` | Yeast cells imaged in brightfield. |
| `bact_phase_cp3` | Bacteria imaged with phase-contrast. |
| `bact_fluor_cp3` | Fluorescently labelled bacteria. |
| `deepbacs_cp3` | Bacteria — trained on the DeepBacs dataset; wider variety of bacterial morphologies. |
| `transformer_cp3` | Transformer-backbone variant of the super-generalist model. Experimental; may outperform `cyto3` on some datasets. |

### Legacy / style-transfer models (Cellpose 2)

These use style-transfer from the original Cellpose2 training sets. Generally superseded by the `_cp3` variants.

| Model string | Best used for |
|---|---|
| `TN1`, `TN2`, `TN3` | TissueNet subsets (style variants). |
| `LC1`, `LC2`, `LC3`, `LC4` | LIVECell subsets — different cell line styles. |
| `CP`, `CPx` | Style-transfer cytoplasm models from Cellpose 2. |

### Model selection guide

```
Mammalian cells, fluorescence cytoplasm  →  cyto3
Nuclei / DAPI stain                      →  nuclei
Phase-contrast cell lines (e.g. HeLa)   →  livecell_cp3
Multiplexed tissue (CODEX, CyCIF)        →  tissuenet_cp3
Yeast, phase contrast                    →  yeast_PhC_cp3
Yeast, brightfield                       →  yeast_BF_cp3
Bacteria, phase contrast                 →  bact_phase_cp3
Bacteria, fluorescence                   →  bact_fluor_cp3
Nothing works well                       →  fine-tune cyto3 with ~500 annotated ROIs
```

---

## CellposeAdvancedDetectorFactory — Additional Settings Keys

Inherits all keys from `CellposeDetectorFactory`, plus:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `FLOW_THRESHOLD` | double | `0.4` | Mean-squared-flow error cutoff. Lower = fewer, more regular shapes. `0` = disable flow validation. |
| `CELL_PROB_THRESHOLD` | double | `0.0` | Neural network confidence cutoff. Range −6 to +6. Lower = more/larger cells; higher = fewer/smaller. |
| `RESAMPLE` | boolean | `true` | Reconstruct masks at original image resolution. Set `false` for faster (but less accurate) processing. |

### Advanced example (key additions only)

```groovy
import fiji.plugin.trackmate.cellpose.advanced.CellposeAdvancedDetectorFactory
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory

settings.detectorFactory = new CellposeAdvancedDetectorFactory()
settings.detectorSettings = [
    'CELLPOSE_PYTHON_FILEPATH'       : '/opt/conda/envs/cellpose/bin/python',
    'CELLPOSE_MODEL_NAME'            : 'cellpose',   // conda env name (safety net)
    'CELLPOSE_MODEL'                 : 'cyto3',
    'CELLPOSE_CUSTOM_MODEL_FILEPATH' : '',
    'TARGET_CHANNEL'                 : '0',    // STRING
    'OPTIONAL_CHANNEL_2'             : '0',    // STRING
    'CELL_DIAMETER'                  : 30.0,
    'USE_GPU'                        : false,
    'SIMPLIFY_CONTOURS'              : true,
    // Advanced-only keys:
    'FLOW_THRESHOLD'                 : 0.4,
    'CELL_PROB_THRESHOLD'            : 0.0,
    'RESAMPLE'                       : true,
]
```

---

## CellposeSAMDetectorFactory — Settings Keys

Uses the `cpsam` model from Cellpose 4.x. Requires the `cellpose-sam` conda environment
if installed separately; otherwise use the same `cellpose` env with a recent version.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `CELLPOSE_PYTHON_FILEPATH` | String | `/opt/conda/bin/conda` | Path to conda executable |
| `CELLPOSE_CUSTOM_MODEL_FILEPATH` | String | `""` | Custom model path; `""` for `cpsam` |
| `TARGET_CHANNEL` | **String** | `"0"` | Cellpose-SAM channel selector. Values: `"0"`=grayscale (full image), `"1"`=red, `"2"`=green, `"3"`=blue. **Must be a String.** |
| `USE_GPU` | boolean | `false` | Enable GPU |
| `SIMPLIFY_CONTOURS` | boolean | `true` | Smooth outlines |

```groovy
import fiji.plugin.trackmate.cellpose.CellposeSAMDetectorFactory

settings.detectorFactory = new CellposeSAMDetectorFactory()
settings.detectorSettings = [
    'CELLPOSE_PYTHON_FILEPATH'       : '/opt/conda/envs/cellpose/bin/python',
    'CELLPOSE_CUSTOM_MODEL_FILEPATH' : '',
    'TARGET_CHANNEL'                 : '0',    // STRING — Cellpose CLI semantics
    'USE_GPU'                        : false,
    'SIMPLIFY_CONTOURS'              : true,
]
```

---

## Cellpose-Specific Pitfalls

### Pitfall C1 — TrackMate v8+ auto-detects conda but misses `/opt/conda`

In **TrackMate-Cellpose v8+** the conda path is auto-detected by
`CLIUtils.findDefaultCondaPath()`, which searches a fixed list of paths including
`/opt/miniconda3/bin/conda`, `/opt/anaconda3/bin/conda`, etc. — but **not**
`/opt/conda/bin/conda`, which is where `continuumio/miniconda3` (our Docker base image)
installs conda.

When none of the search paths are found, it falls through to the hardcoded macOS default:
`/usr/local/opt/micromamba/bin/micromamba` — which does not exist in the container,
causing:

```
java.io.IOException: Cannot run program "/usr/local/opt/micromamba/bin/micromamba"
```

**Fix — add a symlink in the Dockerfile** (already present in this image):

```dockerfile
RUN ln -s /opt/conda /opt/miniconda3
```

This makes `/opt/miniconda3/bin/conda` resolve to the real conda binary, which
`findDefaultCondaPath()` finds on its first try. No GUI configuration or preference
setting is needed.

**DO NOT** try to set this via `PrefService` from a Groovy script — the SciJava context
is not accessible from the Fiji scripting environment in the standard way.

### Pitfall C2 — Cell diameter is in physical units
Like all TrackMate detectors, `CELL_DIAMETER` uses calibrated units (µm).
For an uncalibrated image (1 px = 1 unit), enter the diameter in pixels.

### Pitfall C3 — RGB images are rejected
Cellpose cannot accept single-channel RGB images. Convert first:
`Image › Type › RGB Stack` → `Image › Color › Channels Tool › Make Composite`.

### Pitfall C4 — Models download on first use
The first run downloads model weights (~100–300 MB) to `/home/imagentj/.cellpose/models/`.
This directory is persisted via the `cellpose_models` Docker named volume.
Subsequent runs are instant (offline).

### Pitfall C5 — Tracker package changed in TrackMate v8+

TrackMate v8 moved all tracker classes from `fiji.plugin.trackmate.tracking.sparselap`
to `fiji.plugin.trackmate.tracking.jaqaman`. Using the old package causes `ClassNotFoundException`.
`SimpleSparseLAPTrackerFactory` was **moved, not removed**.

```groovy
// WRONG (old sparselap package — causes ClassNotFoundException in v8+):
import fiji.plugin.trackmate.tracking.sparselap.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.sparselap.SparseLAPTrackerFactory

// CORRECT (v8+):
import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.jaqaman.LAPUtils
```

`settings.trackerFactory` must always be set — `checkInput()` fails with a null tracker
even if you only intend to run detection.

### Pitfall C6 — `initialSpotFilterValue` must be set
Same requirement as all TrackMate detectors: set `settings.initialSpotFilterValue`
before calling `process()`, even if `0.0`.

### Pitfall C10 — `TARGET_CHANNEL` and `OPTIONAL_CHANNEL_2` must be Strings (not int)

Unlike the LoG/DoG detectors (which use **`int` 1-based ImageJ channel**),
the Cellpose detector backs `TARGET_CHANNEL` with a string-valued
`Configurator$ChoiceArgument` whose values are Cellpose CLI channel
selectors: `"0"` (grayscale), `"1"` (red), `"2"` (green), `"3"` (blue).

```groovy
// WRONG — int silently fails or maps to a wrong default at checkSettings:
'TARGET_CHANNEL'      : 1,
'OPTIONAL_CHANNEL_2'  : 0,

// CORRECT — String, Cellpose CLI semantics (NOT 1-based ImageJ):
'TARGET_CHANNEL'      : '0',   // grayscale — use for single-channel images
'OPTIONAL_CHANNEL_2'  : '0',   // 0 = don't use second channel
```

**Verified at runtime** by reading `factory.getDefaultSettings()`:
`TARGET_CHANNEL`'s default is `"0"` of class `java.lang.String`. The
underlying `CellposeCLI.DEFAULT_TARGET_CHANNEL` field is also `String`.

For a multi-channel ImageJ image where you want only the red channel:
`'TARGET_CHANNEL': '1'`. For the cyto3 model with a nuclear hint channel:
`'TARGET_CHANNEL': '2', 'OPTIONAL_CHANNEL_2': '3'` (cyto on green, nuclei on blue).

---

## Settings-Map Key Reality Check (verified at runtime)

`factory.getDefaultSettings()` from this build (`TrackMate-Cellpose-1.0.1`)
returns ONLY these keys:

| Key | Default | Type |
|---|---|---|
| `CONDA_ENV` | `"base"` | String |
| `CELLPOSE_MODEL` | `"cyto3"` | String |
| `CELLPOSE_MODEL_FILEPATH` | `""` | String |
| `TARGET_CHANNEL` | `"0"` | String |
| `OPTIONAL_CHANNEL_2` | `"0"` | String |
| `CELL_DIAMETER` | `30.0` | Double |
| `USE_GPU` | `true` | Boolean |
| `SIMPLIFY_CONTOURS` | `true` | Boolean |
| `PRETRAINED_OR_CUSTOM` | `"CELLPOSE_MODEL"` | String |

Notes on legacy/aliased keys appearing in older examples:
- **`CELLPOSE_PYTHON_FILEPATH`** — NOT in the settings map. The python
  binary path is configured globally via the TrackMate Conda preference
  (`Edit › Options › Configure TrackMate Conda path…`) or via the
  `/opt/conda → /opt/miniconda3` symlink fix from Pitfall C1. Passing
  it in the settings map is silently ignored.
- **`CELLPOSE_MODEL_NAME`** → use `CONDA_ENV` instead. The conda env name
  defaults to `"base"`; set this explicitly to the env that has cellpose
  installed (e.g. `"cellpose"`).
- **`CELLPOSE_CUSTOM_MODEL_FILEPATH`** → the actual key value is
  `CELLPOSE_MODEL_FILEPATH` (the constant *name* contains "CUSTOM" but
  the constant *value* does not). Both names may work in some builds; use
  `CELLPOSE_MODEL_FILEPATH` to match `getDefaultSettings()` exactly.
