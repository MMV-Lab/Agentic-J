/*
 * TransformJ geometric transformation workflow.
 *
 * Required inputs:
 *   - inputFile: an ImageJ-readable image
 *   - outputFile: destination TIFF path; the script fails if it already exists
 *   - mode: one of Scale, Translate, Rotate, Turn, Mirror, Crop, Embed, Affine
 *
 * The workflow uses the ImageScience transformation classes that TransformJ
 * wraps. Coordinates for direct API modes are 0-based in all dimensions.
 */

#@ File inputFile
#@ File outputFile
#@ String(label="Mode", value="Scale") mode
#@ String(label="Interpolation", value="Linear") interpolation
#@ Boolean(label="Show ImageScience progress/logging", value=false) verbose
#@ Double(label="Scale x factor", value=1.25) scaleX
#@ Double(label="Scale y factor", value=1.25) scaleY
#@ Double(label="Scale z factor", value=1.0) scaleZ
#@ Boolean(label="Scale preserves physical dimensions", value=false) preservePhysicalDimensions
#@ Double(label="Translate x distance", value=10.0) translateX
#@ Double(label="Translate y distance", value=0.0) translateY
#@ Double(label="Translate z distance", value=0.0) translateZ
#@ Boolean(label="Translate distances are voxel units", value=true) translateVoxelUnits
#@ Double(label="Rotate z angle degrees", value=15.0) rotateZ
#@ Double(label="Rotate y angle degrees", value=0.0) rotateY
#@ Double(label="Rotate x angle degrees", value=0.0) rotateX
#@ Boolean(label="Adjust bounds to fit result", value=true) adjustBounds
#@ Boolean(label="Resample isotropically", value=false) resampleIsotropically
#@ Boolean(label="Anti-alias borders", value=false) antiAliasBorders
#@ Double(label="Background value", value=0.0) backgroundValue
#@ Integer(label="Turn z quarter turns", value=1) turnZ
#@ Integer(label="Turn y quarter turns", value=0) turnY
#@ Integer(label="Turn x quarter turns", value=0) turnX
#@ Boolean(label="Mirror x", value=true) mirrorX
#@ Boolean(label="Mirror y", value=false) mirrorY
#@ Boolean(label="Mirror z", value=false) mirrorZ
#@ Boolean(label="Mirror t", value=false) mirrorT
#@ Boolean(label="Mirror c", value=false) mirrorC
#@ Integer(label="Crop x start 0-based", value=0) cropXStart
#@ Integer(label="Crop x stop inclusive", value=63) cropXStop
#@ Integer(label="Crop y start 0-based", value=0) cropYStart
#@ Integer(label="Crop y stop inclusive", value=63) cropYStop
#@ Integer(label="Crop z start 0-based", value=0) cropZStart
#@ Integer(label="Crop z stop inclusive", value=0) cropZStop
#@ Integer(label="Crop t start 0-based", value=0) cropTStart
#@ Integer(label="Crop t stop inclusive", value=0) cropTStop
#@ Integer(label="Crop c start 0-based", value=0) cropCStart
#@ Integer(label="Crop c stop inclusive", value=0) cropCStop
#@ Integer(label="Embed output x size", value=256) embedXSize
#@ Integer(label="Embed output y size", value=256) embedYSize
#@ Integer(label="Embed output z size", value=1) embedZSize
#@ Integer(label="Embed output t size", value=1) embedTSize
#@ Integer(label="Embed output c size", value=1) embedCSize
#@ Integer(label="Embed x position 0-based", value=16) embedXPosition
#@ Integer(label="Embed y position 0-based", value=16) embedYPosition
#@ Integer(label="Embed z position 0-based", value=0) embedZPosition
#@ Integer(label="Embed t position 0-based", value=0) embedTPosition
#@ Integer(label="Embed c position 0-based", value=0) embedCPosition
#@ String(label="Embed background", value="Zero") embedBackground
#@ String(label="Affine 4x4 matrix file path", value="") matrixFilePath

import ij.IJ
import ij.ImagePlus
import imagescience.image.Aspects
import imagescience.image.Axes
import imagescience.image.Coordinates
import imagescience.image.Dimensions
import imagescience.image.Image
import imagescience.transform.Affine
import imagescience.transform.Crop
import imagescience.transform.Embed
import imagescience.transform.Mirror
import imagescience.transform.Rotate
import imagescience.transform.Scale
import imagescience.transform.Transform
import imagescience.transform.Translate
import imagescience.transform.Turn
import java.nio.file.Files

File inFile = inputFile
File outFile = outputFile

if (inFile == null || !inFile.isFile()) {
    throw new IllegalArgumentException("Input file does not exist: " + inFile)
}
if (outFile == null) {
    throw new IllegalArgumentException("Output file is required")
}
if (outFile.exists()) {
    throw new IllegalArgumentException("Output file already exists: " + outFile.absolutePath)
}
File outDir = outFile.parentFile
if (outDir != null && !outDir.isDirectory() && !outDir.mkdirs()) {
    throw new IllegalArgumentException("Could not create output directory: " + outDir.absolutePath)
}

ImagePlus imp = IJ.openImage(inFile.absolutePath)
if (imp == null) {
    throw new IllegalArgumentException("Could not open input image: " + inFile.absolutePath)
}

Image input = Image.wrap(imp)
String selectedMode = normalize(mode)
Image output

