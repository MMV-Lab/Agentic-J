// These #@ lines inject Fiji parameters; they must stay at the top of the file.
// Run with EVERY parameter set explicitly — SciJava remembers values from earlier runs.
// Running without a dialog (e.g. from an agent): replace each #@ line with a plain variable
// of the same name and type (`File input = new File("/path")`, `String gpuMode = "auto"`);
// change nothing else. Fiji services are fetched in the code, not via #@.
#@ File (label = "Labkit segmentation (<stem>_labkit_seg.tif)") segFile
#@ File (label = "Intensity image (the raw marker channel)") rawFile
#@ Integer (label = "Channel of the intensity image (1-based)", value = 1) channel
#@ Integer (label = "Marker class value in the segmentation (0-based class index)", value = 1) markerValue
#@ Double (label = "Min object size (µm³ in 3D, µm² in 2D; calibrated units)", value = 20.0) minSize
#@ Double (label = "Max object size (0 = no limit)", value = 0.0) maxSize
#@ Double (label = "Min sphericity 0-1 (3D only; 0 = off)", value = 0.0) minSphericity
#@ File (label = "Output folder", style = "directory") outputDir

import ij.IJ
import ij.ImagePlus
import ij.plugin.Duplicator
import inra.ijpb.binary.BinaryImages
import inra.ijpb.label.LabelImages
import inra.ijpb.measure.IntensityMeasures
import inra.ijpb.measure.region3d.Centroid3D
import inra.ijpb.measure.region3d.IntrinsicVolumes3D

/*
 * Labkit follow-up — turn the marker class into objects, filter them, measure them
 *
 * Pixel classification answers "which voxels look like marker"; it does not know objects.
 * Small bright specks, debris or fragments of the marker class are removed here by SIZE (and in 3D
 * optionally by sphericity), in calibrated units so the thresholds mean the same thing on
 * every stack. Typical starting point for cells: minSize ~ volume of a sphere a few µm
 * across (sphere of 3 µm diameter = 14 µm³), then check the dropped vs kept objects on an
 * overlay and adjust. Choose thresholds from the data (look at the size column of the
 * unfiltered table, i.e. run once with minSize = 0) — never copy numbers between datasets.
 *
 * OUTPUT (outputDir)
 *   <stem>_objects.tif        16-bit label image of the KEPT objects (calibrated)
 *   <stem>_objects.csv        one row per kept object: label, volume/area, equivalent diameter,
 *                             sphericity (3D), mean intensity, centroid (calibrated units)
 *   Prints MARKER_OBJECTS_OK <kept> of <all> objects.
 * Connectivity: 26 in 3D, 8 in 2D.
 */

outputDir.mkdirs()
ImagePlus seg = IJ.openImage(segFile.absolutePath)
ImagePlus raw = IJ.openImage(rawFile.absolutePath)
if (seg == null || raw == null) throw new IllegalArgumentException("Could not open segmentation or intensity image")
if (raw.getNChannels() > 1) raw = new Duplicator().run(raw, channel, channel, 1, raw.getNSlices(), 1, raw.getNFrames())
if (seg.getNFrames() > 1 || raw.getNFrames() > 1) throw new IllegalArgumentException("One time point at a time (duplicate a frame first)")
if (seg.getWidth() != raw.getWidth() || seg.getHeight() != raw.getHeight() || seg.getStackSize() != raw.getStackSize())
    throw new IllegalArgumentException("Segmentation and intensity image differ in size")
def cal = raw.getCalibration()
seg.setCalibration(cal.copy())
boolean is3d = seg.getStackSize() > 1
String unit = cal.getUnit()

