---
name: bigstitcher_documentation
description: A Fiji plugin for stitching and fusing multi-tile, multi-angle, multi-TB microscopy datasets.Stores all state in an XML project file; uses BigDataViewer for interactive display. Primary use cases are cleared-tissue lightsheet stitching, tiled confocal reconstruction, multi-view lightsheet registration. Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---


# BigStitcher — Skill Quick Reference

---

## Can BigStitcher Be Automated via Groovy?

**YES — fully.** All BigStitcher processing steps are exposed as
macro-recordable commands under `Plugins › BigStitcher › Batch Processing`.
These are callable from Groovy (and any other Fiji scripting language) via
`IJ.run()`. The complete pipeline — dataset definition, phase correlation,
global optimization, fusion — can be run from the Fiji Script Editor:

```groovy
IJ.run("Calculate pairwise shifts ...", "select=/path/to/dataset.xml ...")
IJ.run("Optimize globally and apply shifts ...", "select=/path/to/dataset.xml ...")
// NOTE: In many BigStitcher versions the fusion command is recorded as "Image Fusion" (not "Fuse dataset ...").
// Always confirm the exact command name via Plugins › Macros › Record…
IJ.run("Image Fusion", "select=/path/to/dataset.xml ...")
```

Use the **Macro Recorder** (`Plugins › Macros › Record…`) to capture exact
parameter strings while working interactively — then paste them into your
Groovy script.

---

## Processing Pipeline (Stitching Mode)

```
Step 1 — Define dataset         →  IJ.run("Define Multi-View Dataset") *(or similar; command name is version-dependent — use Macro Recorder)*
Step 2 — Calculate pairwise shifts  →  IJ.run("Calculate pairwise shifts ...")
Step 3 — Filter links               →  IJ.run("Filter pairwise shifts ...")
Step 4 — Global optimization        →  IJ.run("Optimize globally and apply shifts ...")
Step 5 — ICP refinement (optional)  →  IJ.run("ICP Refinement ...")
Step 6 — Fuse / Image Fusion         →  IJ.run("Image Fusion")  *(command name depends on BigStitcher version; use Macro Recorder)*
```

All steps are fully automatable via `IJ.run()`. Each call is synchronous and
operates on the shared XML project file.

---

## Key Parameters (All Steps)

| Parameter | Typical value | Notes |
|---|---|---|
| `GRID_TYPE` | acquisition-specific | Infer row order from stage coordinates; use recorder-exact `[Right & Down             ]` when every row increases X, and `[Snake: Right & Down      ]` only when alternate rows reverse X |
| `tiles_x`, `tiles_y` | dataset-specific | From acquisition settings |
| `overlap_x_(%)` | `10` | Match your acquisition overlap |
| `downsample_in_x/y` | `2` | Use `4` for faster/coarser result |
| `downsample_in_z` | `1` for a projected 2D mosaic | Never downsample a singleton Z axis |
| `min_r` | `0.7` | Cross-correlation threshold for link filtering |
| `global_optimization_strategy` | `Two-Round using metadata to align unconnected Tiles` *(exact capitalization varies by BigStitcher version)* | Always copy exactly from the Macro Recorder dropdown (**case/spacing sensitive**). In Fiji 2.16.0/1.54p (Java 21) we observed 5 valid strings: `One-Round`; `One-Round with iterative dropping of bad links`; `Two-Round using metadata to align unconnected Tiles`; `Two-Round using Metadata to align unconnected Tiles and iterative dropping of bad links`; `NO global optimization, just store the corresponding interest points`. |
| `fix_group_0-0,` | always | Trailing comma required |
| `pixel_type` in Fuse | `16-bit unsigned integer` | For fluorescence data |

---

## Critical Pitfalls

1. **Unattended runs must never show a dialog.** This workflow expects a folder
   of already prepared tiles. If the raw input is a multi-series Z-stack, export
   each series programmatically before defining the dataset. For a max-Z
   projection use `ij.plugin.ZProjector.run(imp, 'max')`. Do **not** call
   `IJ.runPlugIn(imp, 'ij.plugin.ZProjector', ...)`: that invokes the plugin's UI
   entry point, opens a modal `ZProjection` dialog, and does not return the
   projected `ImagePlus`. In unattended scripts, signal invalid parameters or
   failed outputs with `throw new IllegalStateException(...)`; never use
   `IJ.error`, `IJ.showMessage`, `WaitForUserDialog`, or another prompt API.
