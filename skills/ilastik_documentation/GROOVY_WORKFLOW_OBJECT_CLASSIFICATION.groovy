// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ CommandService command
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.ObjectClassificationCommand

/*
 * ilastik — Run a trained Object Classification project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Open one raw image and one probability image
 *   3. Apply a trained ilastik Object Classification project
 *   4. Save the returned object-classification result as TIFF
 *
 * REQUIRED INPUTS:
 *   EXECUTABLE        - absolute path to the ilastik executable
 *   PROJECT_FILE      - absolute path to a trained Object Classification .ilp file
 *   INPUT_TIFF        - absolute path to the raw image
 *   SECOND_INPUT_TIFF - absolute path to the probability image
 *   OUTPUT_TYPE       - Object Predictions, Object Probabilities, or Object Identities
 *   OUTPUT_TIFF       - absolute path to the TIFF that will be written
 *
 * IMPORTANT:
 *   - The .ilp project must be closed in ilastik before Fiji runs it
 *   - This workflow uses a probability image as the second input
 *   - The raw image and the second input must describe the same scene
 */

String EXECUTABLE = "/home/imagentj/ilastik-1.4.1.post1-Linux/run_ilastik.sh"
String PROJECT_FILE = "/data/ilastik_validation/obj_class_2d_cells_apoptotic.ilp"
String INPUT_TIFF = "/data/ilastik_validation/2d_cells_apoptotic.tif"
String SECOND_INPUT_TIFF = "/data/ilastik_validation/2d_cells_apoptotic_1channel-data_Probabilities.tif"
String OUTPUT_TYPE = "Object Predictions"
String OUTPUT_TIFF = "/data/ilastik_validation/object_predictions.tif"

def validOutputs = [
    "Object Predictions",
    "Object Probabilities",
    "Object Identities"
]
if (!(OUTPUT_TYPE in validOutputs)) {
    throw new IllegalArgumentException(
        "OUTPUT_TYPE must be one of " + validOutputs + ": " + OUTPUT_TYPE)
}

def executableFile = new File(EXECUTABLE)
def projectFile = new File(PROJECT_FILE)
def inputFile = new File(INPUT_TIFF)
def secondInputFile = new File(SECOND_INPUT_TIFF)
def outputFile = new File(OUTPUT_TIFF)

if (!executableFile.exists()) {
    throw new IllegalArgumentException("Executable not found: " + EXECUTABLE)
}
if (!projectFile.exists()) {
    throw new IllegalArgumentException("Project file not found: " + PROJECT_FILE)
}
if (!inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + INPUT_TIFF)
}
if (!secondInputFile.exists()) {
    throw new IllegalArgumentException("Second input image not found: " + SECOND_INPUT_TIFF)
}
outputFile.getParentFile()?.mkdirs()
if (outputFile.exists()) {
    outputFile.delete()
}

def options = optionsService.getOptions(IlastikOptions)
options.executableFile = executableFile
options.numThreads = -1
options.maxRamMb = 4096
options.save()

def rawDataset = datasetIOService.open(INPUT_TIFF)
def secondDataset = datasetIOService.open(SECOND_INPUT_TIFF)
println("rawDataset=" + rawDataset)
println("secondDataset=" + secondDataset)

def future = command.run(ObjectClassificationCommand, true,
    "projectFileName", projectFile,
    "inputImage", rawDataset,
    "inputProbOrSegImage", secondDataset,
    "secondInputType", "Probabilities",
    "objectExportSource", OUTPUT_TYPE
)
println("future=" + future)

if (future == null) {
    throw new IllegalStateException("ObjectClassificationCommand returned null future")
}

def module = future.get()
println("module=" + module)

def predictions = module.getOutput("predictions")
println("predictions=" + predictions)
if (predictions == null) {
    throw new IllegalStateException("ObjectClassificationCommand returned null predictions")
}

def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
println("saved=" + outputFile.exists())