// binary mask of the marker class (255) -> connected components
def mask = seg.duplicate()
for (int z = 1; z <= mask.getStackSize(); z++) {
    def ip = mask.getStack().getProcessor(z)
    for (int i = 0; i < ip.getPixelCount(); i++) ip.set(i, ip.get(i) == markerValue ? 255 : 0)
}
ImagePlus lab = BinaryImages.componentsLabeling(mask, is3d ? 26 : 8, 16)
lab.setCalibration(cal.copy())
int[] labels = LabelImages.findAllLabels(lab)
IJ.log("[objects] " + labels.length + " connected components of class " + markerValue)
if (labels.length == 0) { println("MARKER_OBJECTS_OK 0 of 0"); return }

double[] size = new double[labels.length]; double[] spher = new double[labels.length]
if (is3d) {
    def res = new IntrinsicVolumes3D().analyzeRegions(lab.getStack(), labels, cal)
    for (int i = 0; i < labels.length; i++) { size[i] = res[i].volume; spher[i] = res[i].sphericity() }
} else {
    int[] px = LabelImages.voxelCount(lab.getStack(), labels)
    for (int i = 0; i < labels.length; i++) { size[i] = px[i] * cal.pixelWidth * cal.pixelHeight; spher[i] = Double.NaN }
}
List<Integer> keep = []
for (int i = 0; i < labels.length; i++) {
    boolean ok = size[i] >= minSize && (maxSize <= 0 || size[i] <= maxSize) && (!is3d || minSphericity <= 0 || spher[i] >= minSphericity)
    if (ok) keep << i
}
int[] drop = (0..<labels.length).findAll { !(it in keep) }.collect { labels[it] } as int[]
if (drop.length > 0) LabelImages.replaceLabels(lab, drop, 0)
IJ.log(String.format("[objects] kept %d, dropped %d (size %s %s, max %s, sphericity >= %s)", keep.size(), drop.length,
        minSize, is3d ? unit + "^3" : unit + "^2", maxSize > 0 ? maxSize : "none", minSphericity))

String stem = segFile.name.replaceFirst(/_labkit_seg\.tif$/, "").replaceFirst(/\.[^.]+$/, "")
def meanTable = new IntensityMeasures(raw, lab).getMean()
Map<Integer, Double> meanByLabel = [:]
for (int r = 0; r < meanTable.size(); r++) meanByLabel[(int) Double.parseDouble(meanTable.getLabel(r))] = meanTable.getValueAsDouble(0, r)
def cents = is3d ? Centroid3D.centroids(lab.getStack(), keep.collect { labels[it] } as int[], cal) : null

StringBuilder csv = new StringBuilder()
csv << (is3d ? "label,volume_${unit}3,equiv_diameter_${unit},sphericity,mean_intensity,centroid_x_${unit},centroid_y_${unit},centroid_z_${unit}\n"
             : "label,area_${unit}2,equiv_diameter_${unit},mean_intensity\n")
keep.eachWithIndex { int i, int j ->
    double d = is3d ? Math.cbrt(6.0 * size[i] / Math.PI) : 2.0 * Math.sqrt(size[i] / Math.PI)
    Double mean = meanByLabel[labels[i]]
    if (is3d) csv << String.format(Locale.ROOT, "%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n", labels[i], size[i], d, spher[i], mean ?: Double.NaN,
            cents[j].getX(), cents[j].getY(), cents[j].getZ())
    else csv << String.format(Locale.ROOT, "%d,%.4f,%.4f,%.4f\n", labels[i], size[i], d, mean ?: Double.NaN)
}
new File(outputDir, stem + "_objects.csv").text = csv.toString()
IJ.saveAsTiff(lab, new File(outputDir, stem + "_objects.tif").absolutePath)
if (keep) {
    def sizes = keep.collect { size[it] }.sort()
    IJ.log(String.format("[objects] kept sizes min/median/max = %.3g / %.3g / %.3g %s", sizes[0], sizes[sizes.size().intdiv(2)], sizes[-1],
            is3d ? unit + "^3" : unit + "^2"))
}
println("MARKER_OBJECTS_OK " + keep.size() + " of " + labels.length)
