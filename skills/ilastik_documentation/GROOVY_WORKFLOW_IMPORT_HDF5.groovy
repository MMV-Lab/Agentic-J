// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.io.ImportCommand

/*
 * ilastik — Import one HDF5 dataset into Fiji
 *
 * PURPOSE:
 *   1. Select one dataset inside an HDF5 file
 *   2. Set the row-major axis order for that dataset
 *   3. Import the dataset into Fiji
 *   4. Save the imported image as TIFF
 *
 * REQUIRED INPUTS:
 *   INPUT_H5     - absolute path to the source HDF5 file
 *   DATASET_NAME - dataset path inside the HDF5 file
 *   AXIS_ORDER   - row-major axis string for the selected dataset
 *   OUTPUT_TIFF  - absolute path to the TIFF that will be written
 *
 * IMPORTANT:
 *   - Use List HDF5 Datasets first if DATASET_NAME or AXIS_ORDER are unknown
 *   - AXIS_ORDER must match the dataset dimensions reported by the plugin
 */

String INPUT_H5 = "/data/ilastik_validation/examples/mitocheck_2d+t/mitocheck_94570_2D+t_01-53.h5"
String DATASET_NAME = "/volume/data"
String AXIS_ORDER = "txyc"
String OUTPUT_TIFF = "/data/ilastik_validation/mitocheck_raw_import.tif"

def inputFile = new File(INPUT_H5)
def outputFile = new File(OUTPUT_TIFF)

if (!inputFile.exists()) {
    throw new IllegalArgumentException("Input HDF5 file not found: " + INPUT_H5)
}
if (DATASET_NAME.trim().isEmpty()) {
    throw new IllegalArgumentException("DATASET_NAME must not be empty")
}
if (AXIS_ORDER.trim().isEmpty()) {
    throw new IllegalArgumentException("AXIS_ORDER must not be empty")
}
outputFile.getParentFile()?.mkdirs()
if (outputFile.exists()) {
    outputFile.delete()
}

def importCommand = new ImportCommand()
importCommand.setContext(context)
importCommand.select = inputFile
importCommand.datasetName = DATASET_NAME
importCommand.axisOrder = AXIS_ORDER
importCommand.run()

def imported = importCommand.output
println("output=" + imported)
if (imported == null) {
    throw new IllegalStateException("ImportCommand returned null output")
}

def outputDataset = datasetService.create(imported)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
println("saved=" + outputFile.exists())
