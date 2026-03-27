# BigStitcher — GUI Workflow: Stitching a Multi-Tile Dataset

This walkthrough guides you through a complete stitching run using the BigStitcher
GUI. The example uses a 3D multi-tile lightsheet dataset of cleared tissue (e.g.
from a Zeiss Lightsheet Z.1), but the steps apply equally to confocal or widefield
tile acquisitions.

---

## Before You Start — Checklist

- [ ] BigStitcher is installed: **Plugins › BigStitcher › BigStitcher** appears in the menu
  - If not: **Help › Update… → Manage Update Sites → tick BigStitcher → Apply Changes → Restart Fiji**
- [ ] You have at least ~2–4× the size of your dataset free in RAM (or plan to use virtual loading in the Fusion dialog)
- [ ] You know approximately:
  - The number of tiles (rows × columns × z-planes)
  - The acquisition overlap percentage between adjacent tiles
  - The voxel size (µm/pixel) if not stored in metadata
  - Whether you have multiple illumination directions, channels, or acquisition angles

---

## Step 1 — Launch BigStitcher

1. Start Fiji
2. Go to **Plugins › BigStitcher › BigStitcher**
3. A dialog asks whether to **Define a new dataset** or **Open an existing dataset**
4. Select **Define a new dataset** for a fresh import

---

## Step 2 — Choose a Loader

In the **Define Dataset** dialog:

- **Automatic Loader (Bioformats based)** — recommended for CZI, ND2, LIF, and other proprietary formats. Bio-Formats reads metadata automatically.
- **Manual Loader (TIFF only)** — for TIFF stacks with no embedded metadata.

Click **OK**.

---

## Step 3 — Set the Data Path

Navigate to the folder containing your raw image files. Set the **project
filename** (e.g. `dataset.xml`) — this XML file will be created in the same
directory and will store all registration state.

In the **exclude** field, enter `10` (bytes) to skip accidentally included
empty or near-empty files.

---

## Step 4 — Assign Dataset Dimensions

BigStitcher will scan the directory and detect groups of files. Assign the
correct dimension to each group:

| Group type | Assign as |
|---|---|
| Different fluorescence wavelengths | Channels |
| Different tile positions (XY grid) | Tiles |
| Different sample rotation angles | Angles |
| Left/right illumination directions | Illuminations |
| Sequential time acquisitions | Timepoints |

> **Tip**: If your acquisition software saved each channel as a separate file
> (`C00`, `C01`, etc.) and each tile in a sub-folder or with a position index,
> BigStitcher will detect these automatically. If it gets it wrong, you can
> reassign groups manually in this dialog.

Click **OK**.

---

## Step 5 — Arrange Tiles on a Grid (Optional but Recommended)

If metadata tile positions are absent or unreliable:

1. Select **Move Tile to Grid (Macro-scriptable)** in the **move tiles to grid** dropdown
2. Enter:
   - **Grid type**: the scan direction (e.g. `Snake: Right & Down` for a boustrophedon scan)
   - **Tiles X**, **Tiles Y**, **Tiles Z**: number of tiles along each axis
   - **Overlap X(%)**, **Overlap Y(%)**, **Overlap Z(%)**: expected percentage overlap between tiles
3. Click **OK**

> **If metadata positions ARE available** (e.g. from CZI): select
> **Do not move Tiles to Grid (use Metadata if available)** instead. BigStitcher
> will use the stage coordinates from the file.

---

## Step 6 — Re-save as HDF5 (Strongly Recommended for Large Data)

In the **how to load images** dropdown:

- Select **Re-save as multiresolution HDF5** to convert all input tiles into
  BigDataViewer's blocked, compressed, multi-resolution HDF5 format.

Set the **dataset_save_path** to an output directory (can be the same as input).

Leave **subsampling factors** and **hdf5_chunk_sizes** at defaults
(`{1,1,1}, {2,2,2}` etc.) unless you have specific requirements.

Click **OK**. BigStitcher will read all input files and write them to HDF5.
This step takes a few minutes but is done only once. All subsequent processing
will be dramatically faster.

> **For quick exploration on small datasets** you can select
> **Load raw data directly (TIFF only)** or **Virtual Load raw data**, but
> these are much slower for iterative processing.

---

## Step 7 — The BigStitcher Main Window

After dataset definition, the **BigStitcher Stitching Explorer** window opens.
It lists all views (tiles × channels × timepoints × illuminations × angles) in a
table. Columns show:

- **TimePt** — timepoint index
- **ViewSetup** — internal view ID
- **Channel / Illumination / Tile** — attribute values
- **Location** — current registration in world coordinates
- **Avg. r** — average cross-correlation quality (filled in after pairwise stitching)
- **# of links** — number of pairwise links this tile participates in

The **BigDataViewer (BDV)** window opens alongside, showing all tiles in their
current positions.

---

## Step 8 — (Optional) Select Best Illumination

If your dataset has dual-sided illumination (left and right), discard the
inferior illumination direction before stitching:

1. In the BigStitcher window, go to **Preprocessing › Select Best Illuminations**
2. Choose **Relative Fourier Ring Correlation** (most discriminating)
3. Click **OK** — BigStitcher computes local image quality scores and keeps only
   the best illumination per block, per tile

---

## Step 9 — Calculate Pairwise Shifts

This is the core registration step. BigStitcher computes the optimal translation
between every pair of overlapping tiles.

