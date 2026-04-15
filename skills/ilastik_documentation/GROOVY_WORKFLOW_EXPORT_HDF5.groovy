// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ CommandService command
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
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
 *   INPUT_TIFF        - absolute path to the source image
 *   OUTPUT_H5         - absolute path to the HDF5 file to write
 *   DATASET_NAME      - dataset path inside the HDF5 file
 *   COMPRESSION_LEVEL - gzip compression level from 0 to 9
 *
 * IMPORTANT:
 *   - OUTPUT_H5 must end with .h5
 *   - This workflow exports data for ilastik and then inspects the written file
 *   - This workflow does not run an ilastik prediction
 */

String INPUT_TIFF = "/data/example_1.tif"
String OUTPUT_H5 = "/data/ilastik_validation/example_1.h5"
String DATASET_NAME = "/data"
int COMPRESSION_LEVEL = 0

def inputFile = new File(INPUT_TIFF)
if (!inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + INPUT_TIFF)
}

def outputFile = new File(OUTPUT_H5)
if (!OUTPUT_H5.endsWith(".h5")) {
    throw new IllegalArgumentException("Output file must end with .h5: " + OUTPUT_H5)
}
outputFile.getParentFile()?.mkdirs()
if (outputFile.exists()) {
    outputFile.delete()
}

def dataset = datasetIOService.open(INPUT_TIFF)
println("opened=" + dataset)

def exportModule = command.run(ExportCommand, true,
    "input", dataset,
    "exportPath", outputFile,
    "datasetName", DATASET_NAME,
    "compressionLevel", COMPRESSION_LEVEL
).get()
println("exportModule=" + exportModule)
println("exportExists=" + outputFile.exists())

def listModule = command.run(ListDatasetsCommand, true,
    "file", outputFile
).get()
def table = listModule.getOutput("datasets")
println("datasets=" + table)
