# MIST — Scripting and Automation Reference

---

## ⚠️ Critical: MIST Has No IJ.run() Scripting API

MIST is **not scriptable via `IJ.run()` macro calls** from within Fiji scripts or the ImageJ Macro Language. Unlike many Fiji plugins (e.g. StarDist, MorphoLibJ), MIST does not expose a SciJava `@Plugin` Command that can be invoked programmatically from a Groovy or IJ macro script.

**The supported automation pathways are:**

1. **Parameter file (GUI automation)** — save all parameters to a `.txt` file via "Save Params", then reload with "Load Params" to reproduce a run
2. **Standalone executable JAR invoked from Python** — run MIST outside Fiji entirely, fully headless, by calling `java -jar MIST.jar ...` via Python's `subprocess` module
3. **Docker container** — the official WIPP Docker image (`wipp/mist`) wraps the JAR for containerised/cloud execution

> **Agent note**: MIST cannot be called from a Groovy script running inside Fiji (no `IJ.run()` API exists). Python (`subprocess.run`) is the correct automation language for this plugin. The workflow script `COMMANDLINE_WORKFLOW_STITCHING.py` is the ready-to-use implementation.

The rest of this document covers all three approaches with verified parameters only.

---

## Approach 1 — Parameter Files

The parameter file is a plain-text key-value format. MIST writes one automatically as `{prefix}statistics.txt` at the end of every run. This file can be re-loaded via "Load Params" to reproduce the exact run.

### How to generate a parameter file

1. Set all parameters manually in the GUI
2. Click **Save Params** on the Input tab
3. Provide a filename (e.g. `my-experiment-params.txt`)

### Format of the parameter file

The file uses `key: value` pairs, one per line. Example from a Row-Column dataset:

```
filenamePattern: img_r{rrr}_c{ccc}.tif
filenamePatternType: ROWCOL
gridWidth: 5
gridHeight: 5
startRow: 1
startCol: 1
gridOrigin: UL
imageDir: /data/experiment01/tiles
outputPath: /data/experiment01/output
displayStitching: true
outputFullImage: true
outFilePrefix: exp01_
blendingMode: OVERLAY
blendingAlpha: -1
```

### Editing parameter files for batch runs

To batch-process multiple datasets that share the same grid layout but different directories, create one validated parameter file, then use a Python script to copy and edit the `imageDir` and `outputPath` lines for each dataset before loading it in the GUI. Alternatively, use the JAR-based Python workflow (Approach 2) which handles this directly in code.

---

## Approach 2 — Standalone JAR via Python (`subprocess`)

The standalone JAR (`MIST_-{version}-jar-with-dependencies.jar`) runs MIST completely outside Fiji, with no GUI. Python invokes it using `subprocess.run()`, passing all parameters as a list of `--key value` strings. This is the primary path for agent-driven and batch automation.

The ready-to-use implementation is `COMMANDLINE_WORKFLOW_STITCHING.py`. The sections below document the full parameter set so the agent can construct or modify calls as needed.

### Building the JAR

The JAR must be compiled from source (it is not distributed as a pre-built download):

```bash
git clone https://github.com/usnistgov/MIST.git
cd MIST
mvn package
# Output: MIST/target/MIST_-{version}-jar-with-dependencies.jar
```

Requires: Java 8+, Maven.

Alternatively, use the official Docker image which contains a pre-built JAR — see Approach 3.

---

### Command-Line Parameters

All parameters are passed as `--key value` pairs. Parameters marked **(required)** must be present; others are optional.

#### Core Required Parameters (all modes)

| Parameter | Values | Description |
|-----------|--------|-------------|
| `--filenamePattern` | string | Filename pattern using tokens; e.g. `img_r{rrr}_c{ccc}.tif` |
| `--filenamePatternType` | `ROWCOL` / `SEQUENTIAL` | Pattern type |
| `--gridHeight` | integer | Number of rows in the tile grid |
| `--gridWidth` | integer | Number of columns in the tile grid |
| `--imageDir` | path | Full path to directory containing tiles |
| `--programType` | `AUTO` / `JAVA` / `FFTW` | FFT execution engine (FFTW strongly recommended) |

#### Required for Row-Column (`ROWCOL`) mode

| Parameter | Values | Description |
|-----------|--------|-------------|
| `--gridOrigin` | `UL` / `UR` / `LL` / `LR` | Grid corner where acquisition began |
| `--startRow` | integer | Smallest row index present in filenames |
| `--startCol` | integer | Smallest column index present in filenames |

#### Required for Sequential (`SEQUENTIAL`) mode

| Parameter | Values | Description |
|-----------|--------|-------------|
| `--gridOrigin` | `UL` / `UR` / `LL` / `LR` | Grid corner where acquisition began |
| `--numberingPattern` | `VERTICALCOMBING` / `VERTICALCONTINUOUS` / `HORIZONTALCOMBING` / `HORIZONTALCONTINUOUS` | Scan path direction |
| `--startTile` | integer | Starting tile index (the number in the first tile filename) |

