/**
 * BIGSTITCHER_WORKFLOW_TILE_STITCHING.groovy
 * BigStitcher — Full Tile Stitching Pipeline
 *
 * PURPOSE:
 *   Drives the complete BigStitcher tile stitching pipeline:
 *     1. Define dataset and re-save as multiresolution HDF5
 *     2. Calculate pairwise shifts (phase correlation)
 *     3. Filter links by correlation threshold
 *     4. Global optimization
 *     5. (Optional) ICP affine refinement
 *     6. Fuse and save as TIFF stacks
 *
 * HOW TO RUN:
 *   1. Open Fiji
 *   2. Plugins › Script Editor
 *   3. Set language to Groovy
 *   4. Edit the PARAMETERS block below
 *   5. Run › Run Script (Ctrl+R)
 *
 * REQUIREMENTS:
 *   - Fiji with BigStitcher installed (Help › Update… → BigStitcher update site)
 *   - Input data in any Bio-Formats-supported format or TIFF
 *
 * ARCHITECTURE NOTE:
 *   BigStitcher uses IJ.run() calls into macro-recordable Batch Processing commands.
 *   All processing steps modify an XML project file on disk. Each IJ.run() call
 *   is synchronous — the next line does not execute until the step is complete.
 */

import ij.IJ
import java.io.File

// ============================================================
// PARAMETERS — edit these for your dataset
// ============================================================

// Directory containing the raw input image files
def INPUT_DIR = "/data/raw/experiment01/"

// Output directory for HDF5 files and fusion results
// Can be the same as INPUT_DIR; a subdirectory is cleaner
def OUTPUT_DIR = "/data/processed/experiment01/"

// Name of the XML project file (will be created in OUTPUT_DIR)
def PROJECT_NAME = "dataset.xml"

// Number of tiles in X and Y (from your acquisition settings)
def TILES_X = 4
def TILES_Y = 4
def TILES_Z = 1   // set to > 1 only for 3D tile grids

// Tile acquisition scan direction.
// Options: "Right & Down", "Left & Down", "Right & Up", "Left & Up",
//          "Snake: Right & Down", "Snake: Left & Down" (most common for stage scans)
def GRID_TYPE = "Snake: Right & Down      "
// NOTE: trailing whitespace IS significant — it is part of BigStitcher's
// internal string key. Confirm with Macro Recorder if you get errors.

// Approximate tile overlap percentage from acquisition settings
def OVERLAP_X_PCT = 10
def OVERLAP_Y_PCT = 10
def OVERLAP_Z_PCT = 10

// Voxel size — leave at 0 to use metadata; set if metadata is missing or wrong
def VOXEL_SIZE_X = 0.915   // µm (set to 0 to use metadata)
def VOXEL_SIZE_Y = 0.915
def VOXEL_SIZE_Z = 2.574

// Phase correlation downsampling (2 = recommended; 4 = faster/coarser; 1 = full res)
def DOWNSAMPLE_PC = 2

// Minimum acceptable correlation coefficient for links (0.7 is typical)
def MIN_CORRELATION = 0.7

// Run ICP affine refinement after global optimization?
def RUN_ICP = false
def ICP_TRANSFORMATION = "Affine"  // "Translation", "Rigid", "Affine", "Split Affine"
def ICP_MAX_ERROR = 5.0
def ICP_ITERATIONS = 100

// Output pixel type for fusion
// Options: "8-bit unsigned integer", "16-bit unsigned integer", "32-bit floating point"
def PIXEL_TYPE = "16-bit unsigned integer"

// Fusion downsampling (1 = full resolution; 2 = 2× downsampled preview)
def FUSION_DOWNSAMPLING = 1

// ============================================================
// SETUP
// ============================================================

def inputDir  = new File(INPUT_DIR)
def outputDir = new File(OUTPUT_DIR)
def xmlFile   = new File(outputDir, PROJECT_NAME)
def xmlPath   = xmlFile.absolutePath

if (!inputDir.isDirectory()) {
    IJ.error("BigStitcher Pipeline", "Input directory not found:\n" + INPUT_DIR)
    return
}

outputDir.mkdirs()
IJ.log("=" * 60)
IJ.log("BigStitcher Tile Stitching Pipeline")
IJ.log("Input  : " + INPUT_DIR)
IJ.log("Output : " + OUTPUT_DIR)
IJ.log("XML    : " + xmlPath)
IJ.log("Grid   : " + TILES_X + " x " + TILES_Y + " x " + TILES_Z)
IJ.log("=" * 60)

// ============================================================
// STEP 1 — DEFINE DATASET AND RE-SAVE AS HDF5
// ============================================================

IJ.log("\n[Step 1] Defining dataset and re-saving as HDF5...")

def exportPath = new File(outputDir, "dataset").absolutePath  // no extension

