# MIST — Plugin Overview
## (Microscopy Image Stitching Tool)

---

## What It Is

MIST is a Fiji plugin developed by NIST (National Institute of Standards and Technology) that assembles a rectangular grid of overlapping microscopy image tiles into a single seamless mosaic image. It is purpose-built for microscope output, where a motorized XY stage moves a sample through the field of view to acquire a grid of overlapping tiles.

MIST is distinct from the older Fiji "Grid/Collection Stitching" plugin (by Preibisch et al.) in two key ways: it models the mechanical behavior of the microscope stage to constrain and correct translations, and it uses maximum likelihood estimation to robustly estimate overlap even when many tiles contain little image content.

- **Input**: a rectangular grid of grayscale image tiles (all the same size), named with a sequential or row-column pattern
- **Output**: a blended mosaic .tif, position files (relative and global), a statistics file, and a log
- **Launched via**: Plugins ▶ Stitching ▶ MIST
- **Update site**: MIST (available via Fiji's update site manager — Help ▶ Update ▶ Manage update sites)
- **Requires**: Fiji (not plain ImageJ); Java 8+; 64-bit OS recommended
- **GPU acceleration**: optional via NVIDIA CUDA (requires CUDA Toolkit installation)
- **Publication**: Chalfoun et al., *MIST: Accurate and Scalable Microscopy Image Stitching Tool with Stage Modeling and Error Minimization*, Scientific Reports 7, 4988 (2017)

---

## Core Use Cases

1. **Standard tile stitching** — assemble a grid of brightfield or fluorescence tiles from any motorized microscope into a single composite image
2. **Multi-channel stitching** — stitch each channel's tile set independently using the same grid parameters; position files from one channel can be reapplied to others via "Assemble from metadata"
3. **Time-lapse stitching** — stitch a time series of tile grids using the `{ttt}` token in the filename pattern; each timepoint is stitched independently
4. **Large sample mapping** — stitch very large grids (e.g. 10×10, 20×20) of high-resolution tiles for plate scanning or whole-slide applications
5. **Headless/batch stitching** — automate stitching of many datasets using the standalone executable JAR with command-line parameters (no GUI required)
6. **Re-assemble from saved positions** — after a first stitching run, recompose the mosaic with different blending modes without re-running the full computation, using the saved global-positions file

---

## Algorithm in Brief

MIST uses a three-phase pipeline:

**Phase 1 — Translation Computation**: For each adjacent pair of tiles, the relative displacement (translation) is computed using the Phase Correlation Image Alignment Method (PCIAM). This computes a Peak Correlation Matrix (PCM) via FFT, finds the top 2 peaks (default), and selects the peak translation that maximises the normalized cross-correlation (NCC) of the overlapping subregion.

**Phase 2 — Translation Optimisation**: A stage model is built by fitting the computed translations to a mixture model (valid translations ~ Gaussian, invalid ~ uniform) using maximum likelihood estimation. This estimates the percent image overlap and stage repeatability separately for NORTH and WEST directions. Bad translations are filtered out and replaced with estimates derived from the valid set (row/column medians). A bounded NCC hill-climbing search then refines every translation to a pixel-level local maximum within a window of ±stage_repeatability pixels.

**Phase 3 — Image Composition**: A maximum spanning tree of the translation graph (weighted by NCC values) is used to convert relative translations to absolute global positions. Tiles are then copied and blended into the final mosaic.

---

## Filename Pattern System

MIST uses a token-based filename pattern to locate tiles. Two pattern types are supported:

**Row-Column (`ROWCOL`)** — tile position encoded as a row number and column number in the filename:
- `img_r{rr}_c{cc}.tif` — rows and columns zero-padded to 2 digits
- `Tile_r{rrr}_c{ccc}.tiff` — zero-padded to 3 digits
- `{r}`, `{rr}`, `{rrr}` ... — increase number of `r`s for wider zero-padding
- Requires specifying `startRow` and `startCol` (the smallest row/column index present in the files)

**Sequential (`SEQUENTIAL`)** — tile position encoded as a single counter in the filename:
- `img_pos{ppp}.tif` — sequential index zero-padded to 3 digits
- `frame_{pppp}.tif` — zero-padded to 4 digits
- Requires specifying `startTile` and a `numberingPattern` (scan direction)

**Time slices** — add `{ttt}` to either pattern type for time series:
- `img_r{rr}_c{cc}_t{ttt}.tif` — each value of {ttt} stitched independently

---

## Grid Origin and Scan Direction

**Grid Origin** — the corner of the grid where the microscope started scanning:
- `UL` — Upper Left (most common)
- `UR` — Upper Right
- `LL` — Lower Left
- `LR` — Lower Right

**Numbering Pattern** (Sequential mode only) — the path the stage took:
- `HORIZONTALCOMBING` — left-right on odd rows, right-left on even rows (boustrophedon)
- `HORIZONTALCONTINUOUS` — always left-to-right, returns to start of each row
- `VERTICALCOMBING` — top-down on odd columns, bottom-up on even columns
- `VERTICALCONTINUOUS` — always top-to-bottom, returns to start of each column

---

## Output Files

For each stitching run (each timeslice `#`, starting at 0), MIST writes to the Output Directory:

| File | Contents |
|------|----------|
| `{prefix}stitched-{#}.tif` | The final blended mosaic image |
| `{prefix}global-positions-{#}.txt` | Absolute (x, y) position of each tile in the mosaic |
| `{prefix}relative-positions-{#}.txt` | Pairwise translations after optimisation |
| `{prefix}relative-positions-no-optimization-{#}.txt` | Pairwise translations before optimisation (raw PCIAM output) |
| `{prefix}statistics.txt` | Run statistics AND a loadable parameters file |
| `{prefix}log.txt` | Execution log |

The `statistics.txt` file doubles as a parameter file — it can be loaded directly into MIST via the "Load Params" button to re-run or re-assemble.

---

## Installation

**Via Fiji Update Site (recommended)**:
1. Help ▶ Update ▶ Manage Update Sites
2. Find and enable the **MIST** update site
3. Click Apply Changes and restart Fiji

**Manual**:
- Copy the MIST `.jar` file into `Fiji.app/plugins/`
- On Windows, FFTW (`libfftw3.dll`) is bundled in `Fiji.app/lib/fftw/`
- On Linux/Mac, install FFTW separately: `sudo apt install libfftw3-dev` or compile from source

**CUDA (optional)**:
- Install NVIDIA CUDA Toolkit
- MIST will detect CUDA GPUs automatically when the toolkit is present

---

## Known Limitations

- **Grayscale only**: all input tiles must be grayscale; RGB tiles cause issues with Linear and Average blending (use Overlay for RGB)
- **Uniform overlap assumption**: MIST assumes the overlap between tiles is approximately constant within each axis — non-uniform grids (e.g. irregular stage movements) may not stitch well
- **Output size limit**: the output mosaic must have fewer than 2,147,483,647 total pixels (2³¹−1); very large grids must be assembled as tiled TIFFs using alternative methods
- **All tiles same size**: MIST requires all input tiles to be identical in pixel dimensions
- **Missing tiles**: empty grid positions are permitted as long as the remaining tiles form a single connected graph; isolated clusters cannot be stitched
- **No rotation correction**: MIST only computes x/y translations; camera rotation relative to stage is not corrected (though the algorithm accounts for its projection onto the translation vectors)
- **No Z-stack support**: MIST handles 2D tiles only; Z-stacks must be projected before stitching

---

## Citations

Chalfoun, J., Majurski, M., Blattner, T., Keyrouz, W., Bajcsy, P., Brady, M. (2017). MIST: Accurate and Scalable Microscopy Image Stitching Tool with Stage Modeling and Error Minimization. *Scientific Reports* 7, 4988. https://doi.org/10.1038/s41598-017-04567-y

Majurski, M., Blattner, T., Chalfoun, J., Keyrouz, W. (2018). MIST Algorithm Documentation. NIST/ITL/SSD, version 2018-05-21.
