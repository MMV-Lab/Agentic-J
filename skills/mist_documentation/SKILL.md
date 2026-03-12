---
name: mist_documentation
description: MIST is a Fiji plugin from NIST for **microscopy image tile stitching**. 
 It assembles a rectangular grid of overlapping microscopy tiles into a single mosaic image.
 Tiles are acquired by a motorized XY stage scanning across a sample.
---

# MIST — SKILL SUMMARY (LLM Reference Card)

- **Input**: a flat directory of same-sized grayscale tiles, named with a sequential or row-column pattern
- **Output**: blended mosaic `.tif` + position files + statistics + log
- **Launched via**: Plugins ▶ Stitching ▶ MIST
- **Algorithm**: Phase correlation (PCIAM) + stage model (MLE overlap estimation) + NCC hill-climbing refinement
- **Parallel**: scalable CPU (FFTW) or GPU (CUDA) execution

---

## ⚠️ CRITICAL: No IJ.run() API

**MIST CANNOT be called from a Groovy script or IJ macro via `IJ.run()`.**
MIST is a standalone GUI plugin. The two automation pathways are:

1. **Parameter file** — save params in GUI, reload for reproducibility
2. **Standalone JAR** — command-line execution, fully headless

Never invent `IJ.run("MIST", ...)` calls. They will not work.

---

## Three-Phase Algorithm (for context)

1. **Translation Computation** — PCIAM (Phase Correlation Image Alignment Method) finds the displacement between each adjacent tile pair using FFT-based cross-correlation; top-2 PCM peaks checked by default
2. **Translation Optimisation** — builds a stage model via MLE (estimates overlap and repeatability); filters bad translations; replaces invalids with row/column medians; refines all translations with bounded NCC hill climbing
3. **Image Composition** — maximum spanning tree of translations → absolute positions → blended mosaic

---

## Filename Patterns

| File | Pattern | Mode |
|------|---------|------|
| `img_r01_c01.tif` | `img_r{rr}_c{cc}.tif` | ROWCOL |
| `Tile_r001_c001.tiff` | `Tile_r{rrr}_c{ccc}.tiff` | ROWCOL |
| `img_pos001.tif` | `img_pos{ppp}.tif` | SEQUENTIAL |
| `scan_001_t01.tif` | `scan_{ppp}_t{tt}.tif` | SEQUENTIAL + timeslice |

Token guide: `{r}` = 1-digit, `{rr}` = 2-digit, `{rrr}` = 3-digit, etc. Same for `{c}`, `{p}`, `{t}`.

---

## Key Parameters — GUI

| Parameter | Location | Values | Notes |
|-----------|----------|--------|-------|
| Filename Pattern Type | Input | `Row-Column` / `Sequential` | |
| Filename Pattern | Input | token string | Must exactly match filenames |
| Starting Point | Input | `Upper Left/Right`, `Lower Left/Right` | Corner where scan began |
| Direction | Input | `Horizontal/Vertical Combing/Continuous` | Sequential only |
| Grid Width | Input | integer | Number of columns |
| Grid Height | Input | integer | Number of rows |
| Image Directory | Input | path | Flat folder, no subdirs |
| Blending Mode | Output | `Overlay`/`Linear`/`Average` | Use Overlay for RGB |
| Horizontal/Vertical Overlap | Advanced | 0–100% | Leave blank = auto-estimated |
| Overlap Uncertainty | Advanced | % (default 5) | Increase for sparse images |
| Stitching Program | Advanced | `Auto`/`Java`/`FFTW`/`CUDA` | FFTW recommended |
| Number of FFT Peaks | Advanced | 1–10 (default 2) | Increase for repetitive content |
| Translation Refinement | Advanced | `Single`/`Multipoint`/`Exhaustive` | Single = default |

---

## Key Parameters — Command Line JAR

Minimal ROWCOL invocation:
```bash
java -jar MIST_-2.1-jar-with-dependencies.jar \
  --filenamePattern img_r{rrr}_c{ccc}.tif \
  --filenamePatternType ROWCOL \
  --gridHeight 5 --gridWidth 5 \
  --gridOrigin UL \
  --startRow 1 --startCol 1 \
  --imageDir /path/to/tiles \
  --outputPath /path/to/output \
  --programType FFTW \
  --fftwLibraryFilename libfftw3.so \
  --fftwLibraryName libfftw3 \
  --fftwLibraryPath /usr/local/lib
```

