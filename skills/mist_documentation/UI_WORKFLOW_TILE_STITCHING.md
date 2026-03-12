# MIST — GUI Workflow: Stitching a Tile Grid

This walkthrough guides you through a complete stitching run using the MIST Fiji plugin GUI. The example uses a 5×5 grid of fluorescence tiles with Row-Column naming, but each step notes how to adapt for other dataset types.

---

## Before You Start — Checklist

- [ ] MIST is installed in Fiji (Plugins ▶ Stitching ▶ MIST appears in the menu)
- [ ] All image tiles are in a single folder with no subdirectories
- [ ] All tiles are the same pixel dimensions (e.g. all 1392×1040)
- [ ] All tiles are grayscale (for RGB tiles, use Overlay blending only)
- [ ] You know:
  - The filename pattern (e.g. `img_r{rrr}_c{ccc}.tif`)
  - The grid dimensions (number of rows and columns)
  - The corner where the scan started (e.g. Upper Left)
  - For sequential naming: the scan direction (e.g. Horizontal Combing)
- [ ] You have an output directory ready (or will use the image directory)

---

## Step 1 — Launch MIST

1. Start Fiji
2. Go to **Plugins ▶ Stitching ▶ MIST**
3. The MIST window opens on the **Input** tab

---

## Step 2 — Set the Filename Pattern Type

In the **Input** tab:

- If your files are named with a row number and a column number (e.g. `img_r01_c01.tif`), select **Row-Column**
- If your files are named with a single sequential counter (e.g. `img_pos001.tif`), select **Sequential**

**Row-Column example:**
```
Files on disk:   img_r001_c001.tif, img_r001_c002.tif, ...
Filename Pattern:  img_r{rrr}_c{ccc}.tif
```

**Sequential example:**
```
Files on disk:   img_pos001.tif, img_pos002.tif, ...
Filename Pattern:  img_pos{ppp}.tif
```

> **Tip for biologists**: Count the digits in the number part of your filenames. Use the same number of matching letters in the token — `{rr}` for 2-digit, `{rrr}` for 3-digit, and so on.

---

## Step 3 — Enter the Filename Pattern

In the **Filename Pattern** field, type the pattern string that matches your filenames, replacing the numeric portion with the appropriate token.

Examples:
| Actual filename | Pattern to enter |
|-----------------|-----------------|
| `img_r01_c01.tif` | `img_r{rr}_c{cc}.tif` |
| `Tile_r001_c001.tiff` | `Tile_r{rrr}_c{ccc}.tiff` |
| `Well_r1_c1.tif` | `Well_r{r}_c{c}.tif` |
| `frame_0001.tif` | `frame_{pppp}.tif` |
| `scan_pos01_t01.tif` | `scan_pos{pp}_t{tt}.tif` |

---

## Step 4 — Set the Image Directory

Click **Browse** next to **Image Directory** and navigate to the folder containing your tile images.

> **Check**: after setting the directory, you can optionally click **Discover Width/Height** (Row-Column mode) to let MIST count the tiles and fill in Grid Width and Grid Height automatically.

---

## Step 5 — Enter Grid Dimensions

- **Grid Width**: the number of tiles across one row (= number of columns in the grid)
- **Grid Height**: the number of tiles down one column (= number of rows in the grid)

Example: for a 5-column by 5-row acquisition, enter Grid Width = 5 and Grid Height = 5.

> **Tip**: If you used a 20% overlap and your sample is 10 mm wide with a 1 mm field of view, you acquired approximately 10 / (1 × 0.8) ≈ 13 tiles wide.

---

## Step 6 — Set the Starting Point

Select the corner of the grid where acquisition began. If unsure, check your microscope acquisition software — it typically logs the scan origin.

Most motorised stage systems start from **Upper Left**.

---

## Step 7 — Set the Scan Direction (Sequential mode only)

If using Sequential naming, select the **Direction** that matches the scan path:
- **Horizontal Combing** — snake/boustrophedon left-right then right-left
- **Horizontal Continuous** — always left-to-right, returns to start of each row
- **Vertical Combing** / **Vertical Continuous** — same but column-by-column

---

## Step 8 — Preview the Grid (Optional but Recommended)