2. **Do not pass a raw multi-series container to Automatic Loader.** In
   BigStitcher 3.0.8, defining a dataset directly from a 64-series LSM can fail
   in `FileListDatasetDefinitionUtil.checkMultiplicity()` with
   `NoSuchElementException`. First open every series with windowless
   Bio-Formats, perform any projection with a direct API, and save one lossless
   TIFF per tile using deterministic row/column indices. Point
   `Define Multi-View Dataset` at a dedicated directory containing only those
   prepared tiles. For this installed Automatic Loader, use the verified naming
   contract `Tiles_0000.tif` ... `Tiles_0063.tif` together with
   `pattern_0=Tiles` (and the recorder's `exclude=10`). These tokens are what
   group the files as 64 **tiles of one timepoint**. Never "repair" a loader
   error by deleting `pattern_0`: without the tile grouping, BigStitcher can
   silently interpret the same inputs as 64 timepoints, emit
   `fused_tp_0...fused_tp_63`, and produce a false `4C x 1024 x 1024` result
   instead of the expected roughly `4C x 7500 x 7500` mosaic. Validate that the
   XML has 64 tile views at one timepoint and that fused XY dimensions are much
   larger than one input tile before accepting it. `pattern_0=Tiles` describes
   that prepared tile set; it is not
   a fix for a raw LSM or a mixed parent directory. Verify the tile count and
   dimensions before invoking BigStitcher.
   For a **2D mosaic assembled from a shallow Z-stack**, this preparation step
   must also collapse Z before BigStitcher: split channels, call
   `ij.plugin.ZProjector.run(channelImp, 'max')` for every channel, merge the
   projected channels, and save exactly one `C x 1Z x 1T` TIFF per tile.
   BigStitcher 3.0.8's directly/virtually loaded TIFF path has been observed to
   fail during phase-correlation downsampling of a `4C x 3Z` tile with repeated
   `LazyDownsample2x` / `ArrayIndexOutOfBoundsException` errors. This is not a
   slow stitch and retrying parameter sweeps will not repair it. Verify every
   prepared tile has `NSlices == 1` before dataset definition, and use
   `downsample_in_z=1` for pairwise registration. Do not merely copy or re-save
   the original multichannel Z-stack as a "prepared" TIFF.
3. **Avoid re-save when the prepared inputs are small enough to load virtually.**
   With BigStitcher 3.0.8 in this Fiji image, the Automatic Loader can create an
   OME-Zarr/N5 store when a macro uses the obsolete
   `how_to_load_images=...` field (the unrecognized option is silently ignored),
   then fail inside `ZarrV3KeyValueWriter.createDataset()` with
   `N5Exception: Can't make a dataset on existing dataset`. A unique filename
   does not cure a collision created within the same export. For a modest 8×8
   prepared-tile dataset, use this version's exact recorded fields:

   ```groovy
   'how_to_store_input_images=[Load raw data directly (no resaving)] ' +
   'load_raw_data_virtually ' +
   'metadata_save_path_(XML)=' + OUTPUT_DIR + ' ' +
   'image_data_save_path=' + OUTPUT_DIR
   ```

   Do not use `how_to_load_images=[Load raw data virtually]`: it belongs to a
   different UI/version and selects the default OME-Zarr v3 resave here. Omit
   all HDF5/Zarr export parameters when direct loading is selected. Reserve
   re-save for large datasets after verifying the installed writer.

   With the Automatic Loader in BigStitcher 3.0.8, an obsolete or misspelled
   save-path field may leave `project_filename` in the prepared-tile input
   directory. Do not declare failure by
   checking only `<dataset_save_path>/dataset.xml`. Resolve the XML after the
   command from both locations (and their `dataset.xml~*` backups):

   ```groovy
   def xmlCandidates = [new File(OUTPUT_DIR, "dataset.xml"),
                        new File(INPUT_DIR, "dataset.xml")]
   xmlCandidates.addAll(new File(OUTPUT_DIR).listFiles()?.findAll { it.name.startsWith("dataset.xml~") } ?: [])
   xmlCandidates.addAll(new File(INPUT_DIR).listFiles()?.findAll { it.name.startsWith("dataset.xml~") } ?: [])
   File xmlFile = xmlCandidates.findAll { it.exists() && it.length() > 0L }
                               .sort { a, b -> b.lastModified() <=> a.lastModified() }
                               .find()
   if (xmlFile == null) throw new IllegalStateException("BigStitcher dataset XML was not created")
   String xmlPath = xmlFile.absolutePath
   ```

   `dataset.xml` appearing under the input tile directory is a successful
   dataset definition, not evidence that BigStitcher is still running or that
   the command failed.
   Keep the prepared-tile directory pristine: only the tile TIFFs may be present
   when Automatic Loader scans it. Put XML/Zarr/N5 outputs elsewhere and remove
   stale dataset artifacts before retrying; Bio-Formats can try to interpret a
   stale XML as another tile and fail in `checkMultiplicity()`.
4. **Choose grid traversal from evidence, then preserve recorder whitespace.**
   This is a common failure with Define Dataset. If stage X increases in every
   successive block of `tiles_x` series, the acquisition is row-major
   `Right & Down`, not snake. Use the recorder-exact value
   `[Right & Down             ]` in this Fiji version. Use
   `[Snake: Right & Down      ]` (6 trailing spaces) only if alternate rows
   actually reverse X. A wrong traversal can define plausible-looking but
   distant neighbor pairs, causing missing links or a scrambled mosaic; phase
   correlation cannot be expected to fix it. Macro choices are whitespace
   sensitive, so copy the exact value from the recorder.
5. **Trailing comma in `fix_group_0-0,`** — required; missing it breaks the
   global optimization reference frame.
6. **Re-save to a different path than input** — writing HDF5 into the same
   folder as raw files is allowed but can cause confusion; use a subdirectory.
7. **Fusion before optimization** — fusing with unregistered positions produces
   a broken output. Always run optimize → (ICP) → fuse in order.
8. **ICP requires sufficient shared signal** — if tiles share little overlap
   content, affine ICP will diverge. Use translation model as fallback.
6. **`org.janelia.saalfeldlab.n5.N5Exception: Can't make a dataset on existing dataset`
   — a leftover output from a PREVIOUS attempt, not a bug in your parameters.**
   BigStitcher's re-save writes N5/Zarr/HDF5, and those are **directories**, not
   files. A retry that only cleans files leaves them behind, and the next run finds
   an existing dataset where it expected clean ground. This bites hardest when the
   stale output sits in the *input* folder that Define Dataset scans.

   The naive cleanup is wrong — `isFile()` skips exactly the thing you need gone:
   ```groovy
   dir.listFiles()?.each { if (it.isFile()) it.delete() }          // WRONG: skips dataset.ome.zarr/
   dir.listFiles()?.each { it.isDirectory() ? it.deleteDir() : it.delete() }   // RIGHT
   ```
   Observed for real: a run left a 681 MB `dataset.ome.zarr/` (30,210 files) in the
   tile input folder; every retry rewrote the 64 tiles beside it and failed again
   with the same N5Exception. If you hit this, delete the stale `*.zarr` / `*.n5` /
   `*.h5` **directory** before re-running — re-running unchanged cannot succeed.
   Keep the re-save target OUT of the input folder as well (see pitfall 3).
7. **"Missing stage coordinates" on a Zeiss LSM mosaic — the positions ARE there,
   you are reading the wrong place.** Bio-Formats leaves OME `StageLabel` null for
   LSM, so `Image.getStageLabel()` returns null for every series and a script that
   trusts it concludes the file has no tile positions. A real run then reported
   `Missing stage coordinates for series 0` → `Positioned series count=0 (< 64)`,
   fell back to inferring the lattice, and produced `Expected 8 axis groups, got 9`
   — all for a file whose grid was perfectly regular.

   The positions live in the vendor block. Get them from the metadata tool
   (`extract_image_metadata` reports `dimensions.mosaic_grid`) or directly:
   ```python
   import tifffile, numpy as np
   md = tifffile.TiffFile(path).lsm_metadata
   tp = np.asarray(md['TilePositions'])          # (n_tiles, 3), METRES
   ux, uy = np.unique(tp[:,0].round(9)), np.unique(tp[:,1].round(9))   # grid_x, grid_y
   ```
   **Round before uniquing** — float noise is what turns 8 rows into "9 axis groups".
   For the reference dataset this yields 64 tiles, an exact 8x8 grid, 382.59 um step
   against a 425.1 um tile = **10.0% overlap**, which you can hand straight to
   `Move Tile to Grid` instead of asking BigStitcher to discover it.

---

## Automation Pathways Summary

| Pathway | Best for |
|---|---|
| BigStitcher GUI | Interactive exploration, visual QC, manual link curation |
| `IJ.run()` in Groovy | Scripted pipeline automation from the Fiji Script Editor |

---

## File Inventory

| File | Contents |
|---|---|
| `OVERVIEW.md` | Plugin description, pipeline, formats, automation pathways, installation |
| `UI_GUIDE.md` | Every dialog parameter with values and notes |
| `UI_WORKFLOW_STITCHING.md` | Step-by-step GUI walkthrough for tile stitching |
| `GROOVY_SCRIPT_API.md` | Full IJ.run() API reference with all pipeline commands |
| `WORKFLOW_TILE_STITCHING.groovy` | Ready-to-run Groovy pipeline script (Fiji Script Editor) |
| `SKILL.md` | This quick-reference card |
