// These #@ lines inject Fiji script parameters and must stay at the top.
#@ File (label = "Input 3D TIFF", value = "/data/your_3d_stack.tif") inputFile
#@ Float (label = "Seeds threshold", value = 15.0, min = 0.0) seedsThreshold
#@ Float (label = "Constant local threshold", value = 65.0, min = 0.0) constantLocalThreshold
#@ Float (label = "Diff local threshold", value = 0.0, min = 0.0) diffLocalThreshold
#@ Float (label = "Local mean radius 0", value = 2.0, min = 0.0) meanRadius0
#@ Float (label = "Local mean radius 1", value = 4.0, min = 0.0) meanRadius1
#@ Float (label = "Local mean radius 2", value = 6.0, min = 0.0) meanRadius2
#@ Float (label = "Local mean weight", value = 0.5, min = 0.0) localMeanWeight
#@ Integer (label = "Gaussian fit max radius", value = 10, min = 1) gaussFitMaxRadius
#@ Float (label = "Gaussian fit sigma percent", value = 1.0, min = 0.0) gaussFitSigmaPercent
#@ String (label = "Local threshold method", choices = {"Constant", "Diff", "Local Mean", "Gaussian fit"}, value = "Constant") localThresholdMethod
#@ String (label = "Spot segmenter", choices = {"Classical", "Maximum", "Block"}, value = "Classical") spotSegmenterMethod
#@ Boolean (label = "Use watershed split", value = true) useWatershedSplit
#@ Integer (label = "Minimum volume", value = 1, min = 0) volumeMin
#@ Integer (label = "Maximum volume", value = 1000000, min = 1) volumeMax
#@ Integer (label = "Automatic seed radius", value = 2, min = 0) automaticSeedRadius
#@ Integer (label = "CPU threads", value = 1, min = 1) cpuThreads
#@ Boolean (label = "Use 32-bit labels", value = false) use32BitLabels
#@ File (label = "Automatic seed TIFF", style = "save", value = "/data/3d_imagej_suite_output/spot_seeds.tif") seedOutputFile
#@ File (label = "Spot label TIFF", style = "save", value = "/data/3d_imagej_suite_output/spot_labels.tif") labelOutputFile

import ij.IJ
import ij.ImagePlus
import ij.ImageStack
import mcib3d.image3d.ImageHandler
import mcib3d.image3d.processing.FastFilters3D
import mcib3d.image3d.segment.LocalThresholder
import mcib3d.image3d.segment.LocalThresholderConstant
import mcib3d.image3d.segment.LocalThresholderDiff
import mcib3d.image3d.segment.LocalThresholderGaussFit
import mcib3d.image3d.segment.LocalThresholderMean
import mcib3d.image3d.segment.Segment3DSpots
import mcib3d.image3d.segment.SpotSegmenter
import mcib3d.image3d.segment.SpotSegmenterBlock
import mcib3d.image3d.segment.SpotSegmenterClassical
import mcib3d.image3d.segment.SpotSegmenterMax
import mcib_plugins.analysis.SimpleMeasure

