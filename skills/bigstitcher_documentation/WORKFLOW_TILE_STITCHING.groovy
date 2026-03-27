import ij.IJ
import java.io.File

// Define constants

def INPUT_DIR  = "/app/data/projects/Big_stitcher_test_run/raw_images/Grid_2d/"
def OUTPUT_DIR = "/app/data/projects/Big_stitcher_test_run/processed_images/"
def TILES_X = 4
def TILES_Y = 4
def TILES_Z = 1
def OVERLAP_X = 10
def OVERLAP_Y = 10
def OVERLAP_Z = 10
def VOXEL_SIZE_X = 0.915
def VOXEL_SIZE_Y = 0.915
def VOXEL_SIZE_Z = 2.574
def GRID_TYPE = "[Snake: Right & Down      ]"
def DOWNSAMPLE_PC = 2
def MIN_CORRELATION = 0.7
def RUN_ICP = false
def ICP_TRANSFORMATION = "Affine"
def ICP_MAX_ERROR = 5.0
def ICP_ITERATIONS = 100
def PIXEL_TYPE = "32-bit floating point"
def FUSION_DOWNSAMPLING = 1

def xmlPath   = new File(OUTPUT_DIR, "dataset.xml").absolutePath
def outputDir = new File(OUTPUT_DIR)
outputDir.mkdirs()

// Define global optimization strategy
final String GLOBAL_OPT_STRATEGY = "Two-Round using metadata to align unconnected Tiles"
Set<String> allowedStrategies = new HashSet<>(Arrays.asList(
    "One-Round",
    "One-Round with iterative dropping of bad links",
    "Two-Round using metadata to align unconnected Tiles",
    "Two-Round using Metadata to align unconnected Tiles and iterative dropping of bad links",
    "NO global optimization, just store the corresponding interest points"
))

if (!allowedStrategies.contains(GLOBAL_OPT_STRATEGY)) {
    IJ.error("Invalid global optimization strategy: " + GLOBAL_OPT_STRATEGY)
    return
}

IJ.runMacro("setBatchMode(true);")

IJ.log("=" * 60)
IJ.log("BigStitcher Tile Stitching Pipeline")
IJ.log("Input  : " + INPUT_DIR)
IJ.log("Output : " + OUTPUT_DIR)
IJ.log("Grid   : " + TILES_X + " x " + TILES_Y + " x " + TILES_Z)
IJ.log("=" * 60)

IJ.log("\n[Step 1] Defining dataset and re-saving as HDF5...")

def exportPath = new File(OUTPUT_DIR, "dataset").absolutePath

IJ.run("Define Multi-View Dataset",
    "define_dataset=[Automatic Loader (Bioformats based)] " +
    "project_filename=dataset.xml " +
    "path=" + INPUT_DIR + " " +
    "exclude=10 " +
    "pattern_0=Tiles " +
    "modify_voxel_size? " +
    "voxel_size_x=" + VOXEL_SIZE_X + " " +
    "voxel_size_y=" + VOXEL_SIZE_Y + " " +
    "voxel_size_z=" + VOXEL_SIZE_Z + " " +
    "voxel_size_unit=µm " +
    "move_tiles_to_grid_(per_angle)?=[Move Tile to Grid (Macro-scriptable)] " +
    "grid_type=" + GRID_TYPE + " " +
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
    "export_path=" + exportPath)

// XML fallback selection logic AFTER Step 1
if (!(new File(xmlPath).exists())) {
    def fallbackFiles = new File(OUTPUT_DIR).listFiles()?.findAll { it.name.startsWith("dataset.xml~") }
    if (fallbackFiles) {
        def latestFallback = fallbackFiles.sort { it.lastModified() }.last()
        xmlPath = latestFallback.absolutePath
    }
}

if (!new File(xmlPath).exists()) {
    IJ.error("BigStitcher Pipeline",
        "Dataset definition failed — XML not created.\n\n" +
        "Most likely cause: GRID_TYPE has wrong trailing spaces.\n" +
        "Fix: open Plugins › Macros › Record… and run Define Dataset\n" +
        "manually to capture the exact grid_type string for your version.")
    IJ.runMacro("setBatchMode(false);")
    return
}
IJ.log("Dataset defined: " + xmlPath)

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

IJ.log("\n[Step 3] Filtering links (min_r=" + MIN_CORRELATION + ")...")

IJ.run("Filter pairwise shifts ...",
    "select=" + xmlPath + " " +
    "filter_by_link_quality " +
    "min_r=" + MIN_CORRELATION + " " +
    "max_r=1 " +
    "max_shift_in_x=0 max_shift_in_y=0 max_shift_in_z=0 " +
    "max_displacement=0")

IJ.log("Links filtered.")

IJ.log("\n[Step 4] Running global optimization...")


IJ.run("Optimize globally and apply shifts ...",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "relative=2.500 absolute=3.500 " +
    "global_optimization_strategy=["+ GLOBAL_OPT_STRATEGY +"] " +
    "fix_group_0-0,")

IJ.log("Global optimization complete.")

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

IJ.log("\n[Step 6] Fusing dataset...")

IJ.run("Image Fusion",
    "select=" + xmlPath + " " +
    "process_angle=[All angles] " +
    "process_channel=[All channels] " +
    "process_illumination=[All illuminations] " +
    "process_tile=[All tiles] " +
    "process_timepoint=[All Timepoints] " +
    "bounding_box=[All Views] " +
    "downsampling=" + FUSION_DOWNSAMPLING + " " +
    "pixel_type=[32-bit floating point] " +
    "interpolation=[Linear Interpolation] " +
    "image=[Precompute Image] " +
    "blend " +
    "produce=[Each timepoint & channel] " +
    "fused_image=[Save as (compressed) TIFF stacks] " +
    "output_file_directory=" + OUTPUT_DIR)

IJ.log("Fusion complete.")

IJ.log("\n" + "=" * 60)
IJ.log("BigStitcher Pipeline Complete")
IJ.log("XML project : " + xmlPath)
IJ.log("Fused output: " + OUTPUT_DIR)
IJ.log("=" * 60)

IJ.runMacro("setBatchMode(false);")