1. Click **Calculate Pairwise Shifts** in the main window
2. In the dialog:
   - **Method**: leave as `Phase Correlation`
   - **Channels**: `Average Channels` (uses average of all channels for cross-correlation)
   - **Downsample in X/Y/Z**: set to `2` (recommended starting point) — provides ~4× speedup with comparable accuracy. For very noisy data, try `4`.
3. Click **OK**

Progress is reported in the Fiji Log window. When complete, the **Avg. r** and
**# of links** columns in the main table are populated.

---

## Step 10 — Inspect and Filter Links

1. Select any tile in the table and click **Link Explorer** (or look at the
   Avg. r column)
2. In the Link Explorer:
   - Examine cross-correlation coefficients (`Avg. r`) for all tile pairs
   - Links with `r < 0.7` are typically unreliable and should be removed
3. Click **Filter by correlation coefficient** and set `min r = 0.7`
4. Optionally add **Filter by shift magnitude** to reject implausibly large shifts
5. Click **Apply Filter**

> **In the BDV window**, tiles connected by remaining links are drawn in yellow.
> Tiles with no links are shown in grey. Verify that the link graph is connected
> (all tiles reachable from any other tile) before proceeding.

---

## Step 11 — Global Optimization

1. Click **Optimize Globally and Apply Shifts**
2. In the dialog:
   - **Strategy**: select **Two-Round using metadata to align unconnected Tiles**
     if any tiles have no phase-correlation links (sparse acquisitions with empty
     regions). **Exact capitalization varies by version**; use the Macro Recorder output verbatim.
     Otherwise **One-Round** is sufficient
   - **Relative threshold**: `2.5` (default)
   - **Absolute threshold**: `3.5` pixels (default)
3. Click **OK**

The global optimization finds the globally consistent set of translations that
minimizes the sum of squared errors across all pairwise links, iteratively
removing the worst outlier links until error thresholds are met.

After completion, tiles in BDV move to their registered positions. Zoom in on
overlapping regions to visually verify alignment.

---

## Step 12 — (Optional) ICP Affine Refinement

If you observe residual spherical or chromatic aberration (tile borders visible
in fused image, slight blurring at edges):

1. Click **ICP Refinement**
2. Set **Transformation** to `Affine` or `Split Affine`
3. Set **ICP max error** to `5–10` pixels
4. Click **OK**

ICP uses interest points or intensity to fit an affine model per tile pair,
correcting non-translational distortions. For chromatic aberration correction,
run ICP separately per-channel using autofluorescent signal as common features.

---

## Step 13 — Define a Bounding Box (Optional)

To fuse only a sub-region of interest:

1. Go to **Bounding Box › Define Bounding Box**
2. Select **Define using BigDataViewer interactively**
3. Drag the bounding box handles in BDV to select the region
4. Name the bounding box (e.g. `my_roi`)
5. Click **OK**

The named bounding box can then be selected in the Fusion dialog.

---

## Step 14 — Fuse the Dataset

1. Click **Fuse Dataset**
2. In the dialog:
   - **Bounding Box**: `All Views` (or your named bounding box)
   - **Downsampling**: `1` for full resolution; `2` or `4` for a quick preview
   - **Pixel type**: `16-bit unsigned integer` for most fluorescence data
   - **Interpolation**: `Linear Interpolation`
   - **Blend**: tick (cosine blending reduces seam artifacts)
   - **Fused image**: `Save as (compressed) TIFF stacks` for most use cases;
     `Save as BigDataViewer XML/HDF5` for very large outputs
   - **Output directory**: set to desired output folder
3. Click **OK**

BigStitcher writes one TIFF file per channel per timepoint. For very large
datasets use **Virtual Image** mode to stream-and-save without holding the
full result in RAM (confirmed: a 787 GB volume fused with 1.25 GB RAM in
Virtual mode).

---

## Step 15 — Inspect the Fused Image

Open the output TIFF in Fiji or another viewer. Check:
- Tile seams are invisible (if blending is on)
- No spatial offset at tile borders
- Image is isotropic in XY (minor Z anisotropy may remain depending on axial
  voxel size vs lateral)

If seams are visible, return to Step 12 (ICP refinement) or check that overlap
percentages and downsampling factors in pairwise shift calculation were correct.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Tiles look misaligned after global optimization | Phase correlation links have low quality | Lower `min_r` to inspect more links in Link Explorer; consider reducing downsampling factor |
| Many tiles have no links (disconnected graph) | Tiles do not actually overlap, or tiles contain only background | Use metadata-based Two-Round optimization; check overlap percentage |
| Phase correlation very slow | Using full resolution | Increase downsampling to 2× or 4× |
| Large files cause out-of-memory | Loading raw TIFF stacks | Re-save as HDF5 (Step 6) |
| BDV window is blank / black | Viewing wrong channel or brightness settings | Adjust display range in BDV (press S, or use Brightness/Contrast) |
| Affine/ICP refinement makes things worse | Insufficient autofluorescent signal in common between tiles | Use translation model only; ICP needs strong, shared signal |
| Output TIFF is too large | Fusing at full resolution | Use downsampling ≥ 2 in fusion dialog, or define a smaller bounding box |
| Stitching results differ between runs | Phase correlation is stochastic at borderline r values | Increase downsampling; set stricter `min_r` threshold |

---

## Saving and Reloading the Project

All registrations are saved automatically to the XML file after each processing
step. The XML also stores backup copies so you can manually revert a step by
editing the XML.

To reload a dataset in a later Fiji session:
1. **Plugins › BigStitcher › BigStitcher**
2. Select **Open an existing dataset**
3. Navigate to the `.xml` file