/*
 * 3D ImageJ Suite — automatic-seed spot segmentation
 *
 * PURPOSE:
 *   1. Open a 3D TIFF stack from disk
 *   2. Compute a seed image with the suite's MaximumLocal filter
 *   3. Segment spot-like objects with Segment3DSpots
 *   4. Save the seed response stack and the labelled spot stack
 *
 * This workflow mirrors the suite's `3D Spot Segmentation` plugin while
 * keeping the local thresholder and spot segmenter choices explicit.
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

LocalThresholder buildLocalThresholder(
    String methodName,
    float constantLocalThreshold,
    float diffLocalThreshold,
    float meanRadius0,
    float meanRadius1,
    float meanRadius2,
    float localMeanWeight,
    int gaussFitMaxRadius,
    float gaussFitSigmaPercent
) {
    switch (methodName) {
        case "Constant":
            return new LocalThresholderConstant(constantLocalThreshold)
        case "Diff":
            return new LocalThresholderDiff(diffLocalThreshold)
        case "Local Mean":
            return new LocalThresholderMean(meanRadius0, meanRadius1, meanRadius2, (double) localMeanWeight)
        case "Gaussian fit":
            return new LocalThresholderGaussFit(gaussFitMaxRadius, (double) gaussFitSigmaPercent)
        default:
            throw new IllegalArgumentException(
                "Unsupported localThresholdMethod: " + methodName +
                ". Accepted: Constant, Diff, Local Mean, Gaussian fit"
            )
    }
}

SpotSegmenter buildSpotSegmenter(String methodName) {
    switch (methodName) {
        case "Classical":
            return new SpotSegmenterClassical()
        case "Maximum":
            return new SpotSegmenterMax()
        case "Block":
            return new SpotSegmenterBlock()
        default:
            throw new IllegalArgumentException(
                "Unsupported spotSegmenterMethod: " + methodName +
                ". Accepted: Classical, Maximum, Block"
            )
    }
}

requireReadable(inputFile, "Input 3D TIFF")
requireFreshWritable(seedOutputFile, "Automatic seed TIFF")
requireFreshWritable(labelOutputFile, "Spot label TIFF")

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
        throw new IllegalArgumentException("Unsupported bit depth for automatic spot seeds: " + bitDepth)
    }

    if (seedStack == null) {
        throw new IllegalStateException("Automatic seed generation returned no stack")
    }

    seedImp = new ImagePlus(baseTitle + "-spot-seeds", seedStack)
    seedImp.setCalibration(analysisImp.getCalibration())

    ImageHandler rawHandler = ImageHandler.wrap(analysisImp)
    ImageHandler seedHandler = ImageHandler.wrap(seedImp)

    Segment3DSpots segmenter = new Segment3DSpots(rawHandler, seedHandler)
    segmenter.setSeedsThreshold(seedsThreshold)
    segmenter.setBigLabel(use32BitLabels)
    segmenter.setUseWatershed(useWatershedSplit)
    segmenter.setVolumeMin(volumeMin)
    segmenter.setVolumeMax(volumeMax)
    segmenter.setLocalThresholder(buildLocalThresholder(
        localThresholdMethod,
        constantLocalThreshold,
        diffLocalThreshold,
        meanRadius0,
        meanRadius1,
        meanRadius2,
        localMeanWeight,
        gaussFitMaxRadius,
        gaussFitSigmaPercent
    ))
    segmenter.setSpotSegmenter(buildSpotSegmenter(spotSegmenterMethod))
    segmenter.segmentAll()

    int objectCount = segmenter.getNbObjects()
    if (objectCount <= 0) {
        throw new IllegalStateException("3D Spot Segmentation found no objects. Check the thresholds and seed radius.")
    }

    def labelHandler = segmenter.getLabeledImage()
    if (labelHandler == null) {
        throw new IllegalStateException("3D Spot Segmentation returned no label image")
    }

    labelImp = labelHandler.getImagePlus()
    if (labelImp == null) {
        throw new IllegalStateException("3D Spot Segmentation returned no ImagePlus")
    }
    labelImp.setCalibration(analysisImp.getCalibration())
    labelImp.setTitle(baseTitle + "-spots")

    IJ.saveAs(seedImp, "Tiff", seedOutputFile.absolutePath)
    IJ.saveAs(labelImp, "Tiff", labelOutputFile.absolutePath)
    if (!seedOutputFile.exists() || seedOutputFile.length() == 0) {
        throw new IllegalStateException("Could not save seed TIFF: " + seedOutputFile.absolutePath)
    }
    if (!labelOutputFile.exists() || labelOutputFile.length() == 0) {
        throw new IllegalStateException("Could not save spot label TIFF: " + labelOutputFile.absolutePath)
    }

    IJ.log("3D spot segmentation workflow complete")
    IJ.log("Input         : " + inputFile.absolutePath)
    IJ.log("Seed TIFF     : " + seedOutputFile.absolutePath)
    IJ.log("Label TIFF    : " + labelOutputFile.absolutePath)
    IJ.log("Objects       : " + objectCount)
    IJ.log("Local method  : " + localThresholdMethod)
    IJ.log("Spot method   : " + spotSegmenterMethod)
}
finally {
    closeImage(labelImp)
    closeImage(seedImp)
    if (analysisImp != null && analysisImp != sourceImp) {
        closeImage(analysisImp)
    }
    closeImage(sourceImp)
}