IJ.run("Define dataset ...",
    "define_dataset=[Automatic Loader (Bioformats based)] " +
    "project_filename=" + PROJECT_NAME + " " +
    "path=" + INPUT_DIR + " " +
    "exclude=10 " +
    "pattern_0=Channels pattern_1=Tiles " +
    "modify_voxel_size? " +
    "voxel_size_x=" + VOXEL_SIZE_X + " " +
    "voxel_size_y=" + VOXEL_SIZE_Y + " " +
    "voxel_size_z=" + VOXEL_SIZE_Z + " " +
    "voxel_size_unit=µm " +
    "move_tiles_to_grid_(per_angle)?=[Move Tile to Grid (Macro-scriptable)] " +
    "grid_type=[" + GRID_TYPE + "] " +
    "tiles_x=" + TILES_X + " tiles_y=" + TILES_Y + " tiles_z=" + TILES_Z + " " +
    "overlap_x_(%)=" + OVERLAP_X_PCT + " " +
    "overlap_y_(%)=" + OVERLAP_Y_PCT + " " +
    "overlap_z_(%)=" + OVERLAP_Z_PCT + " " +
    "keep_metadata_rotation " +
    "how_to_load_images=[Re-save as multiresolution HDF5] " +
    "dataset_save_path=" + OUTPUT_DIR + " " +
    "check_stack_sizes " +
    "subsampling_factors=[{ {1,1,1}, {2,2,2}, {4,4,4} }] " +
    "hdf5_chunk_sizes=[{ {16,16,16}, {16,16,16}, {16,16,16} }] " +
    "timepoints_per_partition=1 setups_per_partition=0 " +
    "use_deflate_compression " +
    "export_path=" + exportPath)

if (!xmlFile.exists()) {
    IJ.error("BigStitcher Pipeline", "Dataset definition failed — XML not created:\n" + xmlPath)
    return
}
IJ.log("Dataset defined: " + xmlPath)

// ============================================================
// STEP 2 — CALCULATE PAIRWISE SHIFTS
// ============================================================

IJ.log("\n[Step 2] Calculating pairwise shifts (Phase Correlation, DS=" + DOWNSAMPLE_PC + ")...")

IJ.run("Calculate pairwise shifts ...",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "method=[Phase Correlation] " +
    "channels=[Average Channels] " +
    "downsample_in_x=" + DOWNSAMPLE_PC + " " +
    "downsample_in_y=" + DOWNSAMPLE_PC + " " +
    "downsample_in_z=" + DOWNSAMPLE_PC)

IJ.log("Pairwise shifts calculated.")

// ============================================================
// STEP 3 — FILTER PAIRWISE SHIFTS
// ============================================================

IJ.log("\n[Step 3] Filtering links (min_r=" + MIN_CORRELATION + ")...")

IJ.run("Filter pairwise shifts ...",
    "select=" + xmlPath + " " +
    "filter_by_link_quality " +
    "min_r=" + MIN_CORRELATION + " " +
    "max_r=1 " +
    "max_shift_in_x=0 max_shift_in_y=0 max_shift_in_z=0 " +
    "max_displacement=0")

IJ.log("Links filtered.")

// ============================================================
// STEP 4 — GLOBAL OPTIMIZATION
// ============================================================

IJ.log("\n[Step 4] Running global optimization...")

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

IJ.log("Global optimization complete.")

// ============================================================
// STEP 5 — ICP AFFINE REFINEMENT (OPTIONAL)
// ============================================================

if (RUN_ICP) {
    IJ.log("\n[Step 5] Running ICP " + ICP_TRANSFORMATION + " refinement...")

    IJ.run("ICP Refinement ...",
        "select=" + xmlPath + " " +
        "process_angle=[All angles] " +
        "process_channel=[All channels] " +
        "process_illumination=[All illuminations] " +
        "process_tile=[All tiles] " +
        "process_timepoint=[All Timepoints] " +
        "icp_refinement_type=[Simple (tile registration)] " +
        "transformation=[" + ICP_TRANSFORMATION + "] " +
        "icp_max_error=" + ICP_MAX_ERROR + " " +
        "icp_iterations=" + ICP_ITERATIONS)

    IJ.log("ICP refinement complete.")
} else {
    IJ.log("\n[Step 5] ICP refinement skipped (RUN_ICP=false).")
}

// ============================================================
// STEP 6 — FUSE DATASET
// ============================================================

IJ.log("\n[Step 6] Fusing dataset...")

IJ.run("Fuse dataset ...",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "bounding_box=[All Views] " +
    "downsampling=" + FUSION_DOWNSAMPLING + " " +
    "pixel_type=[" + PIXEL_TYPE + "] " +
    "interpolation=[Linear Interpolation] " +
    "image=[Precompute Image] " +
    "blend " +
    "produce=[Each timepoint & channel] " +
    "fused_image=[Save as (compressed) TIFF stacks] " +
    "output_file_directory=" + OUTPUT_DIR)

IJ.log("Fusion complete.")

// ============================================================
// SUMMARY
// ============================================================

IJ.log("\n" + "=" * 60)
IJ.log("BigStitcher Pipeline Complete")
IJ.log("XML project : " + xmlPath)
IJ.log("Fused output: " + OUTPUT_DIR)
IJ.log("=" * 60)
