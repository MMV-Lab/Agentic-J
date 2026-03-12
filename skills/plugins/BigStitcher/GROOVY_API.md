# BigStitcher Groovy / Macro API (Evidence-based)

> Important: BigStitcher exposes most scriptable functionality through **macro-recordable batch commands**. Exact option strings are best generated with Fiji Macro Recorder and then adapted.

## Confirmed command strings from official Headless page

### `IJ.run("Define dataset ...", "...")`

| Parameter | Type | Default | Description |
|---|---|---:|---|
| define_dataset | enum string | [UNDOCUMENTED] | Loader type (example: `Automatic Loader (Bioformats based)`) |
| project_filename | string | [UNDOCUMENTED] | Project XML filename |
| path | path string | [UNDOCUMENTED] | Input image search path/pattern |
| pattern_0, pattern_1 | string | [UNDOCUMENTED] | Grouping keys (example: Channels, Tiles) |
| modify_voxel_size? | flag | off | Whether to override voxel size |
| voxel_size_x/y/z | number | [UNDOCUMENTED] | Voxel dimensions |
| voxel_size_unit | string | [UNDOCUMENTED] | Unit label |
| move_tiles_to_grid_(per_angle)? | enum/flag | [UNDOCUMENTED] | Optional grid re-layout |
| grid_type, tiles_x/y/z, overlap_x/y/z_(%) | mixed | [UNDOCUMENTED] | Grid layout settings |
| how_to_load_images | enum | [UNDOCUMENTED] | Storage strategy (example: re-save as HDF5) |
| dataset_save_path, export_path | path string | [UNDOCUMENTED] | Output paths |

**Side effects:** Creates/updates dataset project files (`.xml` plus backing data).  
**Headless-safe:** YES (officially documented).  
**Evidence source:** https://imagej.net/plugins/bigstitcher/headless

---

### `IJ.run("Calculate pairwise shifts ...", "...")`

| Parameter | Type | Default | Description |
|---|---|---:|---|
| select | path string | [UNDOCUMENTED] | Input dataset XML |
| process_angle/channel/illumination/tile/timepoint | selection string | [UNDOCUMENTED] | Which views to process |
| method | enum string | [UNDOCUMENTED] | Shift method (example: `Phase Correlation`) |
| channels | enum string | [UNDOCUMENTED] | Channel policy (example: `Average Channels`) |
| downsample_in_x/y/z | int | [UNDOCUMENTED] | Downsampling factors |

**Side effects:** Computes pairwise links/shifts for stitching graph.  
**Headless-safe:** YES.  
**Evidence source:** https://imagej.net/plugins/bigstitcher/headless

---

### `IJ.run("Filter pairwise shifts ...", "...")`

| Parameter | Type | Default | Description |
|---|---|---:|---|
| select | path string | [UNDOCUMENTED] | Input dataset XML |
| filter_by_link_quality | flag | off | Enable quality filter |
| min_r, max_r | float | [UNDOCUMENTED] | Correlation quality bounds |
| max_shift_in_x/y/z | float | [UNDOCUMENTED] | Optional axis-specific cutoffs |
| max_displacement | float | [UNDOCUMENTED] | Overall displacement cutoff |

**Side effects:** Removes weak/invalid pairwise links.  
**Headless-safe:** YES.  
**Evidence source:** https://imagej.net/plugins/bigstitcher/headless

---

### `IJ.run("Optimize globally and apply shifts ...", "...")`

| Parameter | Type | Default | Description |
|---|---|---:|---|
| select | path string | [UNDOCUMENTED] | Input dataset XML |
| process_* | selection string | [UNDOCUMENTED] | Which views to optimize |
| relative | float | [UNDOCUMENTED] | Relative threshold for optimization |
| absolute | float | [UNDOCUMENTED] | Absolute threshold |
| global_optimization_strategy | enum string | [UNDOCUMENTED] | Strategy (example: Two-Round...) |
| fix_group_0-0, ... | token list | [UNDOCUMENTED] | Fixed reference groups |

**Side effects:** Writes global transforms to project state.  
**Headless-safe:** YES.  
**Evidence source:** https://imagej.net/plugins/bigstitcher/headless

---

### `IJ.run("Fuse dataset ...", "...")`

| Parameter | Type | Default | Description |
|---|---|---:|---|
| select | path string | [UNDOCUMENTED] | Input dataset XML |
| process_* | selection string | [UNDOCUMENTED] | Which views to fuse |
| bounding_box | enum/string | [UNDOCUMENTED] | Volume to fuse |
| downsampling | int/float | [UNDOCUMENTED] | Output downsampling |
| pixel_type | enum string | [UNDOCUMENTED] | Output pixel type |
| interpolation | enum string | [UNDOCUMENTED] | Interpolation method |
| image | enum string | [UNDOCUMENTED] | Compute strategy |
| blend | flag | [UNDOCUMENTED] | Blend overlapping views |
| produce | enum string | [UNDOCUMENTED] | Output partitioning |
| fused_image | enum string | [UNDOCUMENTED] | Save target format |
| output_file_directory | path string | [UNDOCUMENTED] | Output folder |

**Side effects:** Produces fused image files (e.g., TIFF stacks).  
**Headless-safe:** YES.  
**Evidence source:** https://imagej.net/plugins/bigstitcher/headless

---

## UI-only vs scriptable
- Core reconstruction steps above are documented as macro-scriptable.
- Many additional options are available in full GUI and may require macro recording to discover exact tokens.

## Quirks / limitations
- Command string includes ellipsis and exact spacing (e.g., `"Define dataset ..."`); typos will fail.
- Parameter token names are not comprehensively documented in one API reference.
- Best practice: record once with Macro Recorder, then adapt paths/selection values.
