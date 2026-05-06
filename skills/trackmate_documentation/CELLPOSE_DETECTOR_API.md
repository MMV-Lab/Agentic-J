# TrackMate-Cellpose — SCRIPTING API REFERENCE (Groovy)

All settings keys and import paths in this document have been verified against
the **installed JARs in this image** by runtime introspection
(`getDeclaredConstructor().newInstance().getDefaultSettings()` on each factory).
See `skills/_tests/test_trackmate_cellpose_introspect.groovy`.

Reference URLs (may be out-of-date for the version installed here):
- https://imagej.net/plugins/trackmate/detectors/trackmate-cellpose
- https://imagej.net/plugins/trackmate/detectors/trackmate-cellpose-advanced
- https://imagej.net/plugins/trackmate/detectors/trackmate-cellpose-sam
- https://github.com/trackmate-sc/TrackMate-Cellpose

> Requires the **TrackMate-Cellpose** Fiji update site and the `cellpose` conda
> environment at `/opt/conda/envs/cellpose` (baked into the image via Dockerfile).
>
> The image installs a **micromamba shim** at
> `/usr/local/opt/micromamba/bin/micromamba` that intercepts the calls
> TrackMate-Cellpose makes (`micromamba run -n base ...`) and routes them to the
> correct conda env. See `micromamba_shim.sh`. You normally do **not** need to
> override `CONDA_ENV` from its default value of `base`.

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
// NOTE: class is AdvancedCellposeDetectorFactory (NOT CellposeAdvancedDetectorFactory).
import fiji.plugin.trackmate.cellpose.advanced.AdvancedCellposeDetectorFactory

// Cellpose-SAM (cpsam model — Cellpose 4.x)
// NOTE: lives in the `.sam` sub-package, NOT directly under `.cellpose`.
import fiji.plugin.trackmate.cellpose.sam.CellposeSAMDetectorFactory
```

---

## CellposeDetectorFactory — Settings Keys

These are the **exact keys** returned by `getDefaultSettings()` on the JAR
installed in this image. There is **no** `CELLPOSE_PYTHON_FILEPATH`,
`CELLPOSE_MODEL_NAME`, or `CELLPOSE_CUSTOM_MODEL_FILEPATH` — those names from
older docs are silently ignored, and `TARGET_CHANNEL` of the wrong type (Integer
instead of String) raises `IllegalArgumentException` from `process()`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `CONDA_ENV` | String | `base` | Conda env name passed to the micromamba shim. Leave at `base` — the shim routes it to the real cellpose env. |
| `CELLPOSE_MODEL` | String | `cyto3` | Pretrained model string — see **Available Models** section below |
| `CELLPOSE_MODEL_FILEPATH` | String | `""` | Absolute path to a custom `.pth` model; set to `""` to use a pretrained model. **NOTE:** key is `CELLPOSE_MODEL_FILEPATH`, not `CELLPOSE_CUSTOM_MODEL_FILEPATH`. |
| `PRETRAINED_OR_CUSTOM` | String | `CELLPOSE_MODEL` | Selector — `"CELLPOSE_MODEL"` to use the pretrained string in `CELLPOSE_MODEL`, or `"CUSTOM_MODEL"` to load `CELLPOSE_MODEL_FILEPATH`. |
| `TARGET_CHANNEL` | **String** | `"0"` | 0-based channel index, **as a String**. Passing an `Integer` causes `IllegalArgumentException: 'Target channel' expects String. Got Integer`. |
| `OPTIONAL_CHANNEL_2` | **String** | `"0"` | Second channel (nuclei hint for cyto3) as String; `"0"` to skip. |
| `CELL_DIAMETER` | double | `30.0` | Expected cell diameter **in physical units** (µm if calibrated). Use `30.0d` literal in Groovy — bare `30.0` is `BigDecimal` and will fail at `process()`. |
| `USE_GPU` | boolean | `true` | Default is **true**; set `false` for CPU. Falls back silently if GPU is unavailable. |
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
    'CONDA_ENV'                : 'base',         // routed by micromamba shim
    'CELLPOSE_MODEL'           : 'cyto3',
    'CELLPOSE_MODEL_FILEPATH'  : '',
    'PRETRAINED_OR_CUSTOM'     : 'CELLPOSE_MODEL',
    'TARGET_CHANNEL'           : '0',            // String, 0-based
    'OPTIONAL_CHANNEL_2'       : '0',            // String
    'CELL_DIAMETER'            : 30.0d,          // Double — bare 30.0 is BigDecimal
    'USE_GPU'                  : false,
    'SIMPLIFY_CONTOURS'        : true,
]
settings.initialSpotFilterValue = 0.0
settings.addAllAnalyzers()

settings.trackerFactory = new SparseLAPTrackerFactory()
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
settings.trackerSettings['LINKING_MAX_DISTANCE']     = 40.0d
settings.trackerSettings['GAP_CLOSING_MAX_DISTANCE'] = 40.0d
settings.trackerSettings['MAX_FRAME_GAP']            = (Integer) 2

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

## AdvancedCellposeDetectorFactory — Additional Settings Keys

Inherits all keys from `CellposeDetectorFactory`, plus:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `FLOW_THRESHOLD` | double | `0.4` | Mean-squared-flow error cutoff. Lower = fewer, more regular shapes. `0` = disable flow validation. |
| `CELL_PROB_THRESHOLD` | double | `0.0` | Neural network confidence cutoff. Range −6 to +6. Lower = more/larger cells; higher = fewer/smaller. |
| `NO_RESAMPLE` | boolean | `false` | **Inverted-sense flag.** `false` = resample to original resolution (default, accurate). `true` = skip resampling (faster, less accurate). The legacy docs called this `RESAMPLE` with opposite polarity — that key does **not** exist. |

### Advanced example (key additions only)

```groovy
import fiji.plugin.trackmate.cellpose.advanced.AdvancedCellposeDetectorFactory
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory

