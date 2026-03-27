# BigStitcher — UI Parameter Guide

This reference lists every parameter exposed in BigStitcher's GUI dialogs. The
macro-recordable Batch Processing counterparts of each step use the same
parameter names (with underscores and lowercase).

---

## Define Dataset Dialog

**Menu:** Plugins › BigStitcher › BigStitcher → (first run) or
Plugins › BigStitcher › Batch Processing › Define dataset…

| Parameter | Values / Notes |
|---|---|
| **define_dataset** | Loader type. `Automatic Loader (Bioformats based)` (recommended); `Manual Loader (TIFF only, ImageJ Opener)`; `Manual Loader (TIFF only, Bio-Formats)` |
| **project_filename** | Filename of the XML project file to create (e.g. `dataset.xml`) |
| **path** | Directory containing the raw image files |
| **exclude** | Minimum file size in bytes to include (use `10` to skip empty files) |
| **pattern_0…pattern_N** | Dataset dimension assignment for auto-detected groups. e.g. `Channels`, `Tiles`, `Angles`, `Illuminations`, `Timepoints` |
| **modify_voxel_size?** | Tick to override voxel size from metadata |
| **voxel_size_x / _y / _z** | Physical voxel size in voxel_size_unit |
| **voxel_size_unit** | Unit string, e.g. `µm`, `nm`, `pixels` |
| **move_tiles_to_grid_(per_angle)?** | Grid arrangement method. Options: `Do not move Tiles to Grid (use Metadata if available)`, `Move Tile to Grid (Macro-scriptable)`, `Move Tiles to Grid (interactive)` |
| **grid_type** | Scan direction. `Right & Down`, `Left & Down`, `Right & Up`, `Left & Up`, `Snake: Right & Down`, `Snake: Left & Down`, `Snake: Right & Up`, `Snake: Left & Up` |
| **tiles_x / tiles_y / tiles_z** | Number of tiles along each axis |
| **overlap_x_(%) / overlap_y_(%) / overlap_z_(%)** | Expected tile overlap percentage |
| **keep_metadata_rotation** | Preserve rotation from metadata |
| **how_to_load_images** | Storage backend. `Re-save as multiresolution HDF5` (recommended); `Load raw data directly (TIFF only)`; `Virtual Load raw data (TIFF only)` |
| **dataset_save_path** | Directory where HDF5 files will be written |
| **check_stack_sizes** | Verify that all tiles have identical dimensions |
| **subsampling_factors** | Multi-resolution pyramid levels, e.g. `[{ {1,1,1}, {2,2,2}, {4,4,4} }]` |
| **hdf5_chunk_sizes** | HDF5 chunk dimensions per resolution, e.g. `[{ {16,16,16}, {16,16,16}, {16,16,16} }]` |
| **timepoints_per_partition** | HDF5 partition size (number of timepoints per HDF5 file) |
| **setups_per_partition** | HDF5 partition size (number of setups per HDF5 file; `0` = all in one file) |
| **use_deflate_compression** | Enable DEFLATE compression in HDF5 output |
| **export_path** | Base path for HDF5 export (no extension; produces `dataset.h5` + `dataset.xml`) |

---

## Calculate Pairwise Shifts Dialog

**Menu:** BigStitcher window → Calculate Pairwise Shifts  
**Batch:** Plugins › BigStitcher › Batch Processing › Calculate pairwise shifts…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **process_angle** | `All angles` or a specific angle name |
| **process_channel** | `All channels` or a specific channel |
| **process_illumination** | `All illuminations` or a specific illumination |
| **process_tile** | `All tiles` or a specific tile |
| **process_timepoint** | `All Timepoints` or a specific timepoint |
| **method** | `Phase Correlation` (default); `Lucas-Kanade` |
| **channels** | How to handle multiple channels: `Average Channels`, `Best Channel`, or a specific channel name |
| **downsample_in_x / _y / _z** | Downsampling factor for phase correlation (1=full res; 2=2× downsampled; 4=4× downsampled — recommended for most data) |
| **use_linked_interest_points** (advanced) | Use previously detected interest points rather than intensity-based correlation |

---

## Filter Pairwise Shifts Dialog

**Menu:** BigStitcher window → Filter Pairwise Shifts (Link Explorer)
**Batch:** Plugins › BigStitcher › Batch Processing › Filter pairwise shifts…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **filter_by_link_quality** | Enable filtering by correlation coefficient |
| **min_r** | Minimum acceptable correlation coefficient (typical: `0.7`) |
| **max_r** | Maximum (always `1`) |
| **max_shift_in_x / _y / _z** | Maximum allowed shift in pixels (0 = no constraint) |
| **max_displacement** | Maximum allowed Euclidean shift magnitude (0 = no constraint) |

---

## Global Optimization Dialog

**Menu:** BigStitcher window → Optimize Globally and Apply Shifts  
**Batch:** Plugins › BigStitcher › Batch Processing › Optimize globally and apply shifts…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **process_angle / channel / illumination / tile / timepoint** | As in Pairwise Shifts dialog |
| **relative** | Relative error threshold for iterative link removal (default: `2.5`) |
| **absolute** | Absolute error threshold in pixels (default: `3.5`) |
| **global_optimization_strategy** | `Simple One-Round` or `Two-Round using Metadata to align unconnected Tiles` (recommended when sparse empty-tile regions exist) |
| **fix_group_0-0** | Fix the first tile group (group 0-0) as the reference; append additional fixed groups as `fix_group_X-Y` |

---

## ICP Refinement Dialog