#### Required when `--programType FFTW`

| Parameter | Values | Description |
|-----------|--------|-------------|
| `--fftwLibraryFilename` | e.g. `libfftw3f.dll` | Filename of the FFTW shared library |
| `--fftwLibraryName` | e.g. `libfftw3f` | Library name (without extension) |
| `--fftwLibraryPath` | path | Directory containing the FFTW library |

> **Note**: On Windows, `libfftw3f.dll` is bundled with the Fiji installation at `Fiji.app/lib/fftw/`. On Linux/macOS, it is at `/usr/local/lib/` after standard FFTW installation.

#### Optional Output Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--outputPath` | image directory | Directory for all output files |
| `--outFilePrefix` | (empty) | Prefix prepended to all output filenames |
| `--displayStitching` | `false` | Display result in a GUI window (not useful headless) |
| `--outputFullImage` | `true` | Write the full mosaic .tif to disk |
| `--blendingMode` | `OVERLAY` | `OVERLAY` / `LINEAR` / `AVERAGE` |
| `--blendingAlpha` | `-1` | Alpha for Linear blending; `-1` = auto |

#### Optional Advanced Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--stageRepeatability` | auto | Stage repeatability in pixels (overrides automatic estimate) |
| `--horizontalOverlap` | auto | Horizontal overlap percentage (overrides automatic estimate) |
| `--verticalOverlap` | auto | Vertical overlap percentage (overrides automatic estimate) |
| `--overlapUncertainty` | `5` | Overlap uncertainty in percent |
| `--numFFTPeaks` | `2` | Number of PCM peaks to check (1–10) |
| `--translationRefinementMethod` | `SINGLE_HILL_CLIMB` | `SINGLE_HILL_CLIMB` / `MULTI_POINT_HILL_CLIMB` / `EXHAUSTIVE` |
| `--numTranslationRefinementStartPoints` | `16` | Starting points for multipoint hill climb |
| `--isUseBioFormats` | `false` | Use BioFormats reader instead of ImageJ reader |
| `--isUseDoublePrecision` | `false` | Use 64-bit double precision |
| `--logLevel` | `MANDATORY` | `NONE` / `MANDATORY` / `HELPFUL` / `INFO` / `VERBOSE` |
| `--debugLevel` | `NONE` | `NONE` / `MANDATORY` / `HELPFUL` / `INFO` / `VERBOSE` |

---

### Example Invocations (Python `subprocess`)

#### Row-Column dataset, FFTW, Linux/macOS

```python
import subprocess

result = subprocess.run([
    "java", "-jar", "/path/to/MIST_-2.1-jar-with-dependencies.jar",
    "--filenamePattern",     "img_r{rrr}_c{ccc}.tif",
    "--filenamePatternType", "ROWCOL",
    "--gridHeight",          "5",
    "--gridWidth",           "5",
    "--gridOrigin",          "UL",
    "--startRow",            "1",
    "--startCol",            "1",
    "--imageDir",            "/data/experiment01/tiles",
    "--outputPath",          "/data/experiment01/output",
    "--programType",         "FFTW",
    "--fftwLibraryFilename", "libfftw3.so",
    "--fftwLibraryName",     "libfftw3",
    "--fftwLibraryPath",     "/usr/local/lib",
], text=True)
print("Exit code:", result.returncode)
```

#### Row-Column dataset, FFTW, Windows

```python
import subprocess

result = subprocess.run([
    "java", "-jar", r"C:\path\to\MIST_-2.1-jar-with-dependencies.jar",
    "--filenamePattern",     "img_r{rrr}_c{ccc}.tif",
    "--filenamePatternType", "ROWCOL",
    "--gridHeight",          "5",
    "--gridWidth",           "5",
    "--gridOrigin",          "UL",
    "--startRow",            "1",
    "--startCol",            "1",
    "--imageDir",            r"C:\data\experiment01\tiles",
    "--outputPath",          r"C:\data\experiment01\output",
    "--programType",         "FFTW",
    "--fftwLibraryFilename", "libfftw3f.dll",
    "--fftwLibraryName",     "libfftw3f",
    "--fftwLibraryPath",     r"C:\Fiji.app\lib\fftw",
], text=True)
print("Exit code:", result.returncode)
```

#### Sequential dataset, Java engine, known overlap

