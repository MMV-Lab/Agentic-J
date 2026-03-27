# BigStitcher — Groovy Scripting API

## Overview: Automation via IJ.run()

BigStitcher exposes all major processing steps as **macro-recordable commands**
under `Plugins › BigStitcher › Batch Processing`. These commands can be called
from any Fiji scripting language — including Groovy — using `IJ.run()` with
the command name and a parameter string.

This is the **primary and officially supported automation pathway** for BigStitcher.
All parameters use the same names as those documented in the GUI (with spaces
replaced by underscores and all lowercase in the string form).

---

## How to Discover Parameter Strings

The most reliable way to get exact parameter strings for your dataset is to use
the **Macro Recorder**:

1. Open Fiji
2. **Plugins › Macros › Record…**
3. Perform your steps manually in BigStitcher (using Batch Processing menu items)
4. Copy the recorded `run(...)` calls — these are the exact strings to use

---

## Architecture: Why "Unrecognized Command" Happens

BigStitcher dataset definition **is automatable via `IJ.run()`**, but the **command name is version-dependent** (e.g. on Fiji 2.16.0/1.54p it records as `Define Multi-View Dataset`).

It also has one sharp edge that causes "unrecognized command" far more often than any other step:

**The `grid_type` value contains 6 significant trailing spaces.**

```groovy
// WRONG — will fail with "unrecognized command":
"grid_type=[Snake: Right & Down]"

// CORRECT — 6 trailing spaces after "Down":
"grid_type=[Snake: Right & Down      ]"
```

BigStitcher matches the entire string including whitespace against its internal
registry. One missing space = no match = "unrecognized command". The same
applies to any other bracketed option value (loader type, HDF5 method, etc.)
if they contain internal spacing.

**The fix:** run the Define Dataset wizard once with the **Macro Recorder open**
(`Plugins › Macros › Record…`), then copy the exact `grid_type` value — and
only that value — from the recorder output into your script. Everything else in
the string can be typed normally and parameterized freely.

---

## Step 1 — Define Dataset

BigStitcher’s dataset-definition command name is **version-dependent**.
In the working workflow on Fiji **2.16.0/1.54p (Java 21)**, the macro-recorded
command name is:

- `IJ.run("Define Multi-View Dataset", "...")`

In some older installs, you may instead see a different dataset-definition command name (e.g. `Define dataset ...`).
**Always use the Macro Recorder output verbatim**.

```groovy
// IMPORTANT: The grid_type value below contains significant trailing spaces.
// If your grid type differs, run the Macro Recorder once to capture
// the exact string for your scan direction, then replace it here.
//
// Also IMPORTANT: ensure the INPUT_DIR contains ONLY the image tiles.
// Do not leave dataset.xml, dataset.ome.zarr/, __MACOSX/, etc. in the same
// folder, or Define Dataset may crash during file scanning.

IJ.run("Define Multi-View Dataset",
    "define_dataset=[Automatic Loader (Bioformats based)] " +
    "project_filename=dataset.xml " +
    "path=" + INPUT_DIR + " " +
    "exclude=10 " +
    // The grouping patterns depend on your filename conventions.
    // For the Grid_2d example (MAX_*.tif), using only Tiles works.
    "pattern_0=Tiles " +
    "modify_voxel_size? " +
    "voxel_size_x=" + VOXEL_SIZE_X + " " +
    "voxel_size_y=" + VOXEL_SIZE_Y + " " +
    "voxel_size_z=" + VOXEL_SIZE_Z + " " +
    "voxel_size_unit=µm " +
    "move_tiles_to_grid_(per_angle)?=[Move Tile to Grid (Macro-scriptable)] " +
    "grid_type=[Snake: Right & Down      ] " +   // <-- trailing spaces, do not remove
    "tiles_x=" + TILES_X + " tiles_y=" + TILES_Y + " tiles_z=" + TILES_Z + " " +
    "overlap_x_(%)=" + OVERLAP_X + " " +
    "overlap_y_(%)=" + OVERLAP_Y + " " +
    "overlap_z_(%)=" + OVERLAP_Z + " " +
    "keep_metadata_rotation " +
    "how_to_load_images=[Re-save as multiresolution HDF5] " +
    "dataset_save_path=" + OUTPUT_DIR + " " +
    "check_stack_sizes " +
    "subsampling_factors=[{ {1,1,1}, {2,2,2}, {4,4,4} }] " +
    "hdf5_chunk_sizes=[{ {16,16,16}, {16,16,16}, {16,16,16} }] " +
    "timepoints_per_partition=1 setups_per_partition=0 " +
    "use_deflate_compression " +
    "export_path=" + OUTPUT_DIR + "dataset")
```

**Grid type values** (copy including the exact number of trailing spaces shown):

| Scan pattern | String to use |
|---|---|
| Snake right then down | `[Snake: Right & Down      ]` |
| Snake left then down  | `[Snake: Left & Down       ]` |
| Snake right then up   | `[Snake: Right & Up        ]` |
| Snake left then up    | `[Snake: Left & Up         ]` |
| Right & Down (no snake) | `[Right & Down             ]` |

> If your scan pattern is not listed, run the Macro Recorder on your data
> once to capture the exact string. The trailing space count varies per option.

---

## Core IJ.run() Commands (Steps 2 Onwards)

### 1. Calculate Pairwise Shifts

```groovy
def xmlPath = "/path/to/data/dataset.xml"

IJ.run("Calculate pairwise shifts ...",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "method=[Phase Correlation] " +
    "channels=[Average Channels] " +
    "downsample_in_x=2 downsample_in_y=2 downsample_in_z=2")
```

