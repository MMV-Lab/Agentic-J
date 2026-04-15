// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ File (label = "Input TIFF", value = "/data/example_1.tif") inputFile
#@ File (label = "Output HDF5", value = "/data/ilastik_validation/example_1.h5") outputFile
#@ String (label = "Dataset name", value = "/data") datasetName
#@ Integer (label = "Compression level", value = 0) compressionLevel
#@ org.scijava.command.CommandService command
#@ io.scif.services.DatasetIOService datasetIOService

import ij.IJ
import org.ilastik.ilastik4ij.io.ExportCommand
import org.ilastik.ilastik4ij.io.ListDatasetsCommand

/*
 * ilastik — Export a Fiji image to ilastik-compatible HDF5
 *
 * PURPOSE:
 *   1. Open a TIFF image as a Dataset
 *   2. Export it to HDF5 with the ilastik plugin
 *   3. List the datasets stored in the new HDF5 file
 *
 * REQUIRED INPUTS:
 *   inputFile        - source image to export
 *   outputFile       - destination HDF5 file
 *   datasetName      - dataset path inside the HDF5 file
 *   compressionLevel - gzip compression level from 0 to 9
 *
 * IMPORTANT:
 *   - Adjust the default file paths for your own input and output files.
 *   - Choose a new output path instead of overwriting an existing file.
 *   - This workflow does not run an ilastik prediction.
 */

if (inputFile == null || !inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + inputFile)
}
if (outputFile == null) {
    throw new IllegalArgumentException("Output HDF5 file must be provided")
}
if (!outputFile.name.endsWith(".h5")) {
    throw new IllegalArgumentException(
        "Output file must end with .h5: " + outputFile.absolutePath)
}
if (datasetName.trim().isEmpty()) {
    throw new IllegalArgumentException("datasetName must not be empty")
}
if (compressionLevel < 0 || compressionLevel > 9) {
    throw new IllegalArgumentException(
        "compressionLevel must be between 0 and 9: " + compressionLevel)
}
outputFile.parentFile?.mkdirs()
if (outputFile.exists()) {
    throw new IllegalArgumentException(
        "Output file already exists: " + outputFile.absolutePath)
}

IJ.log("ilastik HDF5 export")
IJ.log("Input: " + inputFile.absolutePath)
IJ.log("Output: " + outputFile.absolutePath)

def dataset = datasetIOService.open(inputFile.absolutePath)

command.run(ExportCommand, true,
    "input", dataset,
    "exportPath", outputFile,
    "datasetName", datasetName,
    "compressionLevel", compressionLevel
).get()

def listModule = command.run(ListDatasetsCommand, true,
    "file", outputFile
).get()
def table = listModule.getOutput("datasets")

IJ.log("Exported HDF5: " + outputFile.absolutePath)
IJ.log("Datasets: " + table)