Click **Preview (0% overlap)**. MIST will assemble and display the tile grid assuming zero overlap. This lets you verify:
- All tiles are present (no gaps or error messages)
- Tiles appear in the correct spatial arrangement
- The grid dimensions and filename pattern are correct

If tiles appear shuffled or misaligned in the preview, the filename pattern, starting point, or scan direction is wrong — correct these before proceeding.

---

## Step 9 — Configure the Output Tab

Click the **Output** tab.

1. Set **Output Directory** (or enable **Use Image Directory as Output Directory**)
2. Optionally set a **Filename Prefix** (e.g. `run01_`) to label output files
3. Choose **Blending Mode**:
   - **Overlay** — use this when unsure, or for RGB images
   - **Linear** — best visual quality for grayscale fluorescence; smooth seam blending
   - **Average** — simple mean; rarely the best choice
4. Enable **Display Stitched Image** to see the result in Fiji when done
5. Enable **Save Full Stitched Image** to write the mosaic `.tif` to disk
6. Click **Update** to see the estimated output file size

> **Warning**: if the estimated output size is very large (many gigabytes), consider whether your computer has enough RAM. As a rule of thumb, MIST needs approximately 3–4× the output file size in RAM during processing.

---

## Step 10 — Check Advanced Settings (Optional)

Click the **Advanced** tab. For most datasets the defaults are fine. Consider adjusting:

- **Horizontal / Vertical Overlap**: if you know the overlap percentage from your acquisition settings (e.g. you set 10% overlap in your microscope software), enter it here. This makes MIST's translation filtering more reliable.
  - Formula: `overlap% = (tile_width_µm - step_size_µm) / tile_width_µm × 100`
- **Overlap Uncertainty**: increase from 5% to 10% if tiles are sparse or featureless (e.g. background-heavy brightfield)
- **Stitching Program**: leave as `Auto`. If FFTW is available it will be used; otherwise Java.
- **Number of FFT Peaks**: increase to 3 or 4 if your sample has highly repetitive structure

---

## Step 11 — Begin Stitching

Click **Begin Stitching**.

The MIST Status window appears, showing progress. Stitching typically takes:
- A few seconds for a 5×5 grid of small tiles
- Several minutes for large grids (20×20+) of high-resolution tiles
- Much less with FFTW or CUDA compared to Java

Do not close the Status window during processing. You can click **Cancel Execution** at any time to abort safely.

---

## Step 12 — Inspect the Results

When stitching completes:

1. If **Display Stitched Image** was enabled, the mosaic opens in Fiji automatically
2. Check the mosaic visually for seams, misaligned tiles, or missing regions
3. In your Output Directory, check:
   - `statistics.txt` — reports estimated overlap, stage repeatability, and NCC statistics; low mean NCC values (< 0.5) across many tiles indicate poor alignment
   - `log.txt` — check for any error messages

---

## Step 13 — Troubleshooting Poor Stitching

**Tiles are misaligned at the seams:**
- Try entering the known overlap percentage in the Advanced tab instead of relying on automatic estimation
- Increase the Overlap Uncertainty to 10%
- Try Double Precision Math if tiles are low-contrast

**Many tiles appear shifted to a wrong position:**
- Check that the Starting Point and scan Direction are correct
- Increase Number of FFT Peaks to 3–5
- Try Multipoint hill climb instead of Single hill climb

**Some tiles appear as black rectangles:**
- MIST could not open those files; try enabling BioFormats Image Reader
- Check that the filename pattern exactly matches the actual filenames (case-sensitive on Linux)

**Run is very slow:**
- Switch Stitching Program to FFTW or CUDA
- Reduce CPU worker threads if system is overloaded

---

## Step 14 — Re-Assemble with Different Blending (Optional)

If you want to change the blending mode without re-running the full stitching computation:
1. In the **Input** tab, enable **Assemble from metadata**
2. In the **Global Positions File** field, enter the path to `{prefix}global-positions-0.txt` from the previous run
3. Change the **Blending Mode** in the Output tab
4. Click **Begin Stitching** — only the composition step runs (fast)

---

## Step 15 — Save Parameters for Reuse

Click **Save Params** on the Input tab to save all current settings to a `.txt` file. Next time, click **Load Params** and select this file to restore all settings instantly.

> **Tip**: The `statistics.txt` output file also serves as a parameter file — loading it with **Load Params** restores all settings from that run, including the estimated overlap and repeatability values.
