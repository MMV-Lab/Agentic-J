# MIST — GUI Parameter Reference

All parameters available in the MIST Fiji plugin, organised by tab. Parameters marked **\*** are required.

---

## Launching MIST

1. Start Fiji
2. Navigate: **Plugins ▶ Stitching ▶ MIST**
3. The MIST window opens with 5 tabs: Input, Output, Subgrid, Advanced, Help

---

## Tab 1: Input

### Toolbar Buttons

| Button | Action |
|--------|--------|
| **Save Params** | Saves all current parameters to a `.txt` file for reuse |
| **Load Params** | Loads parameters from a saved file; also accepts the `statistics.txt` from a previous run |
| **Preview (0% overlap)** | Assembles and displays the tile grid assuming zero overlap — useful for verifying grid layout before stitching |
| **Begin Stitching** | Launches the stitching pipeline |

---

### \* Filename Pattern Type

Selects how tile positions are encoded in filenames.

**Sequential** — a single counter represents position in the scan order:
```
img_pos001_c01.tif  →  img_pos{ppp}_c01.tif
img_pos0001.tif     →  img_pos{pppp}.tif
```
- `{p}`, `{pp}`, `{ppp}`, `{pppp}` — number of `p`s sets zero-padding width

**Row-Column** — separate row and column numbers encode position:
```
img_r01_c01.tif      →  img_r{rr}_c{cc}.tif
Tile_r001_c001.tiff  →  Tile_r{rrr}_c{ccc}.tiff
```
- `{r}`, `{rr}`, `{rrr}` — row number zero-padding
- `{c}`, `{cc}`, `{ccc}` — column number zero-padding

---

### \* Starting Point

The corner of the image grid where the microscope began acquisition. This is the position of tile index [0,0] (or tile 1 in sequential mode).

| Value | Meaning |
|-------|---------|
| `Upper Left` | Grid starts at top-left (most common) |
| `Upper Right` | Grid starts at top-right |
| `Lower Left` | Grid starts at bottom-left |
| `Lower Right` | Grid starts at bottom-right |

---

### \* Direction

*(Visible only for Sequential pattern type)* — the path the stage took while acquiring tiles.

| Value | Meaning |
|-------|---------|
| `Horizontal Combing` | Left-right on odd rows, right-left on even rows (boustrophedon / snake) |
| `Horizontal Continuous` | Always left-to-right; returns to row start for each new row |
| `Vertical Combing` | Top-down on odd columns, bottom-up on even columns |
| `Vertical Continuous` | Always top-to-bottom; returns to column start for each new column |

---

### \* Grid Width

The number of tiles in each row (i.e. the number of columns in the grid).
- Type: integer
- Example: a 5×5 grid has Grid Width = 5

---

### \* Grid Height

The number of tiles in each column (i.e. the number of rows in the grid).
- Type: integer
- Example: a 5×5 grid has Grid Height = 5

---

### Timeslices

*(Optional)* The timeslice numbers to stitch. Leave blank to stitch all timeslices. Requires `{ttt}` (or `{tt}`, `{tttt}` etc.) in the filename pattern.

- Format: comma-separated values and/or ranges
- Example: `1-25,35,45` → stitches timeslices 1–25, 35, and 45
- If left blank: all timeslices found matching the pattern are stitched

---

### \* Filename Pattern

The pattern string used to locate tiles. Must match the **Filename Pattern Type** selected above. The character `%` cannot be used in a pattern.

**Sequential examples:**
```
img_pos{ppp}.tif           ← 3-digit zero-padded sequential index
img_pos{pppp}_ch00.tif     ← 4-digit with channel suffix
img_{ppp}_t{ttt}.tif       ← with timeslice token
```

**Row-Column examples:**
```
img_r{rr}_c{cc}.tif        ← 2-digit row and column
Tile_r{rrr}_c{ccc}.tiff    ← 3-digit row and column
img_r{rr}_c{cc}_t{ttt}.tif ← with timeslice token
```

---

### \* Image Directory

The folder containing all source image tiles. Use the **Browse** button to navigate to it.
- All files matching the filename pattern in this directory will be loaded
- Subdirectories are not searched

---

### Discover Width/Height Button

Attempts to automatically determine Grid Width and Grid Height by scanning the Image Directory for filenames matching the pattern. Requires a valid Filename Pattern and Image Directory to be set first (Row-Column type only).

---

### Assemble from Metadata

