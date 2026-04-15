// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ File (label = "Input image", value = "/data/example_1.tif") inputFile
#@ File (label = "Labkit classifier", value = "/data/labkit_validation/example_1.classifier") classifierFile
#@ File (label = "Output TIFF", style = "save", value = "/data/labkit_validation/example_1-segmentation.tif") outputFile
#@ CommandService command

import ij.IJ
import ij.ImagePlus
import sc.fiji.labkit.ui.plugin.SegmentImageWithLabkitIJ1Plugin

/*
 * Labkit — Batch segmentation with a saved classifier
 *
 * PURPOSE:
 *   1. Open an image from disk
 *   2. Apply a previously saved Labkit classifier
 *   3. Save the segmentation result as TIFF
 *   4. Close the image windows created by the workflow
 *
 * REQUIRED INPUTS:
 *   inputFile      - image to segment
 *   classifierFile - Labkit .classifier file created in the GUI
 *   outputFile     - TIFF path that will be written
 *
 * GROOVY CALL USED IN THIS SCRIPT:
 *   command.run(SegmentImageWithLabkitIJ1Plugin, true,
 *       "input",          imp,
 *       "segmenter_file", classifierFile,
 *       "use_gpu",        false
 *   ).get()
 *
 * IMPORTANT:
 *   - Adjust the default file paths for your own image, classifier, and output files.
 *   - The classifier must already exist. This script does not train one.
 *   - Choose a new output path instead of overwriting an existing file.
 */

void closeImageIfOpen(ImagePlus imp) {
    if (imp != null) {
        imp.changes = false
        imp.close()
    }
}

if (!inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + inputFile.absolutePath)
}
if (!classifierFile.exists()) {
    throw new IllegalArgumentException("Classifier file not found: " + classifierFile.absolutePath)
}
if (outputFile == null) {
    throw new IllegalArgumentException("Output TIFF file must be provided")
}
outputFile.getParentFile()?.mkdirs()
if (outputFile.exists()) {
    throw new IllegalArgumentException("Output file already exists: " + outputFile.absolutePath)
}

IJ.log("Labkit batch segmentation")
IJ.log("Input      : " + inputFile.absolutePath)
IJ.log("Classifier : " + classifierFile.absolutePath)
IJ.log("Output     : " + outputFile.absolutePath)

ImagePlus sourceImp = null
ImagePlus resultImp = null

try {
    sourceImp = IJ.openImage(inputFile.absolutePath)
    if (sourceImp == null) {
        throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
    }

    def module = command.run(SegmentImageWithLabkitIJ1Plugin, true,
        "input",          sourceImp,
        "segmenter_file", classifierFile,
        "use_gpu",        false
    ).get()

    resultImp = module.getOutput("output")
    if (resultImp == null) {
        throw new IllegalStateException("Labkit returned no output image.")
    }

    IJ.saveAs(resultImp, "Tiff", outputFile.absolutePath)
    if (!outputFile.exists() || outputFile.length() == 0) {
        throw new IllegalStateException("Labkit did not write a TIFF: " + outputFile.absolutePath)
    }

    IJ.log("Saved segmentation: " + outputFile.absolutePath)
}
finally {
    closeImageIfOpen(resultImp)
    closeImageIfOpen(sourceImp)
}

IJ.log("Labkit workflow complete")
