// These #@ lines inject Fiji services; they must stay at the top of the file.
#@ CommandService command
#@ net.imagej.DatasetService datasetService
#@ org.scijava.options.OptionsService optionsService
#@ io.scif.services.DatasetIOService datasetIOService

import java.io.File
import org.ilastik.ilastik4ij.ui.IlastikOptions
import org.ilastik.ilastik4ij.workflow.PixelClassificationCommand

/*
 * ilastik — Run a trained Pixel Classification project from Fiji
 *
 * PURPOSE:
 *   1. Configure the ilastik executable path used by ilastik4ij
 *   2. Open a raw input image as a Dataset
 *   3. Apply a trained ilastik Pixel Classification project
 *   4. Save the returned probabilities or segmentation as TIFF
 *
 * REQUIRED INPUTS:
 *   EXECUTABLE   - absolute path to the ilastik executable, for example run_ilastik.sh
 *   PROJECT_FILE - absolute path to a trained Pixel Classification .ilp file
 *   INPUT_TIFF   - absolute path to the raw image to process
 *   OUTPUT_TYPE  - Probabilities or Segmentation
 *   OUTPUT_TIFF  - absolute path to the TIFF that will be written
 *
 * IMPORTANT:
 *   - The .ilp project must be closed in ilastik before Fiji runs it
 *   - The image dimensionality and channel layout must match the project
 *   - This script saves the command output returned as `predictions`
 */

String EXECUTABLE = "/home/imagentj/ilastik-1.4.1.post1-Linux/run_ilastik.sh"
String PROJECT_FILE = "/data/ilastik_validation/pixel_class_2d_cells_apoptotic.ilp"
String INPUT_TIFF = "/data/ilastik_validation/2d_cells_apoptotic.tif"
String OUTPUT_TYPE = "Probabilities"
String OUTPUT_TIFF = "/data/ilastik_validation/pixel_class_probabilities.tif"

if (!(OUTPUT_TYPE in ["Probabilities", "Segmentation"])) {
    throw new IllegalArgumentException(
        "OUTPUT_TYPE must be Probabilities or Segmentation: " + OUTPUT_TYPE)
}

def executableFile = new File(EXECUTABLE)
def projectFile = new File(PROJECT_FILE)
def inputFile = new File(INPUT_TIFF)
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
outputFile.getParentFile()?.mkdirs()
if (outputFile.exists()) {
    outputFile.delete()
}

def options = optionsService.getOptions(IlastikOptions)
options.executableFile = executableFile
options.numThreads = -1
options.maxRamMb = 4096
options.save()

def dataset = datasetIOService.open(INPUT_TIFF)
println("dataset=" + dataset)

def future = command.run(PixelClassificationCommand, true,
    "projectFileName", projectFile,
    "inputImage", dataset,
    "pixelClassificationType", OUTPUT_TYPE
)
println("future=" + future)

if (future == null) {
    throw new IllegalStateException("PixelClassificationCommand returned null future")
}

def module = future.get()
println("module=" + module)

def predictions = module.getOutput("predictions")
println("predictions=" + predictions)
if (predictions == null) {
    throw new IllegalStateException("PixelClassificationCommand returned null predictions")
}

def outputDataset = datasetService.create(predictions)
datasetIOService.save(outputDataset, OUTPUT_TIFF)
println("saved=" + outputFile.exists())