**Downsampling guidelines:**

| Data type | Recommended downsampling |
|---|---|
| High SNR (SNR ≥ 16), large tiles | 2× |
| Medium SNR (SNR 8–16), typical tile | 4× |
| Low SNR (SNR < 8) | 2× (downsampling smoothing helps at low SNR) |
| Quick preview only | 8× |

---

### 2. Filter Pairwise Shifts

```groovy
IJ.run("Filter pairwise shifts ...",
    "select=" + xmlPath + " " +
    "filter_by_link_quality min_r=0.7 max_r=1 " +
    "max_shift_in_x=0 max_shift_in_y=0 max_shift_in_z=0 " +
    "max_displacement=0")
```

> **Tuning min_r:** For high-overlap, high-SNR data use `0.7`. For sparse,
> low-contrast data try `0.5`. Never go below `0.3` — very low correlation
> shifts are likely noise.

---

### 3. Global Optimization

```groovy
IJ.run("Optimize globally and apply shifts ...",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "relative=2.500 absolute=3.500 " +
    // IMPORTANT: this dropdown is case/spacing sensitive.
    // In Fiji 2.16.0/1.54p (Java 21), the working strings observed are:
    //   - One-Round
    //   - One-Round with iterative dropping of bad links
    //   - Two-Round using metadata to align unconnected Tiles
    //   - Two-Round using Metadata to align unconnected Tiles and iterative dropping of bad links
    //   - NO global optimization, just store the corresponding interest points
    // Use Macro Recorder to confirm the exact spelling for your install.
    "global_optimization_strategy=" +
    "[Two-Round using metadata to align unconnected Tiles] " +
    "fix_group_0-0,")
```

> `fix_group_0-0,` fixes the first tile as the reference frame. Always include
> the trailing comma — it is part of the recorded parameter string.
>
> **Case sensitivity note:** strategy labels can differ between BigStitcher versions.
> Do not “correct” capitalization by hand; copy from the recorder.

---

### 4. ICP Affine Refinement (Optional)

```groovy
IJ.run("ICP Refinement ...",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "icp_refinement_type=[Simple (tile registration)] " +
    "transformation=[Affine] " +
    "icp_max_error=5 " +
    "icp_iterations=100")
```

---

### 5. Fuse Dataset / Image Fusion

> **Important:** depending on your BigStitcher version, the fusion step may be macro-recorded as **`Image Fusion`** (and *not* `Fuse dataset ...`).
> Always confirm the exact command name and bracketed dropdown values (case/spacing) using **Plugins › Macros › Record…**.

```groovy
// Example as recorded in some BigStitcher versions:
IJ.run("Image Fusion",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "bounding_box=[All Views] " +
    "downsampling=1 " +
    "interpolation=[Linear Interpolation] " +
    "fusion_type=[Avg, Blending] " +
    "pixel_type=[32-bit floating point] " +
    "interest_points_for_non_rigid=[-= Disable Non-Rigid =-] " +
    "produce=[Each timepoint & channel] " +
    "fused_image=[Display using ImageJ]")

// If your version records a different command name or parameters,
// copy/paste the recorder output exactly.
```

---

### 6. Select Best Illumination (Optional — dual-sided lightsheet only)

```groovy
IJ.run("Select Best Illumination ...",
    "select=" + xmlPath + " " +
    "process_timepoint=[All Timepoints] " +
    "selection_method=[Relative Fourier Ring Correlation]")
```

---

## Groovy-specific Patterns

### Reading Parameters from a Config File

For repeatable runs on multiple datasets, read parameters from a Java properties
file rather than hard-coding them in the script:

```groovy
// Read parameters from a Java properties file
def props = new Properties()
new File("/path/to/params.properties").withInputStream { props.load(it) }
def xmlPath  = props.getProperty("xml_path")
def tilesX   = props.getProperty("tiles_x").toInteger()
def tilesY   = props.getProperty("tiles_y").toInteger()
```

---

### Checking Processing Completed

Because IJ.run() is synchronous in Fiji's scripting engine, each step completes
before the next line executes. You can verify success by checking file creation:

```groovy
import ij.IJ
import java.io.File

def xmlPath = "/path/to/data/dataset.xml"

if (!new File(xmlPath).exists()) {
    IJ.error("BigStitcher Pipeline", "XML file not found: " + xmlPath)
    return
}

IJ.run("Calculate pairwise shifts ...", "select=" + xmlPath + " ...")
IJ.log("Pairwise shifts done.")

IJ.run("Filter pairwise shifts ...", "select=" + xmlPath + " ...")
IJ.log("Filter done.")

IJ.run("Optimize globally and apply shifts ...", "select=" + xmlPath + " ...")
IJ.log("Global optimization done.")
```

---

## Critical Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Missing trailing comma in `fix_group_0-0,` | Optimization fails to fix reference frame | Always copy parameter strings from the Macro Recorder |
| Incorrect grid_type whitespace | Tiles arranged in wrong order | Use Macro Recorder to capture exact string |
| Re-saving to same path as input | File conflicts or data corruption | Set `dataset_save_path` to a different directory |
| Running fusion before global optimization | Fusion uses incorrect (unregistered) positions | Always complete Steps 2→3→4 (shifts → filter → optimize) before fusion |
| ICP refinement with wrong channel | Affine correction using inconsistent signal | Use Macro Recorder to confirm channel selection; match to channel with best signal |