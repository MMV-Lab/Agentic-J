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

## Core IJ.run() Commands

### 1. Define Dataset

```groovy
IJ.run("Define dataset ...",
    "define_dataset=[Automatic Loader (Bioformats based)] " +
    "project_filename=dataset.xml " +
    "path=/path/to/data/ " +
    "exclude=10 " +
    "pattern_0=Channels pattern_1=Tiles " +
    "modify_voxel_size? voxel_size_x=0.915 voxel_size_y=0.915 voxel_size_z=2.574 voxel_size_unit=µm " +
    "move_tiles_to_grid_(per_angle)?=[Move Tile to Grid (Macro-scriptable)] " +
    "grid_type=[Snake: Right & Down      ] " +
    "tiles_x=4 tiles_y=4 tiles_z=1 " +
    "overlap_x_(%)=10 overlap_y_(%)=10 overlap_z_(%)=10 " +
    "keep_metadata_rotation " +
    "how_to_load_images=[Re-save as multiresolution HDF5] " +
    "dataset_save_path=/path/to/data " +
    "check_stack_sizes " +
    "subsampling_factors=[{ {1,1,1}, {2,2,2}, {4,4,4} }] " +
    "hdf5_chunk_sizes=[{ {16,16,16}, {16,16,16}, {16,16,16} }] " +
    "timepoints_per_partition=1 setups_per_partition=0 " +
    "use_deflate_compression " +
    "export_path=/path/to/data/dataset")
```

> **Note on grid_type whitespace**: the grid type string must include the exact
> trailing whitespace as recorded by the macro recorder. Copy-paste from recorder
> output rather than typing manually.

---

### 2. Calculate Pairwise Shifts

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

### 3. Filter Pairwise Shifts

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

### 4. Global Optimization

```groovy
IJ.run("Optimize globally and apply shifts ...",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "relative=2.500 absolute=3.500 " +
    "global_optimization_strategy=" +
    "[Two-Round using Metadata to align unconnected Tiles] " +
    "fix_group_0-0,")
```

> `fix_group_0-0,` fixes the first tile as the reference frame. Always include
> the trailing comma — it is part of the recorded parameter string.

---

### 5. ICP Affine Refinement (Optional)

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

### 6. Fuse Dataset

```groovy
IJ.run("Fuse dataset ...",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "bounding_box=[All Views] " +
    "downsampling=1 " +
    "pixel_type=[16-bit unsigned integer] " +
    "interpolation=[Linear Interpolation] " +
    "image=[Precompute Image] " +
    "blend " +
    "produce=[Each timepoint & channel] " +
    "fused_image=[Save as (compressed) TIFF stacks] " +
    "output_file_directory=/path/to/output/")
```

---

### 7. Select Best Illumination (Optional — dual-sided lightsheet only)

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
