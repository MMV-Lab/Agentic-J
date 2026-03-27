import loci.plugins.BF
import loci.plugins.in.ImporterOptions
import ij.IJ
import ij.ImagePlus
import java.io.File
import java.io.FileWriter
import java.io.PrintWriter
import java.io.StringWriter

/*
 * =================================================================================================
 * Bio-Formats Batch Convert (Test Harness)
 * =================================================================================================
 * PURPOSE
 *   Batch-convert microscopy files from a raw input directory into OME-TIFF outputs using
 *   Bio-Formats import + export in a fully non-interactive, GUI-compatible Fiji/ImageJ script.
 *
 * INPUTS
 *   - INPUT_DIR: directory containing source microscopy/image files.
 *   - INPUT_EXTENSIONS: filename extensions allowed for import filtering.
 *
 * OUTPUTS
 *   - OUTPUT_DIR: generated .ome.tif files (one per source series; series suffix when needed).
 *   - LOG_PATH: persistent run log with all status/error lines and stack traces.
 *
 * WHY USE BIO-FORMATS EXPORTER HERE
 *   - The test harness targets broad microscopy format interoperability.
 *   - Bio-Formats importer handles vendor formats consistently via ImporterOptions.
 *   - Bio-Formats exporter is attempted through multiple option-key variants to tolerate
 *     plugin/version differences in accepted argument names.
 *
 * WHY MIRROR IJ.LOG TO STDOUT + FILE
 *   - IJ.log alone can be hard to capture in headless/remote orchestration.
 *   - stdout makes logs visible to external runners/CI wrappers.
 *   - file logging preserves full diagnostics and stack traces for post-mortem analysis.
 *
 * KNOWN PITFALLS / MAINTENANCE NOTES
 *   - BF.openImagePlus(...) returns ImagePlus[] (array), not a single ImagePlus.
 *   - Different Bio-Formats Exporter variants may require different option keys:
 *       'save=[...]' vs 'export=[...]' vs 'outfile=[...]'.
 *   - Some exporter calls may return without exception yet still not write output; therefore
 *     this script validates both file existence and non-zero length.
 *   - Existing outputs are deleted before export attempts to avoid false positives from stale files.
 *   - Script intentionally avoids dialogs and ARGS; all parameters are hardcoded.
 * =================================================================================================
 */

// ============================================================
// PARAMETERS (hardcoded for this project)
// ============================================================

def INPUT_DIR  = "/app/data/projects/bioformats_workflow_batch_convert_test/raw_images"
def OUTPUT_DIR = "/app/data/projects/bioformats_workflow_batch_convert_test/processed_images"
def LOG_PATH   = "/app/data/projects/bioformats_workflow_batch_convert_test/logs/batch_convert_log.txt"

def INPUT_EXTENSIONS = [".czi", ".nd2", ".lif", ".oif", ".lsm", ".tif", ".tiff"] as Set

def COLOR_MODE = ImporterOptions.COLOR_MODE_COMPOSITE

// ============================================================
// SETUP
// ============================================================

def inputDir = new File(INPUT_DIR)
def outputDir = new File(OUTPUT_DIR)
def logFile = new File(LOG_PATH)
def logDir = logFile.parentFile

if (logDir != null && !logDir.exists()) {
    logDir.mkdirs()
}

PrintWriter logWriter = new PrintWriter(new FileWriter(logFile, false))

// ============================================================
// LOGGING UTILITIES
// ============================================================

def logLine = { String msg ->
    IJ.log(msg)      // Fiji log window (interactive visibility)
    println(msg)     // stdout (external runner/CI visibility)
    logWriter.println(msg) // persistent file log
    logWriter.flush()
}

def logException = { String context, Exception ex ->
    logLine(context)
    logLine("  Exception class: " + ex.getClass().getName())
    logLine("  Exception message: " + String.valueOf(ex.getMessage()))
    StringWriter sw = new StringWriter()
    PrintWriter pw = new PrintWriter(sw)
    ex.printStackTrace(pw)
    pw.flush()
    logLine("  Stack trace:")
    sw.toString().split('\\r?\\n').each { line -> logLine("    " + line) }
}