| Param | Required | Values |
|-------|----------|--------|
| `--filenamePattern` | ✓ | token string |
| `--filenamePatternType` | ✓ | `ROWCOL` / `SEQUENTIAL` |
| `--gridHeight` | ✓ | integer |
| `--gridWidth` | ✓ | integer |
| `--gridOrigin` | ✓ (ROWCOL/SEQ) | `UL`/`UR`/`LL`/`LR` |
| `--startRow` / `--startCol` | ✓ ROWCOL | integer |
| `--startTile` | ✓ SEQUENTIAL | integer |
| `--numberingPattern` | ✓ SEQUENTIAL | `HORIZONTALCOMBING` / `HORIZONTALCONTINUOUS` / `VERTICALCOMBING` / `VERTICALCONTINUOUS` |
| `--imageDir` | ✓ | path |
| `--programType` | ✓ | `AUTO` / `JAVA` / `FFTW` |
| `--fftwLibraryFilename` | ✓ FFTW | e.g. `libfftw3.so` |
| `--fftwLibraryName` | ✓ FFTW | e.g. `libfftw3` |
| `--fftwLibraryPath` | ✓ FFTW | path to lib directory |
| `--outputPath` | optional | path (default = imageDir) |
| `--outFilePrefix` | optional | string |
| `--blendingMode` | optional | `OVERLAY`/`LINEAR`/`AVERAGE` |
| `--horizontalOverlap` | optional | number (%) |
| `--verticalOverlap` | optional | number (%) |
| `--overlapUncertainty` | optional | number (%) default 5 |
| `--numFFTPeaks` | optional | 1–10, default 2 |
| `--logLevel` | optional | `MANDATORY`/`HELPFUL`/`INFO`/`VERBOSE` |

---

## Output Files

| File | Contents |
|------|----------|
| `{prefix}stitched-{#}.tif` | Final mosaic |
| `{prefix}global-positions-{#}.txt` | Absolute (x,y) pixel coordinates per tile |
| `{prefix}relative-positions-{#}.txt` | Pairwise translations (post-optimisation) |
| `{prefix}relative-positions-no-optimization-{#}.txt` | Raw PCIAM translations |
| `{prefix}statistics.txt` | Quality stats + reloadable params file |
| `{prefix}log.txt` | Execution log |

`{#}` = timeslice index starting at 0.

---

## 5 Critical Pitfalls

**1. No IJ.run() API** — MIST cannot be called from a Fiji Groovy/macro script. Use the GUI or the standalone JAR.

**2. Flat directory required** — all tile files must be in a single folder with no subdirectories.

**3. Pattern must exactly match filenames** — including case (Linux), exact number of digits (count r's/c's to match zero-padding), and any suffix. A wrong pattern means tiles are not found at all.

**4. Grid Width = columns, Grid Height = rows** — biologists often confuse these. Width is how many tiles fit across, height is how many fit down.

**5. startRow/startCol are the minimum indices in the filenames** — if your files are `img_r001_c001.tif` through `img_r005_c005.tif`, then startRow=1 and startCol=1. If they start from `img_r000_c000.tif`, use startRow=0 and startCol=0.

---

## Multi-Channel Strategy

Run MIST on one channel to generate `global-positions-0.txt`.
Then use "Assemble from metadata" with that file and a different image directory for each other channel — no re-registration needed, all channels align to the same coordinate system.

---

## Common Decision Tree

```
User wants to stitch tiles?
├── Has access to Fiji GUI?
│   └── YES → Use GUI workflow (UI_WORKFLOW_TILE_STITCHING.md)
│       ├── Know overlap? → Enter in Advanced tab
│       └── Unknown overlap? → Leave blank, MIST estimates it
└── Needs batch / headless?
    └── YES → Build standalone JAR and use command line
        ├── FFTW available? → --programType FFTW (faster)
        └── No FFTW? → --programType JAVA (always works)
```

---

## When to Adjust Parameters

| Symptom | Fix |
|---------|-----|
| Seams visible / tiles misaligned | Enter known overlap% in Advanced |
| Many tiles shifted to wrong position | Increase Number of FFT Peaks to 3–5 |
| Poor results with low-contrast tiles | Enable Double Precision Math |
| Unreadable file format | Enable BioFormats Image Reader |
| Very slow execution | Switch to FFTW or CUDA |
| Automatic overlap estimate unreliable | Set Overlap Uncertainty to 10%; provide explicit overlap |

---

## Installation

Via Fiji update site: Help ▶ Update ▶ Manage Update Sites → enable **MIST** → Apply Changes → restart.
FFTW bundled on Windows (`Fiji.app/lib/fftw/`); install separately on Linux/macOS.

Citation: Chalfoun et al., *Scientific Reports* 7, 4988 (2017). https://doi.org/10.1038/s41598-017-04567-y