settings.detectorFactory = new AdvancedCellposeDetectorFactory()
settings.detectorSettings = [
    'CONDA_ENV'                : 'base',
    'CELLPOSE_MODEL'           : 'cyto3',
    'CELLPOSE_MODEL_FILEPATH'  : '',
    'PRETRAINED_OR_CUSTOM'     : 'CELLPOSE_MODEL',
    'TARGET_CHANNEL'           : '0',
    'OPTIONAL_CHANNEL_2'       : '0',
    'CELL_DIAMETER'            : 30.0d,
    'USE_GPU'                  : false,
    'SIMPLIFY_CONTOURS'        : true,
    // Advanced-only keys:
    'FLOW_THRESHOLD'           : 0.4d,
    'CELL_PROB_THRESHOLD'      : 0.0d,
    'NO_RESAMPLE'              : false,   // false = resample (default, accurate)
]
```

---

## CellposeSAMDetectorFactory — Settings Keys

Uses the `cpsam` model from Cellpose 4.x. The micromamba shim routes
`CONDA_ENV='base'` to the `cellpose4` env (which contains the cpsam model)
when `CELLPOSE_MODEL = 'cpsam'`. Lives in
`fiji.plugin.trackmate.cellpose.sam.CellposeSAMDetectorFactory`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `CONDA_ENV` | String | `base` | Conda env (routed by the shim). |
| `CELLPOSE_MODEL` | String | `cpsam` | Model name. |
| `CELLPOSE_MODEL_FILEPATH` | String | `""` | Custom model path; `""` for the pretrained `cpsam`. |
| `PRETRAINED_OR_CUSTOM` | String | `CELLPOSE_MODEL` | `"CELLPOSE_MODEL"` or `"CUSTOM_MODEL"`. |
| `TARGET_CHANNEL` | **String** | `"0"` | 0-based channel index, as String. |
| `USE_GPU` | boolean | `true` | Enable GPU. |
| `SIMPLIFY_CONTOURS` | boolean | `true` | Smooth outlines. |

(There is no `OPTIONAL_CHANNEL_2` or `CELL_DIAMETER` for SAM — cpsam does not
need a diameter prior.)

```groovy
import fiji.plugin.trackmate.cellpose.sam.CellposeSAMDetectorFactory