*(Checkbox)* When enabled, skips all stitching computation and instead assembles the mosaic using positions from a previously saved **Global Positions File**. Useful for:
- Re-exporting the mosaic with a different blending mode
- Applying positions from one channel to another

Requires the **Global Positions File** field to be filled in.

---

### Global Positions File

*(Active only when "Assemble from metadata" is checked)* — the full file path to a previously generated `global-positions-{#}.txt` file. Must be an individual file, not a directory. If the filename pattern contains a timeslice token, the global positions filename must also contain the matching timeslice identifier.

---

## Tab 2: Output

### Use Image Directory as Output Directory

*(Checkbox)* When enabled, sets the output directory to be the same as the image input directory.

---

### Output Directory

The folder where all output files will be saved. If it does not exist, MIST will create it.

---

### Filename Prefix

A string prepended to all output filenames. Default is empty (no prefix). Example: setting this to `exp01_` produces `exp01_stitched-0.tif`, `exp01_statistics.txt`, etc.

---

### Blending Mode

Controls how pixel values are calculated in regions where tiles overlap.

| Mode | Behaviour |
|------|-----------|
| `Overlay` | Selects one pixel from overlapping tiles based on highest-confidence position; sharp but may show seams |
| `Linear` | Linearly blends intensities across the overlap zone; smooth transitions; controlled by alpha (0–5] |
| `Average` | Computes the mean intensity across all overlapping tiles; simple but can reduce contrast |

> **Warning**: Linear and Average blending with RGB images can cause out-of-memory errors. Use Overlay for RGB images.

---

### Display Stitched Image

*(Checkbox)* When enabled, opens the completed mosaic in Fiji's image viewer upon completion.

---

### Save Full Stitched Image

*(Checkbox)* When enabled, writes the completed mosaic `.tif` file to the Output Directory.

---

### Update Button

Estimates and displays the expected file size of the stitched output image. Use this before stitching to verify the output will fit in memory.

> **Warning**: Output mosaics exceeding 2,147,483,647 pixels total (width × height) cannot be saved as a standard TIFF and must use alternative export methods.

---

## Tab 3: Subgrid

Use this tab to stitch only a rectangular sub-region of the full tile grid. By default the full grid is used.

| Parameter | Description |
|-----------|-------------|
| **Use full grid** | Resets subgrid parameters to encompass the entire grid |
| **Start Col** | The first column (0-indexed) of the subgrid |
| **Start Row** | The first row (0-indexed) of the subgrid |
| **Extent Width** | The number of columns in the subgrid |
| **Extent Height** | The number of rows in the subgrid |
| **Suppress SubGrid Warning** | Suppresses the confirmation dialog shown when stitching a subgrid |

---

## Tab 4: Advanced

### Stage Repeatability

Overrides MIST's automatic estimate of the microscope stage's mechanical repeatability. This value bounds the hill-climbing search window: the algorithm searches ±repeatability pixels around each estimated translation.
- **Units**: pixels
- **Default**: automatically estimated from the translations
- **When to set manually**: if MIST produces a poor stitch and the stage repeatability is known from the microscope spec sheet, entering it here can improve results
- **Tip**: a value that is too small will miss the correct translation; too large makes the hill climb slow and may converge to the wrong peak

---

### Horizontal Overlap

Overrides the automatic estimate of the horizontal percent overlap between left-right adjacent tiles.
- **Units**: percent (0–100)
- **Default**: automatically estimated using maximum likelihood estimation
- **When to set manually**: if you know the overlap from your acquisition settings (e.g. "20% overlap"), entering it directly will make translation filtering more reliable

---

### Vertical Overlap

Same as Horizontal Overlap but for top-bottom adjacent tiles.
- **Units**: percent (0–100)
- **Default**: automatically estimated

---

### Overlap Uncertainty

The ±tolerance around the estimated overlap used to decide whether a computed translation is valid. A translation whose implied overlap falls outside `estimated_overlap ± overlap_uncertainty` is considered invalid and replaced with an estimate.
- **Units**: percent
- **Default**: 5
- **Range**: 0–100; should generally not exceed 10
- **Tip**: increase if many tiles have low image content and the automatic overlap estimate is unreliable; decrease if you know the overlap precisely

---

### Use BioFormats Image Reader?

*(Checkbox)* When enabled, uses the BioFormats reader instead of the default ImageJ reader.
- **Default**: off (ImageJ reader is faster)
- **When to enable**: if tiles cannot be opened by the ImageJ reader (e.g. proprietary microscope formats like `.lif`, `.czi`, `.nd2`)