try {
    switch (selectedMode) {
        case "scale":
            Scale scaler = new Scale()
            configure(scaler, verbose)
            int scaleScheme = interpolationScheme(interpolation, Scale)
            output = scaler.run(input, scaleX, scaleY, scaleZ, 1.0d, 1.0d, scaleScheme)
            if (preservePhysicalDimensions) {
                Aspects a = input.aspects()
                output.aspects(new Aspects(a.x / scaleX, a.y / scaleY, a.z / scaleZ, a.t, a.c))
            }
            break

        case "translate":
            Translate translator = new Translate()
            configure(translator, verbose)
            translator.background = backgroundValue
            int translateScheme = interpolationScheme(interpolation, Translate)
            double dx = translateVoxelUnits ? imp.getCalibration().pixelWidth * translateX : translateX
            double dy = translateVoxelUnits ? imp.getCalibration().pixelHeight * translateY : translateY
            double dz = translateVoxelUnits ? imp.getCalibration().pixelDepth * translateZ : translateZ
            output = translator.run(input, dx, dy, dz, translateScheme)
            break

        case "rotate":
            Rotate rotator = new Rotate()
            configure(rotator, verbose)
            rotator.background = backgroundValue
            int rotateScheme = interpolationScheme(interpolation, Rotate)
            output = rotator.run(input, rotateZ, rotateY, rotateX, rotateScheme, adjustBounds, resampleIsotropically, antiAliasBorders)
            break

        case "turn":
            Turn turner = new Turn()
            configure(turner, verbose)
            output = turner.run(input, turnZ, turnY, turnX)
            break

        case "mirror":
            Mirror mirror = new Mirror()
            configure(mirror, verbose)
            output = input.duplicate()
            mirror.run(output, new Axes(mirrorX, mirrorY, mirrorZ, mirrorT, mirrorC))
            break

        case "crop":
            Crop cropper = new Crop()
            configure(cropper, verbose)
            Coordinates start = new Coordinates(cropXStart, cropYStart, cropZStart, cropTStart, cropCStart)
            Coordinates stop = new Coordinates(cropXStop, cropYStop, cropZStop, cropTStop, cropCStop)
            output = cropper.run(input, start, stop)
            break

        case "embed":
            Embed embedder = new Embed()
            configure(embedder, verbose)
            Dimensions dims = new Dimensions(embedXSize, embedYSize, embedZSize, embedTSize, embedCSize)
            Coordinates pos = new Coordinates(embedXPosition, embedYPosition, embedZPosition, embedTPosition, embedCPosition)
            output = embedder.run(input, dims, pos, embedBackgroundScheme(embedBackground))
            break

        case "affine":
            Affine affiner = new Affine()
            configure(affiner, verbose)
            affiner.background = backgroundValue
            Transform transform = loadTransform(matrixFilePath)
            int affineScheme = interpolationScheme(interpolation, Affine)
            output = affiner.run(input, transform, affineScheme, adjustBounds, resampleIsotropically, antiAliasBorders)
            break

        default:
            throw new IllegalArgumentException("Unsupported mode: " + mode)
    }

    ImagePlus outImp = output.imageplus()
    IJ.saveAsTiff(outImp, outFile.absolutePath)
    IJ.log("TransformJ " + selectedMode + " saved: " + outFile.absolutePath)
    IJ.log("Input size: " + imp.getWidth() + " x " + imp.getHeight() + " x " + imp.getNSlices())
    IJ.log("Output size: " + outImp.getWidth() + " x " + outImp.getHeight() + " x " + outImp.getNSlices())
    outImp.close()
} finally {
    imp.close()
}

String normalize(Object value) {
    return value == null ? "" : value.toString().trim().toLowerCase().replaceAll(/[\s_-]+/, "")
}

void configure(Object operation, boolean enabled) {
    if (operation.hasProperty("messenger")) operation.messenger.log(enabled)
    if (operation.hasProperty("progressor")) operation.progressor.display(enabled)
}

int interpolationScheme(String label, Class owner) {
    switch (normalize(label)) {
        case "nearest":
        case "nearestneighbor":
            return owner.NEAREST
        case "linear":
            return owner.LINEAR
        case "cubic":
        case "cubicconvolution":
            return owner.CUBIC
        case "bspline3":
        case "cubicbspline":
            return owner.BSPLINE3
        case "omoms3":
        case "cubicomoms":
            return owner.OMOMS3
        case "bspline5":
        case "quinticbspline":
            return owner.BSPLINE5
        default:
            throw new IllegalArgumentException("Unsupported interpolation: " + label)
    }
}

int embedBackgroundScheme(String label) {
    switch (normalize(label)) {
        case "zero":
            return Embed.ZERO
        case "minimum":
        case "min":
            return Embed.MINIMUM
        case "maximum":
        case "max":
            return Embed.MAXIMUM
        case "repeat":
            return Embed.REPEAT
        case "mirror":
            return Embed.MIRROR
        case "clamp":
            return Embed.CLAMP
        default:
            throw new IllegalArgumentException("Unsupported embed background: " + label)
    }
}

Transform loadTransform(String path) {
    if (path == null || path.trim().isEmpty()) {
        throw new IllegalArgumentException("Affine mode requires matrixFilePath")
    }
    File matrixFile = new File(path)
    if (!matrixFile.isFile()) {
        throw new IllegalArgumentException("Matrix file does not exist: " + matrixFile.absolutePath)
    }

    List<String> rows = Files.readAllLines(matrixFile.toPath()).findAll { line ->
        !line.trim().isEmpty()
    }
    if (rows.size() != 4) {
        throw new IllegalArgumentException("Affine matrix file must contain exactly four non-empty rows")
    }

    double[][] values = new double[4][4]
    rows.eachWithIndex { String row, int r ->
        String[] parts = row.trim().split(/[\t ,]+/)
        if (parts.length != 4) {
            throw new IllegalArgumentException("Affine matrix row " + (r + 1) + " must contain four values")
        }
        parts.eachWithIndex { String part, int c ->
            values[r][c] = Double.parseDouble(part)
        }
    }
    return new Transform(values)
}