settings.detectorFactory = new CellposeSAMDetectorFactory()
settings.detectorSettings = [
    'CONDA_ENV'                : 'base',
    'CELLPOSE_MODEL'           : 'cpsam',
    'CELLPOSE_MODEL_FILEPATH'  : '',
    'PRETRAINED_OR_CUSTOM'     : 'CELLPOSE_MODEL',
    'TARGET_CHANNEL'           : '0',
    'USE_GPU'                  : false,
    'SIMPLIFY_CONTOURS'        : true,
]
```

---

## Cellpose-Specific Pitfalls

### Pitfall C1 — How conda actually gets called: the micromamba shim

TrackMate-Cellpose v8+ does not invoke a Python interpreter directly. It builds a
command of the form
`/usr/local/opt/micromamba/bin/micromamba run -n <CONDA_ENV> cellpose ...`
(macOS-style hardcoded path).

This image satisfies that command with a **shell shim** at
`/usr/local/opt/micromamba/bin/micromamba` (see `micromamba_shim.sh` in the repo
root) that:
- Translates `-n base` → the real cellpose env
- Translates `-n omnipose` → the cellpose env (omnipose ships in the same env)
- Detects `--pretrained_model cpsam` and routes to the `cellpose4` env

For Groovy callers this means:

- Leave `CONDA_ENV = 'base'`. The shim handles the routing.
- **Do not** set `CELLPOSE_PYTHON_FILEPATH` (no such key — see settings table).
- **Do not** add a `/opt/miniconda3` symlink — that path is not consulted in this
  build of TrackMate-Cellpose.

Verify the shim end-to-end:
```bash
/usr/local/opt/micromamba/bin/micromamba run -n base cellpose --version
```

### Pitfall C1.5 — Groovy `BigDecimal` literals fail tracker validation

In Groovy, the literal `30.0` is a `java.math.BigDecimal`, not `Double`.
TrackMate's `checkInput()` validates the type of every settings value; passing a
`BigDecimal` for a key declared `Double` fails with:

```
Value for parameter LINKING_MAX_DISTANCE is not of the right class.
Expected java.lang.Double, got java.math.BigDecimal.
```

**Always suffix double literals with `d`** (or use explicit `(double)` casts):

```groovy
// WRONG — BigDecimal
settings.trackerSettings['LINKING_MAX_DISTANCE'] = 30.0
settings.detectorSettings['CELL_DIAMETER']       = 20.0

// CORRECT — Double
settings.trackerSettings['LINKING_MAX_DISTANCE'] = 30.0d
settings.detectorSettings['CELL_DIAMETER']       = 20.0d
settings.trackerSettings['MAX_FRAME_GAP']        = (Integer) 1
```

This applies to **every** Double-typed key (`CELL_DIAMETER`, `FLOW_THRESHOLD`,
`CELL_PROB_THRESHOLD`, all distance-based tracker keys, `RADIUS`, `THRESHOLD`,
etc.).

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

### Pitfall C5 — Tracker package changed in TrackMate v8+; use a reflection loader

TrackMate v8 moved all tracker classes from `fiji.plugin.trackmate.tracking.sparselap`
to `fiji.plugin.trackmate.tracking.jaqaman`. Using the old package causes `ClassNotFoundException`.
`SimpleSparseLAPTrackerFactory` was **moved, not removed**. Hard-coding either path is
brittle; future TrackMate versions may rename again.

`settings.trackerFactory` must always be set — `checkInput()` fails with a null tracker
even if you only intend to run detection. Symptoms:

```
The tracker factory is null.
unable to resolve class SparseLAPTrackerFactory
unable to resolve class ManualTrackerFactory
```

```groovy
// WRONG — old sparselap package; ClassNotFoundException in v8+:
import fiji.plugin.trackmate.tracking.sparselap.SparseLAPTrackerFactory

// WRONG — ManualTrackerFactory does not live at this path; never import it:
import fiji.plugin.trackmate.tracking.ManualTrackerFactory

// CORRECT (v8+ direct import — works in current builds):
import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.jaqaman.LAPUtils
```

**Recommended — version-agnostic reflection loader.** Tries each known class
name at runtime and uses whichever one resolves, so the script survives
TrackMate package renames without an edit:

```groovy
def buildTrackerFactoryAndSettings() {
    String[] candidates = [
        'fiji.plugin.trackmate.tracking.jaqaman.SparseLAPTrackerFactory',
        'fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory',
        'fiji.plugin.trackmate.tracking.jaqaman.LAPTrackerFactory',
        'fiji.plugin.trackmate.tracking.sparselap.SparseLAPTrackerFactory',
        'fiji.plugin.trackmate.tracking.sparselap.SimpleSparseLAPTrackerFactory',
    ]
    for (String cn : candidates) {
        try {
            Class cls = Class.forName(cn)
            def factory = cls.getDeclaredConstructor().newInstance()
            return [factory, factory.getDefaultSettings()]
        } catch (Throwable t) { /* try next */ }
    }
    return null
}

