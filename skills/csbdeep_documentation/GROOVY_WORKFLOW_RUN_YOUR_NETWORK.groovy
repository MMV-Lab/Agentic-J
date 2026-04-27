#@ File(label = "Input image", value = "/data/example_1.tif") inputFile
#@ File(label = "Output TIFF", style = "save", value = "/data/csbdeep_validation/example_1-restored.tif") outputFile
#@ File(label = "Model ZIP", required = false) modelFile
#@ String(label = "Model URL", required = false, value = "") modelUrl
#@ Integer(label = "Number of tiles", min = 1, value = 8) nTiles
#@ Integer(label = "Tile size multiple", min = 1, value = 32) blockMultiple
#@ Integer(label = "Tile overlap", min = 0, value = 32) overlap
#@ Integer(label = "Batch size", min = 1, value = 1) batchSize
#@ Boolean(label = "Normalize input", value = true) normalizeInput
#@ Float(label = "Bottom percentile", value = 3.0, stepSize = 0.1) percentileBottom
#@ Float(label = "Top percentile", value = 99.8, stepSize = 0.1) percentileTop
#@ Boolean(label = "Clip normalization", value = false) clip
#@ Boolean(label = "Show progress dialog", value = false) showProgressDialog
#@ DatasetIOService datasetIO
#@ CommandService command

import de.csbdresden.csbdeep.commands.GenericNetwork

/*
 * CSBDeep — Run your network from a local ZIP or URL
 *
 * REQUIRED INPUTS:
 *   inputFile  - image to restore
 *   outputFile - new TIFF path to write
 *   modelFile  - exported CSBDeep/CARE model ZIP on disk
 *   modelUrl   - optional URL to a model ZIP; use this only when modelFile is empty
 *
 * NOTES:
 *   - Provide exactly one model source: modelFile or modelUrl.
 *   - This workflow fails if outputFile already exists.
 *   - Adjust nTiles / overlap / normalization for your model and image size.
 */

if (inputFile == null || !inputFile.exists()) {
    throw new IllegalArgumentException("Input image not found: " + inputFile)
}
if (outputFile == null) {
    throw new IllegalArgumentException("Output TIFF file must be provided")
}

boolean hasModelFile = modelFile != null && modelFile.exists()
boolean hasModelUrl = modelUrl != null && modelUrl.trim().length() > 0

if (hasModelFile == hasModelUrl) {
    throw new IllegalArgumentException(
        "Provide exactly one model source: an existing modelFile or a non-empty modelUrl."
    )
}

outputFile.getParentFile()?.mkdirs()
if (outputFile.exists()) {
    throw new IllegalArgumentException("Output file already exists: " + outputFile.absolutePath)
}

def inputDataset = datasetIO.open(inputFile.absolutePath)
if (inputDataset == null) {
    throw new IllegalStateException("Could not open input image: " + inputFile.absolutePath)
}

def args = [
    "input", inputDataset,
    "nTiles", nTiles,
    "blockMultiple", blockMultiple,
    "overlap", overlap,
    "batchSize", batchSize,
    "normalizeInput", normalizeInput,
    "percentileBottom", percentileBottom,
    "percentileTop", percentileTop,
    "clip", clip,
    "showProgressDialog", showProgressDialog
]

if (hasModelFile) {
    args += ["modelFile", modelFile]
} else {
    args += ["modelUrl", modelUrl.trim()]
}

println("CSBDeep Run your network")
println("Input      : " + inputFile.absolutePath)
println("Output     : " + outputFile.absolutePath)
println("Model file : " + (hasModelFile ? modelFile.absolutePath : "<none>"))
println("Model URL  : " + (hasModelUrl ? modelUrl.trim() : "<none>"))

def module = command.run(GenericNetwork, false, args as Object[]).get()
def outputDataset = module.getOutput("output")

if (outputDataset == null) {
    throw new IllegalStateException("CSBDeep GenericNetwork returned no output dataset.")
}

datasetIO.save(outputDataset, outputFile.absolutePath)
if (!outputFile.exists() || outputFile.length() == 0L) {
    throw new IllegalStateException("CSBDeep did not write an output TIFF: " + outputFile.absolutePath)
}

println("Saved restored image: " + outputFile.absolutePath)