try {
    // ============================================================
    // PRE-FLIGHT CHECKS
    // ============================================================
    if (!inputDir.exists() || !inputDir.isDirectory()) {
        logLine("FAILURE: Input directory missing: " + INPUT_DIR)
        return
    }

    if (!outputDir.exists()) {
        boolean made = outputDir.mkdirs()
        if (!made) {
            logLine("FAILURE: Could not create output directory: " + OUTPUT_DIR)
            return
        }
    }

    def beforeNames = outputDir.listFiles()?.findAll { f ->
        f.isFile() && (f.name.toLowerCase().endsWith('.ome.tif') || f.name.toLowerCase().endsWith('.ome.tiff'))
    }?.collect { it.name } as Set
    if (beforeNames == null) beforeNames = [] as Set

    // ============================================================
    // FILE ENUMERATION
    // ============================================================
    def inputFiles = inputDir.listFiles()?.findAll { f ->
        f.isFile() && INPUT_EXTENSIONS.any { ext -> f.name.toLowerCase().endsWith(ext) }
    }?.sort { it.name }

    if (inputFiles == null || inputFiles.isEmpty()) {
        logLine("No matching files found in: " + INPUT_DIR)
        logLine("Looking for extensions: " + INPUT_EXTENSIONS)
        logLine("FAILURE: No matching input files.")
        return
    }

    logLine("=" * 60)
    logLine("Bio-Formats Batch Conversion (TEST HARNESS)")
    logLine("Input dir  : " + INPUT_DIR)
    logLine("Output dir : " + OUTPUT_DIR)
    logLine("Log file   : " + LOG_PATH)
    logLine("Files found: " + inputFiles.size())
    logLine("=" * 60)

    // ============================================================
    // IMPORT OPTIONS + CONVERSION LOOP
    // ============================================================

    def succeeded = []
    def failed = []
    def failedSeries = []

    inputFiles.each { inputFile ->
        logLine("\nProcessing: " + inputFile.name)

        // ImporterOptions configured per file; open all series for explicit per-series export.
        def opts = new ImporterOptions()
        opts.setId(inputFile.absolutePath)
        opts.setWindowless(true)
        opts.setQuiet(true)
        opts.setColorMode(COLOR_MODE)
        opts.setAutoscale(true)
        opts.setVirtual(false)
        opts.setOpenAllSeries(true)

        ImagePlus[] imps = null

        try {
            imps = BF.openImagePlus(opts)
        } catch (Exception e) {
            logException("  ERROR opening file", e)
            failed << inputFile.name
            return
        }

        if (imps == null || imps.length == 0) {
            logLine("  WARNING: no images returned for " + inputFile.name)
            failed << inputFile.name
            return
        }

        logLine("  Opened " + imps.length + " image(s)")

        // Strip only final extension (regex), preserving earlier dots in the stem if present.
        def baseName = inputFile.name.replaceAll(/\.[^.]+$/, "")
        boolean fileHadAnyExportFailure = false

        imps.eachWithIndex { imp, idx ->
            try {
                if (imp == null) {
                    logLine("  WARNING: null ImagePlus at series index " + idx)
                    fileHadAnyExportFailure = true
                    failedSeries << (inputFile.name + " [series " + idx + ": null image]")
                    return
                }

                def suffix = (imps.length > 1) ? "_s${idx}" : ""
                def outName = baseName + suffix + ".ome.tif"
                def outPath = new File(outputDir, outName).absolutePath
                def outFile = new File(outPath)

                // Delete pre-existing output so success checks cannot pass due to stale file from older runs.
                if (outFile.exists()) {
                    if (!outFile.delete()) {
                        logLine("  WARNING: could not delete existing output before export: " + outPath)
                    }
                }

                boolean exported = false
                Exception lastExportException = null

                // ============================================================
                // EXPORT ATTEMPTS (legacy command/plugin fallbacks preserved)
                // ============================================================
                def attempts = [
                    [type: "ijrun", cmd: "Bio-Formats Exporter", opts: "save=[" + outPath + "] windowless=true"],
                    [type: "ijrun", cmd: "Bio-Formats Exporter", opts: "save=[" + outPath + "]"],
                    [type: "ijrun", cmd: "Bio-Formats Exporter", opts: "export=[" + outPath + "] windowless=true"],
                    [type: "ijrun", cmd: "Bio-Formats Exporter", opts: "export=[" + outPath + "]"],
                    [type: "ijrun", cmd: "Bio-Formats Exporter", opts: "outfile=[" + outPath + "] windowless=true"],
                    [type: "ijrun", cmd: "Bio-Formats Exporter", opts: "outfile=[" + outPath + "]"],
                    [type: "plugin", className: "loci.plugins.LociExporter", opts: "save=[" + outPath + "] windowless=true"],
                    [type: "plugin", className: "loci.plugins.LociExporter", opts: "save=[" + outPath + "]"]
                ]

                attempts.eachWithIndex { a, ai ->
                    if (exported) return
                    try {
                        if (a.type == "ijrun") {
                            IJ.run(imp, a.cmd as String, a.opts as String)
                            logLine("  Export attempt " + (ai + 1) + " used IJ.run command='" + a.cmd + "' options='" + a.opts + "'")
                        } else {
                            IJ.runPlugIn(imp, a.className as String, a.opts as String)
                            logLine("  Export attempt " + (ai + 1) + " used IJ.runPlugIn class='" + a.className + "' options='" + a.opts + "'")
                        }

                        // Validate exporter success by existence + non-zero bytes; avoids false success on empty files.
                        if (outFile.exists() && outFile.length() > 0L) {
                            exported = true
                        }
                    } catch (Exception exAttempt) {
                        lastExportException = exAttempt
                        logException("  Export attempt " + (ai + 1) + " failed", exAttempt)
                    }
                }

                // ============================================================
                // VALIDATION
                // ============================================================
                if (exported) {
                    def sizeMB = outFile.length() / (1024.0 * 1024.0)
                    logLine(String.format("  Saved: %s  (%.1f MB)", outName, sizeMB))
                } else {
                    if (lastExportException != null) {
                        logException("  ERROR: exporter failed for " + outPath, lastExportException)
                    }
                    if (!outFile.exists()) {
                        logLine("  ERROR: output file not found after save: " + outPath)
                    } else {
                        logLine("  ERROR: output file is zero bytes after save: " + outPath)
                    }
                    fileHadAnyExportFailure = true
                    failedSeries << (inputFile.name + " [series " + idx + ": export failed]")
                }
            } catch (Exception eSeries) {
                logException("  ERROR exporting series " + idx, eSeries)
                fileHadAnyExportFailure = true
                failedSeries << (inputFile.name + " [series " + idx + ": " + String.valueOf(eSeries.getMessage()) + "]")
            } finally {
                // ============================================================
                // CLEANUP (per-series)
                // ============================================================
                try {
                    if (imp != null) imp.close()
                } catch (Exception closeEx) {
                    logException("  WARNING: could not close image for series " + idx, closeEx)
                }
            }
        }

        if (fileHadAnyExportFailure) {
            failed << inputFile.name
        } else {
            succeeded << inputFile.name
        }
    }

    // ============================================================
    // SUMMARY
    // ============================================================

    def afterFiles = outputDir.listFiles()?.findAll { f ->
        f.isFile() && (f.name.toLowerCase().endsWith('.ome.tif') || f.name.toLowerCase().endsWith('.ome.tiff'))
    } ?: []
    def afterNames = afterFiles.collect { it.name } as Set
    def newNames = afterNames - beforeNames

    logLine("\n" + "=" * 60)
    logLine("Done. Succeeded: " + succeeded.size() + "  Failed: " + failed.size())
    if (!succeeded.isEmpty()) {
        logLine("Succeeded files:")
        succeeded.each { logLine("  ✓ " + it) }
    }
    if (!failed.isEmpty()) {
        logLine("Failed files:")
        failed.unique().each { logLine("  ✗ " + it) }
    }
    if (!failedSeries.isEmpty()) {
        logLine("Failed series details:")
        failedSeries.each { logLine("  - " + it) }
    }
    logLine("Output directory: " + OUTPUT_DIR)
    logLine("New .ome.tif/.ome.tiff files created this run: " + newNames.size())
    if (!newNames.isEmpty()) {
        newNames.sort().each { logLine("  + " + it) }
    }
    logLine("=" * 60)

    if (failed.isEmpty()) {
        logLine("SUCCESS: Bio-Formats batch conversion test completed. Converted files in: " + OUTPUT_DIR)
    } else {
        logLine("FAILURE: Bio-Formats batch conversion test completed with errors. See log file for details.")
    }
} catch (Exception topEx) {
    logException("FATAL: Unhandled exception in batch convert script", topEx)
    logLine("FAILURE: Script terminated due to unhandled exception.")
} finally {
    logWriter.flush()
    logWriter.close()
}