def bundle = buildTrackerFactoryAndSettings()
if (bundle == null) { IJ.log('[ERROR] No tracker factory available'); return }
settings.trackerFactory  = bundle[0]
settings.trackerSettings = bundle[1]
```

### Pitfall C7 — Cellpose mask is a file in /tmp, not an ImagePlus

After `trackmate.process()`, TrackMate-Cellpose does NOT open the segmentation
result as a window — it writes the Cellpose label image to a temp folder and
parses spots from it internally. Searching `WindowManager` for a "mask" image
returns nothing.

Symptom:
```
[ERROR] Could not locate Cellpose mask image generated by TrackMate-Cellpose.
```

The output lives at `/tmp/TrackMate-cellpose_<random>/<basename>_cp_masks.{png,tif}`.
Read it directly:

```groovy
def findNewestTrackMateCellposeDir() {
    def best = null; long bestT = Long.MIN_VALUE
    new File('/tmp').listFiles()?.each { d ->
        if (d.isDirectory() && d.name.startsWith('TrackMate-cellpose_')
                && d.lastModified() > bestT) {
            bestT = d.lastModified(); best = d
        }
    }
    return best
}

def findBestMaskFile(File dir) {
    dir?.listFiles()?.findAll { it.isFile() &&
        (it.name.toLowerCase() =~ /(_cp_masks|cp_masks|_masks)\.(tif|tiff|png)$/)
    }?.sort { -it.lastModified() }?.first()
}

File cpDir   = findNewestTrackMateCellposeDir()
File maskFile = findBestMaskFile(cpDir)
ImagePlus labelImp = IJ.openImage(maskFile.getAbsolutePath())
```

Convert to a binary mask with `IJ.setThreshold(labelImp, 1, 65535)` +
`IJ.run(maskImp, "Convert to Mask", "")`.

### Pitfall C8 — `SpotRoi` is not an `ij.gui.Roi`; spots may yield 0 ROIs

TrackMate's `Spot.getRoi()` returns a `fiji.plugin.trackmate.SpotRoi`, NOT an
`ij.gui.Roi`. Adding it to `RoiManager` raises:
```
RoiManager.addRoi() expected an ij.gui.Roi but received fiji.plugin.trackmate.SpotRoi
```

Even after converting via reflection (`getRoi()` / `toPolygon()`), Cellpose
detections may yield zero usable contours in some builds — you'll see
`ROIs extracted ... 0` even though `model.getSpots().getNSpots(true) > 0`.

**Don't try to extract ROIs from spots for Cellpose pipelines.** Use the mask
file from Pitfall C7 as the ground-truth output, and derive any ROIs you need
from the label image (`LabelImages.findAllLabels` + per-label processing) or
from the binary mask via `Analyze Particles…`.

### Pitfall C9 — MorphoLibJ classes may not be importable in every build

`inra.ijpb.measure.region2d.IntensityMeasures` and a few sibling classes
sometimes fail at compile time even when MorphoLibJ is installed:
```
unable to resolve class inra.ijpb.measure.region2d.IntensityMeasures
```

For label-image measurements, prefer plain pixel iteration (no MorphoLibJ
import required):

```groovy
def computeAreaCentroidPerLabel(ImagePlus labelImp) {
    def ip = labelImp.getProcessor()
    def acc = [:] // label → [count, sumX, sumY]
    for (int y = 0; y < labelImp.height; y++) {
        for (int x = 0; x < labelImp.width; x++) {
            int lbl = (int) ip.getPixelValue(x, y)
            if (lbl <= 0) continue
            def v = acc.get(lbl) ?: [0d, 0d, 0d]
            v[0]++; v[1] += x; v[2] += y
            acc.put(lbl, v)
        }
    }
    return acc
}
```

If you genuinely need MorphoLibJ, use the same reflection pattern as the
tracker loader (`Class.forName('inra.ijpb.measure.region2d.IntensityMeasures')`)
so the script degrades to the pixel-iteration fallback when the class is absent.

### Pitfall C6 — `initialSpotFilterValue` must be set
Same requirement as all TrackMate detectors: set `settings.initialSpotFilterValue`
before calling `process()`, even if `0.0`.
