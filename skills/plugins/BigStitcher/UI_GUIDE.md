# BigStitcher UI Guide (Fiji GUI)

This guide walks through a standard tile-stitching workflow in the Fiji interface.

## Before you start
1. Open Fiji.
2. Confirm BigStitcher exists in menu: **Plugins > BigStitcher > BigStitcher**.
3. Download sample data if needed (from BigStitcher page):
   - 2D example: `Grid_2d.zip`

---

## Step-by-step workflow (GUI)

1. **Launch BigStitcher**  
   Menu: **Plugins > BigStitcher > BigStitcher**  
   Expected window title: a BigStitcher main control window with mode options.

2. **Define a new dataset**  
   Choose the import/definition action ("Define New Dataset").
   - **define_dataset**: choose loader type (usually automatic Bio-Formats loader)
   - **project filename**: name of output XML project
   - **path/pattern**: where raw tiles are located and how they are matched
   - **pattern fields** (e.g., Channels, Tiles): tell BigStitcher how filenames encode axes
   - **voxel size fields**: physical spacing in X/Y/Z

   Expected output: saved dataset project (`.xml`) and dataset listed/openable.

3. **(Optional) Move tiles to regular grid**  
   If metadata coordinates are missing/wrong, use move-to-grid options.
   - **grid type**: scan order pattern
   - **tiles_x / tiles_y / tiles_z**: tile counts in each axis
   - **overlap %**: expected overlap between neighboring tiles

   Expected output: initial rough placement visible in preview/BDV.

4. **Calculate pairwise shifts**  
   Action: **Calculate pairwise shifts**
   - **method**: typically Phase Correlation
   - **channels**: average channels or a selected channel
   - **downsample_in_x/y/z**: speed vs precision tradeoff

   Expected output: link calculations complete (progress dialog/log updates).

5. **Preview / filter pairwise shifts**  
   Action: **Filter pairwise shifts**
   - **min_r / max_r**: keep links by correlation quality
   - **max shift / max displacement**: reject implausible links

   Expected output: weak links removed; cleaner connection graph.

6. **Global optimization**  
   Action: **Optimize globally and apply shifts**
   - **relative / absolute**: optimization thresholds
   - **global optimization strategy**: e.g., two-round strategies
   - **fixed group(s)**: define reference to anchor transforms

   Expected output: globally consistent tile alignment.

7. **Inspect in BigDataViewer**  
   Open dataset in BDV for quality check.
   Look for:
   - Seam continuity across tile boundaries
   - No obvious duplicated structures
   - Reasonable alignment in all axes

8. **Fuse dataset for export**  
   Action: **Fuse dataset**
   - **bounding box**: all views or a selected sub-volume
   - **downsampling**: output scale
   - **pixel type**: output bit depth
   - **interpolation/blend**: fusion quality settings
   - **fused image target**: choose TIFF stack export directory

   Expected output: fused TIFF(s) written to disk.

---

## Annotated example (from official headless example settings)
- Pairwise shift: Phase Correlation with 2×2×2 downsampling
- Filter links: keep correlation >= 0.7
- Global optimization: two-round strategy with strict constraints
- Fusion: all views, linear interpolation, save compressed TIFF stack

You should see:
- Updated dataset XML after each processing stage
- Progress dialogs/log entries for each step
- Final fused output files in the chosen output directory

---

## Common UI pitfalls
1. **Incorrect filename pattern parsing** → tiles/channels/timepoints mixed incorrectly.
2. **Wrong voxel spacing** → distorted geometry and poor registration.
3. **Too permissive link filtering** → bad pairwise links degrade global optimization.

## Evidence sources
- https://imagej.net/plugins/bigstitcher/
- https://imagej.net/plugins/bigstitcher/headless
