// These #@ lines inject Fiji script parameters and must stay at the top.
#@ File (label = "Input 3D TIFF", value = "/data/your_3d_stack.tif") inputFile
#@ Float (label = "Mean filter radius X", value = 1.0, min = 0.0) radiusX
#@ Float (label = "Mean filter radius Y", value = 1.0, min = 0.0) radiusY
#@ Float (label = "Mean filter radius Z", value = 1.0, min = 0.0) radiusZ
#@ Integer (label = "Threshold", value = 80, min = 0) threshold
#@ Integer (label = "Minimum object size", value = 20, min = 0) minSize
#@ Integer (label = "Maximum object size (-1 disables)", value = -1) maxSize
#@ Integer (label = "CPU threads", value = 1, min = 1) cpuThreads
#@ Boolean (label = "Use 32-bit labels", value = false) use32BitLabels
#@ File (label = "Filtered TIFF", style = "save", value = "/data/3d_imagej_suite_output/filtered.tif") filteredOutputFile
#@ File (label = "Label TIFF", style = "save", value = "/data/3d_imagej_suite_output/labels.tif") labelOutputFile
#@ File (label = "Volume CSV", style = "save", value = "/data/3d_imagej_suite_output/volumes.csv") volumeCsvFile
#@ File (label = "Intensity CSV", style = "save", value = "/data/3d_imagej_suite_output/intensity.csv") intensityCsvFile

import ij.IJ
import ij.ImagePlus
import ij.ImageStack
import ij.measure.ResultsTable
import mcib3d.geom2.measurements.MeasureIntensity
import mcib3d.image3d.ImageHandler
import mcib3d.image3d.ImageLabeller
import mcib3d.image3d.processing.FastFilters3D
import mcib_plugins.analysis.SimpleMeasure

/*
 * 3D ImageJ Suite — batch smoothing, 3D labeling, and measurements
 *
 * PURPOSE:
 *   1. Open a 3D TIFF stack from disk
 *   2. Apply a 3D mean filter with the suite's filtering API
 *   3. Threshold bright objects over a dark background
 *   4. Label 3D connected components
 *   5. Save the filtered stack, the label stack, and per-object CSV tables
 *
 * REQUIRED INPUT:
 *   inputFile - 3D TIFF stack with bright objects over a dark background
 *
 * OUTPUTS:
 *   filteredOutputFile - filtered 3D TIFF
 *   labelOutputFile    - labelled 3D TIFF
 *   volumeCsvFile      - per-object volume table
 *   intensityCsvFile   - per-object intensity table
 *
 * EQUIVALENT FILTER COMMAND:
 *   IJ.run(imp, "3D Fast Filters",
 *       "filter=Mean radius_x_pix=<RX> radius_y_pix=<RY> radius_z_pix=<RZ> Nb_cpus=<N>")
 *
 * This workflow uses the underlying FastFilters3D API directly because it is
 * more predictable for batch execution and returns the filtered stack object.
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

ResultsTable buildIntensityTable(List<Double[]> rows, String[] headers) {
    ResultsTable table = new ResultsTable()
    rows.each { row ->
        table.incrementCounter()
        int rowIndex = table.getCounter() - 1
        headers.eachWithIndex { String name, int i ->
            Double value = row[i]
            table.setValue(name, rowIndex, value == null ? Double.NaN : value.doubleValue())
        }
    }
    return table
}

requireReadable(inputFile, "Input 3D TIFF")
requireFreshWritable(filteredOutputFile, "Filtered TIFF")
requireFreshWritable(labelOutputFile, "Label TIFF")
requireFreshWritable(volumeCsvFile, "Volume CSV")
requireFreshWritable(intensityCsvFile, "Intensity CSV")

ImagePlus sourceImp = null
ImagePlus analysisImp = null
ImagePlus filteredImp = null
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
    ImageStack filteredStack

    if (bitDepth == 8 || bitDepth == 16) {
        filteredStack = FastFilters3D.filterIntImageStack(
            analysisImp.getStack(),
            0,
            radiusX,
            radiusY,
            radiusZ,
            cpuThreads,
            true
        )
    }
    else if (bitDepth == 32) {
        filteredStack = FastFilters3D.filterFloatImageStack(
            analysisImp.getStack(),
            0,
            radiusX,
            radiusY,
            radiusZ,
            cpuThreads,
            true
        )
    }
    else {
        throw new IllegalArgumentException("Unsupported bit depth for 3D Fast Filters: " + bitDepth)
    }

    if (filteredStack == null) {
        throw new IllegalStateException("3D Fast Filters returned no stack")
    }

    filteredImp = new ImagePlus(baseTitle + "-mean3d", filteredStack)
    filteredImp.setCalibration(analysisImp.getCalibration())

    ImageHandler filteredHandler = ImageHandler.wrap(filteredImp)
    def binary = filteredHandler.thresholdAboveInclusive((float) threshold)
    binary.setVoxelSize(filteredHandler)

    ImageLabeller labeller = new ImageLabeller()
    if (minSize > 0) {
        labeller.setMinSize(minSize)
    }
    if (maxSize > 0) {
        labeller.setMaxsize(maxSize)
    }

    def labels = use32BitLabels ? labeller.getLabelsFloat(binary) : labeller.getLabels(binary)
    labels.setVoxelSize(filteredHandler)
    labelImp = labels.getImagePlus()
    labelImp.setCalibration(filteredImp.getCalibration())
    labelImp.setTitle(baseTitle + "-labels")

    SimpleMeasure measure = new SimpleMeasure(labelImp)
    ResultsTable volumeTable = measure.getResultsTable("Volume")
    if (volumeTable == null || volumeTable.getCounter() == 0) {
        throw new IllegalStateException("3D Volume returned no objects. Check the threshold and size limits.")
    }

    List<Double[]> intensityRows = measure.getMeasuresStats(analysisImp)
    String[] intensityHeaders = new MeasureIntensity().getNamesMeasurement()
    ResultsTable intensityTable = buildIntensityTable(intensityRows, intensityHeaders)
    if (intensityTable.getCounter() == 0) {
        throw new IllegalStateException("3D intensity measurements returned no objects.")
    }

    IJ.saveAs(filteredImp, "Tiff", filteredOutputFile.absolutePath)
    IJ.saveAs(labelImp, "Tiff", labelOutputFile.absolutePath)
    volumeTable.save(volumeCsvFile.absolutePath)
    intensityTable.save(intensityCsvFile.absolutePath)

    double maxLabel = labelImp.getStatistics().max
    IJ.log("3D ImageJ Suite workflow complete")
    IJ.log("Input          : " + inputFile.absolutePath)
    IJ.log("Filtered TIFF  : " + filteredOutputFile.absolutePath)
    IJ.log("Label TIFF     : " + labelOutputFile.absolutePath)
    IJ.log("Volume CSV     : " + volumeCsvFile.absolutePath)
    IJ.log("Intensity CSV  : " + intensityCsvFile.absolutePath)
    IJ.log("Detected labels: " + Math.round(maxLabel))
}
finally {
    closeImage(labelImp)
    closeImage(filteredImp)
    if (analysisImp != null && analysisImp != sourceImp) {
        closeImage(analysisImp)
    }
    closeImage(sourceImp)
}