---

### Use Double Precision Math?

*(Checkbox)* When enabled, all FFT and correlation computations use 64-bit doubles instead of 32-bit floats.
- **Default**: off (32-bit is faster)
- **When to enable**: if stitching results are unsatisfactory and precision is suspected as the cause

---

### Translation Refinement Method

Selects the strategy for the bounded NCC hill-climbing refinement step.

| Option | Behaviour | Speed |
|--------|-----------|-------|
| `Single hill climb` | One hill climb per tile pair, starting at the computed/estimated translation | Fastest (default) |
| `Multipoint hill climb` | One hill climb from the estimated translation PLUS n random starting points within the search bounds; takes the best result | Slower, more robust |
| `Exhaustive` | Tests every pixel position within the stage repeatability search bounds | Slowest, most thorough |

**Number of Starting Points** — visible when Multipoint is selected; sets how many random restarts are used (default: 16).

---

### Number of FFT Peaks

The number of peaks to extract from the Peak Correlation Matrix (PCM) per tile pair. For each peak, all possible translation interpretations are tested via NCC and the best is kept.
- **Default**: 2
- **Range**: 1–10
- **Tip**: increase to 3–5 if your tiles have repetitive content (e.g. regular cell arrays) where the PCM may have multiple plausible peaks

---

### Log Level

Controls how much information is written to the log during stitching.

| Level | Output |
|-------|--------|
| `None` | No logging |
| `Mandatory` | Critical events only |
| `Helpful` | Recommended for troubleshooting |
| `Info` | Detailed progress information |
| `Verbose` | Everything (very detailed, slows execution) |

---

### Debug Level

Same hierarchy as Log Level but for debug-specific messages. Use `None` for normal operation.

---

### Stitching Program

Selects which FFT implementation to use.

| Option | Behaviour |
|--------|-----------|
| `Auto` | Tries FFTW first; falls back to Java if FFTW is unavailable |
| `Java` | Pure Java FFT (built-in, always available, 32-bit, slowest) |
| `FFTW` | Native FFTW library (faster than Java, recommended when available) |
| `CUDA` | NVIDIA GPU-accelerated FFT (fastest; requires CUDA Toolkit and compatible GPU) |

---

### Java Execution Sub-tab

| Parameter | Description |
|-----------|-------------|
| **CPU worker threads** | Number of parallel threads for tile processing; should not exceed the number of physical CPU cores |

---

### FFTW Execution Sub-tab

| Parameter | Description |
|-----------|-------------|
| **CPU worker threads** | Number of parallel threads |
| **FFTW Plan Type** | `Measure` (default, fast planning), `Patient` (longer planning, more optimised), `Exhaustive` (longest planning, most optimised) |
| **Save Plan?** | Saves the FFTW plan to disk so it can be reused without replanning |
| **Load Plan?** | Loads a previously saved FFTW plan |
| **FFTW Library File** | Path to the FFTW shared library: Windows `libfftw3.dll` (bundled in `Fiji.app/lib/fftw/`), Linux `libfftw3.so`, macOS `libfftw3.dylib` |
| **Plan Location (or file)** | Directory or file path for saving/loading FFTW plans |

---

### CUDA Execution Sub-tab

| Parameter | Description |
|-----------|-------------|
| **CPU worker threads** | Number of parallel CPU threads (used alongside GPU workers) |
| **Execute Device Query** | Queries all installed GPUs and prints their specs to the log |
| **Refresh Device Table** | Re-queries GPUs and updates the selection table |
| **GPU Table** | Lists all detected GPUs; enable the **Selected?** checkbox for each GPU to use |

> **Note**: GPUs with at least 1 GB VRAM are recommended; the required memory scales with tile image size.

---

## Tab 5: Help

| Button | Action |
|--------|--------|
| **Open Local Help Documentation** | Opens a local copy of the MIST User Guide without requiring internet access |

---

## MIST Status Window

After clicking **Begin Stitching**, a progress window appears.

| Element | Description |
|---------|-------------|
| **Progress** | Shows current timeslice / total timeslices / number of groups |
| **Progress bar** | Percentage completion for the current timeslice |
| **Log Level** | Can be changed during execution |
| **Debug Level** | Can be changed during execution |
| **Cancel Execution** | Safely stops the stitching and releases resources |
