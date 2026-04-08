import ij.IJ
import ij.ImagePlus
import ij.WindowManager
import ij.plugin.frame.Editor
import ij.text.TextPanel
import ij.text.TextWindow
import ij.measure.ResultsTable
import java.io.File

/*
 * ============================================================================
 * COLOC2_FIXED_WORKFLOW_NO_DIALOG.groovy
 * ============================================================================
 * PURPOSE (for non-programmers):
 * - This script runs a fixed Coloc 2 colocalization workflow on the CURRENT
 *   active image in Fiji/ImageJ.
 *
 * WHAT THE SCRIPT EXPECTS:
 * - You must have an active RGB image selected when running this script.
 * - If no image is active, or the active image is not RGB, the script stops.
 *
 * WHAT THE SCRIPT DOES (step-by-step):
 * 1) Reads the active image.
 * 2) Makes a duplicate working copy (original is never modified).
 * 3) Splits the working RGB image into color channels.
 * 4) Selects RED and BLUE channels.
 * 5) Runs Coloc 2 with fixed parameters.
 * 6) Saves Coloc-related log text and Results table to disk.
 * 7) Cleans up temporary working/split images.
 *
 * OUTPUT FILES (saved here):
 * - Folder: /app/data/projects/coloc2_blue_red_whole_image/data
 * - Log file: coloc2_fixed_blue_red_log.txt
 * - Results CSV: coloc2_fixed_blue_red_results_table.csv
 *
 * IF YOU WANT DIFFERENT CHANNELS OR SETTINGS:
 * - Channel choice is defined by expected split titles '(red)' and '(blue)'.
 *   Change those title targets if you want different channels.
 * - Coloc iterations are set by: number_of_iterations=50
 *   Change this value in the args list if needed.
 * ============================================================================
 */

// Get the currently active image window.
ImagePlus original = WindowManager.getCurrentImage()
if (original == null) {
    // Stop early if no image is selected/open.
    IJ.error('No active image found. Please open/select an image and rerun.')
    println('FAIL: No active image.')
    return
}

// Define output folder and output file paths (hardcoded).
String outputDirPath = '/app/data/projects/coloc2_blue_red_whole_image/data'
String logOutPath = outputDirPath + '/coloc2_fixed_blue_red_log.txt'
String resultsOutPath = outputDirPath + '/coloc2_fixed_blue_red_results_table.csv'
new File(outputDirPath).mkdirs()

// Build a predictable title for the duplicate working image.
String originalTitle = original.getTitle()
String workingTitle = 'Coloc2_WorkingCopy_' + originalTitle

// Cleanup pre-existing temporary windows from prior runs (if any).
String[] existingTitles = WindowManager.getImageTitles()
for (String t : existingTitles) {
    if (t == null) continue
    if (t.equals(originalTitle)) continue
    if (t.startsWith('Coloc2_WorkingCopy_')) {
        ImagePlus tmp = WindowManager.getImage(t)
        if (tmp != null && tmp != original) {
            tmp.changes = false
            tmp.close()
        }
    }
}

// Duplicate the original image so processing never alters the source image.
ImagePlus working = original.duplicate()
working.setTitle(workingTitle)
working.show()

// Variables that will hold the selected RED and BLUE channel images.
ImagePlus redImp = null
ImagePlus blueImp = null
boolean splitDone = false

try {
    // This workflow requires RGB so channels can be split into red/green/blue.
    if (working.getType() == ImagePlus.COLOR_RGB) {
        // Split RGB into separate channel images.
        IJ.run(working, 'Split Channels', '')
        splitDone = true

        // Expected channel window titles created by "Split Channels".
        String expectedRed = workingTitle + ' (red)'
        String expectedBlue = workingTitle + ' (blue)'
        String[] titlesAfterSplit = WindowManager.getImageTitles()

        // Find those exact red/blue windows among currently open images.
        for (String t : titlesAfterSplit) {
            if (t == null) continue
            if (t.equals(expectedRed)) {
                redImp = WindowManager.getImage(t)
            } else if (t.equals(expectedBlue)) {
                blueImp = WindowManager.getImage(t)
            }
        }

        // If channels are missing, log details and stop.
        if (redImp == null || blueImp == null) {
            IJ.log('ERROR: Could not find expected split channels.')
            IJ.log('Expected RED title: ' + expectedRed)
            IJ.log('Expected BLUE title: ' + expectedBlue)
            IJ.log('Open image titles at failure:')
            for (String t : titlesAfterSplit) {
                IJ.log(' - ' + t)
            }
            println('FAIL: Missing red/blue split channels.')
            return
        }
    } else {
        // Stop if the active image is not RGB.
        IJ.error('Active image is not RGB. This script requires an RGB image.')
        println('FAIL: Non-RGB input image.')
        return
    }

    // Fixed Coloc 2 configuration (unchanged behavior):
    // - channel_1 = RED
    // - channel_2 = BLUE
    // - threshold = Costes
    // - iterations = 50
    // - psf_width = 3.0
    String args = [
        'channel_1=[' + redImp.getTitle() + ']',
        'channel_2=[' + blueImp.getTitle() + ']',
        'threshold_regression=Costes',
        'display_images=false',
        'display_results=true',
        'statistic_1=true',
        'statistic_2=true',
        'statistic_3=true',
        'number_of_iterations=50',
        'psf_width=3.0'
    ].join(' ')

    // Run Coloc 2 using the fixed arguments above.
    IJ.run('Coloc 2', args)

    // Try to capture text output from the log panel first.
    String logText = ''
    try {
        TextPanel logPanel = IJ.getTextPanel()
        if (logPanel != null) {
            String panelText = logPanel.getText()
            if (panelText != null) logText = panelText
        }
    } catch (Exception ignored) {
        // Fallback to IJ.getLog() if direct panel access fails.
    }

    // Secondary fallback for collecting log content.
    if (logText == null || logText.length() == 0) {
        String rawLog = IJ.getLog()
        if (rawLog != null) logText = rawLog
    }

    // Save collected log text to a fixed txt path.
    if (logText == null) logText = ''
    IJ.saveString(logText, logOutPath)

    // Save Results table if available and non-empty.
    ResultsTable rt = ResultsTable.getResultsTable()
    if (rt != null && rt.size() > 0) {
        rt.save(resultsOutPath)
    }

    // Final success message with output location.
    println('SUCCESS: Coloc2 run completed. Log saved to: ' + logOutPath)
} catch (Exception e) {
    // Catch-all error handling to keep failure clear in Console/Log.
    IJ.log('ERROR during Coloc2 run: ' + e.toString())
    e.printStackTrace()
    println('FAIL: Exception during Coloc2 run: ' + e.getMessage())
} finally {
    // Always cleanup temporary working/split windows; keep original open.
    String[] endTitles = WindowManager.getImageTitles()
    for (String t : endTitles) {
        if (t == null) continue
        if (t.equals(originalTitle)) continue
        if (t.startsWith('Coloc2_WorkingCopy_')) {
            ImagePlus tmp = WindowManager.getImage(t)
            if (tmp != null && tmp != original) {
                tmp.changes = false
                tmp.close()
            }
        }
    }
}
