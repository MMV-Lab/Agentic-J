// These #@ lines inject Fiji script parameters and must stay at the top.
#@ File (label = "Input 3D TIFF", value = "/data/your_3d_stack.tif") inputFile
#@ Integer (label = "Seeds threshold", value = 180, min = 0) seedsThreshold
#@ Integer (label = "Image threshold", value = 80, min = 0) imageThreshold
#@ Integer (label = "Automatic seed radius", value = 2, min = 0) automaticSeedRadius
#@ Integer (label = "CPU threads", value = 1, min = 1) cpuThreads
#@ File (label = "Automatic seed TIFF", style = "save", value = "/data/3d_imagej_suite_output/watershed_seeds.tif") seedOutputFile
#@ File (label = "Watershed label TIFF", style = "save", value = "/data/3d_imagej_suite_output/watershed_labels.tif") labelOutputFile

import ij.IJ
import ij.ImagePlus
import ij.ImageStack
import mcib3d.image3d.processing.FastFilters3D
import mcib3d.image3d.regionGrowing.Watershed3D
import mcib_plugins.analysis.SimpleMeasure

/*
 * 3D ImageJ Suite — watershed segmentation with automatic local-max seed image
 *
 * PURPOSE:
 *   1. Open a 3D TIFF stack from disk
 *   2. Compute an automatic seed image with the suite's MaximumLocal filter
 *   3. Run seeded 3D watershed using the raw image and seed image
 *   4. Save the seed response stack and the labelled watershed stack
 *
 * This follows the same automatic-seed path as the suite's `3D Watershed`
 * dialog, but keeps everything in a predictable batch script.
 */

void requireReadable(File file, String label) {
    if (file == null || !file.exists()) {
        throw new IllegalArgumentException(label + " not found: " + file)
    }
}

void requireFreshWritable(File file, String label) {
    if (file == null) {
        throw new IllegalArgumentException(label + " must be provided")
    }
    File parent = file.getParentFile()
    if (parent != null && !parent.exists()) {
        parent.mkdirs()
    }
    if (file.exists()) {
        throw new IllegalArgumentException(label + " already exists: " + file.absolutePath)
    }
}

void closeImage(ImagePlus imp) {
    if (imp != null) {
        imp.changes = false
        imp.close()
    }
}

String stripTiffExtension(String name) {
    return name
        .replaceAll(/(?i)\.ome\.tiff?$/, "")
        .replaceAll(/(?i)\.tiff?$/, "")
}

requireReadable(inputFile, "Input 3D TIFF")
requireFreshWritable(seedOutputFile, "Automatic seed TIFF")
requireFreshWritable(labelOutputFile, "Watershed label TIFF")

ImagePlus sourceImp = null
ImagePlus analysisImp = null
ImagePlus seedImp = null
ImagePlus labelImp = null

try {
    sourceImp = IJ.openImage(inputFile.absolutePath)
    if (sourceImp == null) {
        throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
    }

    analysisImp = SimpleMeasure.extractCurrentStack(sourceImp)
    if (analysisImp == null) {
        throw new IllegalStateException("Could not extract a 3D stack from: " + inputFile.absolutePath)
    }

    String baseTitle = stripTiffExtension(inputFile.getName())
    analysisImp.setTitle(baseTitle)

    int bitDepth = analysisImp.getBitDepth()
    ImageStack seedStack

    if (bitDepth == 8 || bitDepth == 16) {
        seedStack = FastFilters3D.filterIntImageStack(
            analysisImp.getStack(),
            4,
            (float) automaticSeedRadius,
            (float) automaticSeedRadius,
            (float) automaticSeedRadius,
            cpuThreads,
            true
        )
    }
    else if (bitDepth == 32) {
        seedStack = FastFilters3D.filterFloatImageStack(
            analysisImp.getStack(),
            4,
            (float) automaticSeedRadius,
            (float) automaticSeedRadius,
            (float) automaticSeedRadius,
            cpuThreads,
            true
        )
    }
    else {
        throw new IllegalArgumentException("Unsupported bit depth for automatic watershed seeds: " + bitDepth)
    }

    if (seedStack == null) {
        throw new IllegalStateException("Automatic seed generation returned no stack")
    }

    seedImp = new ImagePlus(baseTitle + "-watershed-seeds", seedStack)
    seedImp.setCalibration(analysisImp.getCalibration())

    Watershed3D watershed = new Watershed3D(
        analysisImp.getStack(),
        seedStack,
        (double) imageThreshold,
        seedsThreshold
    )
    watershed.setLabelSeeds(true)
    watershed.setAnim(false)

    def labelHandler = watershed.getWatershedImage3D()
    if (labelHandler == null) {
        throw new IllegalStateException("3D Watershed returned no label image")
    }

    labelImp = labelHandler.getImagePlus()
    if (labelImp == null) {
        throw new IllegalStateException("3D Watershed returned no ImagePlus")
    }
    labelImp.setCalibration(analysisImp.getCalibration())
    labelImp.setTitle(baseTitle + "-watershed")

    IJ.saveAs(seedImp, "Tiff", seedOutputFile.absolutePath)
    IJ.saveAs(labelImp, "Tiff", labelOutputFile.absolutePath)
    if (!seedOutputFile.exists() || seedOutputFile.length() == 0) {
        throw new IllegalStateException("Could not save seed TIFF: " + seedOutputFile.absolutePath)
    }
    if (!labelOutputFile.exists() || labelOutputFile.length() == 0) {
        throw new IllegalStateException("Could not save watershed label TIFF: " + labelOutputFile.absolutePath)
    }

    double maxLabel = labelImp.getStatistics().max
    IJ.log("3D watershed workflow complete")
    IJ.log("Input         : " + inputFile.absolutePath)
    IJ.log("Seed TIFF     : " + seedOutputFile.absolutePath)
    IJ.log("Label TIFF    : " + labelOutputFile.absolutePath)
    IJ.log("Seeds thr     : " + seedsThreshold)
    IJ.log("Image thr     : " + imageThreshold)
    IJ.log("Detected labels: " + Math.round(maxLabel))
}
finally {
    closeImage(labelImp)
    closeImage(seedImp)
    if (analysisImp != null && analysisImp != sourceImp) {
        closeImage(analysisImp)
    }
    closeImage(sourceImp)
}
