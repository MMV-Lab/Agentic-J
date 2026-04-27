#@ File(label = "Input image", value = "/data/example_1.tif") inputFile
#@ File(label = "Output TIFF", style = "save", value = "/data/csbdeep_validation/example_1-tribolium-demo.tif") outputFile
#@ Integer(label = "Number of tiles", min = 1, value = 8) nTiles
#@ Boolean(label = "Show progress dialog", value = false) showProgressDialog
#@ DatasetIOService datasetIO
#@ CommandService command

import de.csbdresden.csbdeep.commands.NetTribolium

/*
 * CSBDeep — Tribolium demo model
 *
 * REQUIRED INPUTS:
 *   inputFile  - image to denoise
 *   outputFile - new TIFF path to write
 *
 * NOTES:
 *   - The demo downloads the Tribolium model from the official CSBDeep URL.
 *   - This workflow fails if outputFile already exists.
 *   - The same command accepts 2D XY images and XYZ stacks.
 */

if (inputFile == null || !inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + inputFile)
}
if (outputFile == null) {
    throw new IllegalArgumentException("Output TIFF file must be provided")
}

outputFile.getParentFile()?.mkdirs()
if (outputFile.exists()) {
    throw new IllegalArgumentException("Output file already exists: " + outputFile.absolutePath)
}

def inputDataset = datasetIO.open(inputFile.absolutePath)
if (inputDataset == null) {
    throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
}

println("CSBDeep Tribolium demo")
println("Input  : " + inputFile.absolutePath)
println("Output : " + outputFile.absolutePath)

def module = command.run(NetTribolium, false,
    "input", inputDataset,
    "nTiles", nTiles,
    "showProgressDialog", showProgressDialog
).get()

def outputDataset = module.getOutput("output")
if (outputDataset == null) {
    throw new IllegalStateException("CSBDeep NetTribolium returned no output dataset.")
}

datasetIO.save(outputDataset, outputFile.absolutePath)
if (!outputFile.exists() || outputFile.length() == 0L) {
    throw new IllegalStateException("CSBDeep did not write an output TIFF: " + outputFile.absolutePath)
}

println("Saved demo result: " + outputFile.absolutePath)
