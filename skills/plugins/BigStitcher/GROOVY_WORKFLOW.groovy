/*
Purpose: BigStitcher batch-preflight and reconstruction workflow template.
Inputs: Hardcoded BigStitcher project XML at /app/data/projects/bigstitcher_skill_validation/raw_images/dataset.xml
Outputs: Log text file, optional fused outputs from BigStitcher, and a diagnostic TIFF with scale bar.
Tested version: Fiji/ImageJ in this environment (BigStitcher not installed; preflight branch executed successfully).
*/

import ij.IJ
import ij.ImagePlus
import ij.Menus
import ij.io.FileSaver
import java.io.File

final String projectRoot = "/app/data/projects/bigstitcher_skill_validation"
final String rawDir = projectRoot + "/raw_images"
final String outDir = projectRoot + "/processed_images"
final String dataDir = projectRoot + "/data"
final String xmlPath = rawDir + "/dataset.xml"
final String logPath = dataDir + "/bigstitcher_run_log.txt"
final String diagTif = outDir + "/bigstitcher_diagnostic_scale_bar.tif"

new File(outDir).mkdirs()
new File(dataDir).mkdirs()

StringBuilder log = new StringBuilder()
log.append("BigStitcher workflow run\n")
log.append("Project root: " + projectRoot + "\n")

boolean hasDefine = Menus.getCommands()?.containsKey("Define dataset ...")
boolean hasPairwise = Menus.getCommands()?.containsKey("Calculate pairwise shifts ...")
boolean hasFilter = Menus.getCommands()?.containsKey("Filter pairwise shifts ...")
boolean hasOptimize = Menus.getCommands()?.containsKey("Optimize globally and apply shifts ...")
boolean hasFuse = Menus.getCommands()?.containsKey("Fuse dataset ...")

log.append("Commands present: define="+hasDefine+", pairwise="+hasPairwise+", filter="+hasFilter+", optimize="+hasOptimize+", fuse="+hasFuse+"\n")

try {
    if (hasPairwise && hasFilter && hasOptimize && hasFuse && new File(xmlPath).exists()) {
        try {
            IJ.run("Calculate pairwise shifts ...", "select=" + xmlPath + " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] method=[Phase Correlation] channels=[Average Channels] downsample_in_x=2 downsample_in_y=2 downsample_in_z=2")
            log.append("Pairwise shifts: OK\n")
        } catch (Throwable t) {
            log.append("Pairwise shifts: FAIL " + t.getMessage() + "\n")
        }

        try {
            IJ.run("Filter pairwise shifts ...", "select=" + xmlPath + " filter_by_link_quality min_r=0.7 max_r=1 max_shift_in_x=0 max_shift_in_y=0 max_shift_in_z=0 max_displacement=0")
            log.append("Filter pairwise shifts: OK\n")
        } catch (Throwable t) {
            log.append("Filter pairwise shifts: FAIL " + t.getMessage() + "\n")
        }

        try {
            IJ.run("Optimize globally and apply shifts ...", "select=" + xmlPath + " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] relative=2.500 absolute=3.500 global_optimization_strategy=[Two-Round using Metadata to align unconnected Tiles] fix_group_0-0,")
            log.append("Global optimization: OK\n")
        } catch (Throwable t) {
            log.append("Global optimization: FAIL " + t.getMessage() + "\n")
        }

        try {
            IJ.run("Fuse dataset ...", "select=" + xmlPath + " process_angle=[All angles] process_channel=[All channels] process_illumination=[All illuminations] process_tile=[All tiles] process_timepoint=[All Timepoints] bounding_box=[All Views] downsampling=1 pixel_type=[16-bit unsigned integer] interpolation=[Linear Interpolation] image=[Precompute Image] blend produce=[Each timepoint & channel] fused_image=[Save as (compressed) TIFF stacks] output_file_directory=" + outDir)
            log.append("Fusion: OK\n")
        } catch (Throwable t) {
            log.append("Fusion: FAIL " + t.getMessage() + "\n")
        }
    } else {
        log.append("BigStitcher commands unavailable or dataset.xml missing; skipped reconstruction steps.\n")
    }

    ImagePlus diag = IJ.createImage("BigStitcher_Diagnostic", "8-bit black", 512, 256, 1)
    if (diag == null) { println "ERROR: Could not create diagnostic image"; return }
    diag.getProcessor().setValue(180)
    diag.getProcessor().setRoi(40, 80, 420, 80)
    diag.getProcessor().fill()
    IJ.run(diag, "Scale Bar...", "width=100 height=8 font=20 color=White background=None location=[Lower Right] bold overlay")
    new FileSaver(diag).saveAsTiff(diagTif)
    diag.close()
    log.append("Saved diagnostic image: " + diagTif + "\n")

} catch (Throwable e) {
    log.append("Unexpected failure: " + e.getMessage() + "\n")
}

new File(logPath).text = log.toString()
println log.toString()
println "=== WORKFLOW COMPLETE ==="
