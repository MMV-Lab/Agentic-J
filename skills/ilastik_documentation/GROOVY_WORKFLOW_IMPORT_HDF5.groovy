// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ File (label = "Input HDF5", value = "/data/ilastik_validation/examples/mitocheck_2d+t/mitocheck_94570_2D+t_01-53.h5") inputFile
#@ String (label = "Dataset name", value = "/volume/data") datasetName
#@ String (label = "Axis order", value = "txyc") axisOrder
#@ File (label = "Output TIFF", value = "/data/ilastik_validation/mitocheck_raw_import.tif") outputFile
#@ org.scijava.Context context
#@ net.imagej.DatasetService datasetService
#@ io.scif.services.DatasetIOService datasetIOService

import ij.IJ
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
 *   inputFile   - source HDF5 file
 *   datasetName - dataset path inside the HDF5 file
 *   axisOrder   - row-major axis string for the selected dataset
 *   outputFile  - TIFF path to write
 *
 * IMPORTANT:
 *   - Use `List HDF5 Datasets` first if datasetName or axisOrder are unknown.
 *   - Adjust the default file paths for your own input and output files.
 *   - Choose a new output path instead of overwriting an existing file.
 */

if (inputFile == null || !inputFile.exists()) {
    throw new IllegalArgumentException("Input HDF5 file not found: " + inputFile)
}
if (datasetName.trim().isEmpty()) {
    throw new IllegalArgumentException("datasetName must not be empty")
}
if (axisOrder.trim().isEmpty()) {
    throw new IllegalArgumentException("axisOrder must not be empty")
}
if (outputFile == null) {
    throw new IllegalArgumentException("Output TIFF file must be provided")
}
outputFile.parentFile?.mkdirs()
if (outputFile.exists()) {
    throw new IllegalArgumentException(
        "Output file already exists: " + outputFile.absolutePath)
}

def importCommand = new ImportCommand()
importCommand.setContext(context)
importCommand.select = inputFile
importCommand.datasetName = datasetName
importCommand.axisOrder = axisOrder
importCommand.run()

def imported = importCommand.output
if (imported == null) {
    throw new IllegalStateException("ImportCommand returned null output")
}

def outputDataset = datasetService.create(imported)
datasetIOService.save(outputDataset, outputFile.absolutePath)
IJ.log("Imported HDF5 dataset to: " + outputFile.absolutePath)
