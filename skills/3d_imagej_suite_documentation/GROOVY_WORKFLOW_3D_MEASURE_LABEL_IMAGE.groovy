// These #@ lines inject Fiji script parameters and must stay at the top.
#@ File (label = "Label TIFF", value = "/data/your_labels.tif") labelFile
#@ File (label = "Signal TIFF", value = "/data/your_signal.tif") signalFile
#@ File (label = "Volume CSV", style = "save", value = "/data/3d_imagej_suite_output/label_volumes.csv") volumeCsvFile
#@ File (label = "Intensity CSV", style = "save", value = "/data/3d_imagej_suite_output/label_intensity.csv") intensityCsvFile

import ij.IJ
import ij.ImagePlus
import ij.measure.ResultsTable
import mcib3d.geom2.measurements.MeasureIntensity
import mcib_plugins.analysis.SimpleMeasure

/*
 * 3D ImageJ Suite — measure an existing label image
 *
 * PURPOSE:
 *   1. Open a 3D labelled object image
 *   2. Measure object volume
 *   3. Measure signal intensity from a matching grayscale stack
 *   4. Save both tables as CSV
 *
 * Use this workflow when segmentation already exists and only measurements are needed.
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

requireReadable(labelFile, "Label TIFF")
requireReadable(signalFile, "Signal TIFF")
requireFreshWritable(volumeCsvFile, "Volume CSV")
requireFreshWritable(intensityCsvFile, "Intensity CSV")

ImagePlus labelSource = null
ImagePlus signalSource = null
ImagePlus labelImp = null
ImagePlus signalImp = null

try {
    labelSource = IJ.openImage(labelFile.absolutePath)
    signalSource = IJ.openImage(signalFile.absolutePath)
    if (labelSource == null) {
        throw new IllegalStateException("Could not open label image: " + labelFile.absolutePath)
    }
    if (signalSource == null) {
        throw new IllegalStateException("Could not open signal image: " + signalFile.absolutePath)
    }

    labelImp = SimpleMeasure.extractCurrentStack(labelSource)
    signalImp = SimpleMeasure.extractCurrentStack(signalSource)
    if (labelImp == null || signalImp == null) {
        throw new IllegalStateException("Could not extract stacks from the provided inputs.")
    }

    if (labelImp.getNSlices() != signalImp.getNSlices()
        || labelImp.getWidth() != signalImp.getWidth()
        || labelImp.getHeight() != signalImp.getHeight()) {
        throw new IllegalArgumentException("Label and signal images must have matching stack dimensions.")
    }

    SimpleMeasure measure = new SimpleMeasure(labelImp)
    ResultsTable volumeTable = measure.getResultsTable("Volume")
    if (volumeTable == null || volumeTable.getCounter() == 0) {
        throw new IllegalStateException("No objects were found in the label image.")
    }

    List<Double[]> intensityRows = measure.getMeasuresStats(signalImp)
    String[] intensityHeaders = new MeasureIntensity().getNamesMeasurement()
    ResultsTable intensityTable = buildIntensityTable(intensityRows, intensityHeaders)
    if (intensityTable.getCounter() == 0) {
        throw new IllegalStateException("No intensity measurements were produced.")
    }

    volumeTable.save(volumeCsvFile.absolutePath)
    intensityTable.save(intensityCsvFile.absolutePath)

    IJ.log("3D label measurement workflow complete")
    IJ.log("Labels       : " + labelFile.absolutePath)
    IJ.log("Signal       : " + signalFile.absolutePath)
    IJ.log("Volume CSV   : " + volumeCsvFile.absolutePath)
    IJ.log("Intensity CSV: " + intensityCsvFile.absolutePath)
    IJ.log("Objects      : " + volumeTable.getCounter())
}
finally {
    if (labelImp != null && labelImp != labelSource) {
        closeImage(labelImp)
    }
    if (signalImp != null && signalImp != signalSource) {
        closeImage(signalImp)
    }
    closeImage(labelSource)
    closeImage(signalSource)
}