```python
import subprocess

result = subprocess.run([
    "java", "-jar", "/path/to/MIST_-2.1-jar-with-dependencies.jar",
    "--filenamePattern",     "scan_{ppp}.tif",
    "--filenamePatternType", "SEQUENTIAL",
    "--gridHeight",          "4",
    "--gridWidth",           "4",
    "--gridOrigin",          "UL",
    "--numberingPattern",    "HORIZONTALCOMBING",
    "--startTile",           "1",
    "--imageDir",            "/data/scans/tiles",
    "--outputPath",          "/data/scans/output",
    "--horizontalOverlap",   "15",
    "--verticalOverlap",     "15",
    "--overlapUncertainty",  "5",
    "--programType",         "JAVA",
    "--logLevel",            "HELPFUL",
], text=True)
print("Exit code:", result.returncode)
```

> **Important**: always pass parameters as a Python **list** (not a single string) to `subprocess.run()`. This avoids shell quoting issues, particularly with the `{rrr}` tokens in filename patterns which shells may try to interpret as brace expansions.

---

## Approach 3 — Docker Container

The WIPP Docker image provides a pre-built MIST JAR without requiring compilation. The agent can invoke it via `subprocess.run()` exactly as with the JAR directly.

```python
import subprocess

result = subprocess.run([
    "docker", "run", "--rm",
    "-v", "/local/data:/data",
    "wipp/mist:2.0.7",
    "--filenamePattern",     "img_r{rrr}_c{ccc}.tif",
    "--filenamePatternType", "ROWCOL",
    "--gridHeight",          "5",
    "--gridWidth",           "5",
    "--gridOrigin",          "UL",
    "--startRow",            "1",
    "--startCol",            "1",
    "--imageDir",            "/data/tiles",
    "--outputPath",          "/data/output",
    "--programType",         "JAVA",
], text=True)
print("Exit code:", result.returncode)
```

See https://hub.docker.com/r/wipp/mist for available image tags.

---

## Batch Processing Pattern (Python)

The following pattern processes multiple tile directories in a loop, using a shared grid configuration. This is the agent-friendly approach — no shell required.

```python
import subprocess
from pathlib import Path

# --- Shared configuration ---
MIST_JAR      = "/path/to/MIST_-2.1-jar-with-dependencies.jar"
FILENAME_PATTERN      = "img_r{rrr}_c{ccc}.tif"
FILENAME_PATTERN_TYPE = "ROWCOL"
GRID_WIDTH    = 10
GRID_HEIGHT   = 10
GRID_ORIGIN   = "UL"
START_ROW     = 1
START_COL     = 1
FFTW_LIB_FILE = "libfftw3.so"
FFTW_LIB_NAME = "libfftw3"
FFTW_LIB_PATH = "/usr/local/lib"
BASE_DIR      = Path("/data/experiments")

# --- Loop over all tile directories ---
for tile_dir in sorted(BASE_DIR.glob("tiles_*")):
    out_dir = BASE_DIR / "output" / tile_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Stitching: {tile_dir.name}")

    result = subprocess.run([
        "java", "-jar", MIST_JAR,
        "--filenamePattern",     FILENAME_PATTERN,
        "--filenamePatternType", FILENAME_PATTERN_TYPE,
        "--gridHeight",          str(GRID_HEIGHT),
        "--gridWidth",           str(GRID_WIDTH),
        "--gridOrigin",          GRID_ORIGIN,
        "--startRow",            str(START_ROW),
        "--startCol",            str(START_COL),
        "--imageDir",            str(tile_dir),
        "--outputPath",          str(out_dir),
        "--programType",         "FFTW",
        "--fftwLibraryFilename", FFTW_LIB_FILE,
        "--fftwLibraryName",     FFTW_LIB_NAME,
        "--fftwLibraryPath",     FFTW_LIB_PATH,
        "--logLevel",            "MANDATORY",
    ], text=True)

    if result.returncode == 0:
        print(f"  Done → {out_dir}")
    else:
        print(f"  FAILED (exit {result.returncode}) — check {out_dir}/log.txt")
```

---

## Output Files Reference

All output files use the configured `outFilePrefix` (empty by default). The `{#}` is the timeslice index, starting at 0.

| File | Purpose |
|------|---------|
| `{prefix}stitched-{#}.tif` | Final blended mosaic image |
| `{prefix}global-positions-{#}.txt` | Absolute (x, y) pixel positions of each tile in the mosaic coordinate system; can be reloaded for "Assemble from metadata" |
| `{prefix}relative-positions-{#}.txt` | Pairwise translations after optimisation (NCC-filtered and hill-climb refined) |
| `{prefix}relative-positions-no-optimization-{#}.txt` | Raw pairwise translations from PCIAM before any optimisation |
| `{prefix}statistics.txt` | Summary statistics (estimated overlap, repeatability, NCC distribution) AND full parameter set — can be reloaded as a params file |
| `{prefix}log.txt` | Full execution log |

### Global Positions File Format

Each line in `global-positions-{#}.txt` contains:
```
file: <filename>; corr: <ncc_value>; position: (<x>, <y>); grid: (<col>, <row>);
```

This file is the key output for downstream analysis — it gives you the pixel coordinates of each tile in the assembled mosaic.