**Menu:** BigStitcher window → ICP Refinement  
**Batch:** Plugins › BigStitcher › Batch Processing › ICP Refinement…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **process_angle / channel / illumination / tile / timepoint** | As before |
| **icp_refinement_type** | `Simple (tile registration)` or `Precise (use interest points if available)` |
| **transformation** | `Translation` · `Rigid` · `Affine` · `Split Affine` (affine per half-tile; corrects spherical aberration) |
| **icp_max_error** | Maximum acceptable ICP error in pixels; point pairs further apart are rejected |
| **icp_iterations** | Maximum ICP iterations per pair (default: `100`) |

---

## Illumination Selection Dialog

**Menu:** BigStitcher window → Select Best Illuminations  
**Batch:** Plugins › BigStitcher › Batch Processing › Select Best Illumination…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **selection_method** | `Average Intensity` · `Gradient Magnitude` · `Relative Fourier Ring Correlation` (most discriminating) |
| **process_timepoint** | `All Timepoints` or specific timepoint |

---

## Fusion Dialog

**Menu:** BigStitcher window → Fuse Dataset  
**Batch:** Plugins › BigStitcher › Batch Processing › Fuse dataset…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **process_angle / channel / illumination / tile / timepoint** | As before |
| **bounding_box** | `All Views` or the name of a previously defined bounding box |
| **downsampling** | Integer downsampling factor for output (1 = full resolution) |
| **pixel_type** | `8-bit unsigned integer` · `16-bit unsigned integer` · `32-bit floating point` |
| **interpolation** | `Nearest Neighbor` · `Linear Interpolation` (default) |
| **image** | `Precompute Image` (RAM) · `Virtual Image` (stream) |
| **blend** | Enable cosine-weighted blending at tile borders |
| **produce** | `Each timepoint & channel` · `All timepoints & channels` |
| **fused_image** | Output format: `Display in ImageJ` · `Save as (compressed) TIFF stacks` · `Save as BigDataViewer XML/HDF5` · `Save as N5` |
| **output_file_directory** | Directory for TIFF output |
| **export_path** | Base path for HDF5/N5 output |

---

## Interest Point Detection Dialog

**Menu:** BigStitcher MultiView mode → Interest Point Detection  
**Batch:** Plugins › BigStitcher › Batch Processing › Interest Point Detection…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **process_angle / channel / illumination / tile / timepoint** | As before |
| **type_of_interest_point_detection** | `Difference-of-Gaussian (DoG)` (default) · `Difference-of-Mean (DoM)` |
| **label** | Name for this set of interest points (e.g. `beads`, `nuclei`) |
| **sigma** | DoG inner Gaussian sigma (in pixels) |
| **threshold** | Minimum DoG response; lower = more points detected |
| **find_maxima** | `Maxima only` · `Minima only` · `Both` |
| **minimal_distance_between_interest_points** | Minimum separation between adjacent detections (pixels) |
| **subpixel_localization** | Enable sub-pixel refinement via quadratic fit |

---

## MultiView Registration Dialog

**Menu:** BigStitcher MultiView mode → Registration  
**Batch:** Plugins › Multiview Reconstruction › Batch Processing › Register Dataset…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **transformation** | `Translation` · `Rigid` · `Affine` (default for multi-view) |
| **interest_points** | Name of the interest point set to use (must exist) |
| **method** | `Fast Rotation-Invariant (Geometric Hashing)` · `Translation-Invariant (Redundant)` · `ICP (Iterative Closest Point)` · `Center of Mass` |
| **downsample_xyz** | Downsampling factor for interest-point based registration |
| **fix_views** | `Fix first view` · `Fix all views` · `Do not fix views` |
| **number_of_neighbors** | Number of nearest neighbours for geometric descriptor (default: `3`) |
| **significance** | Ratio test threshold for descriptor matching (default: `3`) |
| **ransac_iterations** | Number of RANSAC iterations (default: `1000`) |
| **max_epsilon** | RANSAC inlier threshold in world coordinates |

---

## Bounding Box Dialog

**Menu:** BigStitcher window → Bounding Box → Define Bounding Box  

| Parameter | Values / Notes |
|---|---|
| **bounding_box** | Definition mode: `Define using BigDataViewer interactively` · `Enter coordinates manually` |
| **name** | Name for this bounding box (referenced later in Fusion) |
| **x min / x max / y min / y max / z min / z max** | Coordinate bounds in global world coordinates |

---

## FRC Quality Control Dialog

**Menu:** BigStitcher window → FRC Quality Control  

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **frc_type** | `FRC` (standard) · `Relative FRC` (rFRC — accounts for camera-pattern background; recommended) |
| **block_size** | Size of the FRC computation block in pixels (e.g. `128` for fine spatial resolution; `512` for whole-brain datasets) |
| **spacing** | Pixel spacing between block centres |
| **use_subset_of_data** | Restrict FRC computation to a bounding box |

---

## Flat-Field Correction Dialog

**Menu:** BigStitcher window → Flat-field Correction  

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **flat_field_file** | Path to a bright reference image (TIFF) |
| **dark_field_file** | Path to a dark reference image (TIFF; optional — assumed zero if absent) |
| **assignment** | Which (channel, illumination) pair to apply the correction to |
| **caching** | Enable caching of corrected planes for repeated access |

---

## Brightness and Contrast Adjustment Dialog

**Menu:** BigStitcher window → Brightness/Contrast Adjustment  
**Batch:** Plugins › BigStitcher › Batch Processing › Brightness/Contrast Adjustment…

| Parameter | Values / Notes |
|---|---|
| **select** | Path to the dataset XML file |
| **process_angle / channel / illumination / tile / timepoint** | As before |
| **relative_lambda1** | Weight for full linear (α, β) transform component |
| **relative_lambda2** | Weight for additive (β only) component |
| **relative_lambda3** | Weight for identity (no change) component; prevents trivial zero solution |
| **downsample_for_adjustment** | Downsampling factor for computing adjustments (default: `4` or `8`) |
