# 3D ImageJ Suite — Script API

This file separates the suite's scripting surface into:

- container-validated Groovy API calls
- source-grounded command strings from plugin source or installed macro files
- excluded items that are intentionally not documented as runnable API

## Container-Validated Automation

### 1. 3D mean filtering

Use the direct `FastFilters3D` API for non-interactive batch scripts.

For 8-bit or 16-bit stacks:

```groovy
import ij.ImagePlus
import ij.ImageStack
import mcib3d.image3d.processing.FastFilters3D

ImageStack filtered = FastFilters3D.filterIntImageStack(
    imp.getStack(),
    0,      // Mean
    1f,     // radius X
    1f,     // radius Y
    1f,     // radius Z
    1,      // CPU threads
    true    // show progress
)
ImagePlus filteredImp = new ImagePlus("mean3d", filtered)
filteredImp.setCalibration(imp.getCalibration())
```

For 32-bit stacks:

```groovy
ImageStack filtered = FastFilters3D.filterFloatImageStack(
    imp.getStack(),
    0, 1f, 1f, 1f, 1, true
)
```

Accepted filter indices come from the plugin source:

| Index | Filter token |
|------:|--------------|
| `0` | `Mean` |
| `1` | `Median` |
| `2` | `Minimum` |
| `3` | `Maximum` |
| `4` | `MaximumLocal` |
| `5` | `TopHat` |
| `6` | `OpenGray` |
| `7` | `CloseGray` |
| `8` | `Variance` |
| `9` | `Sobel` |
| `10` | `Adaptive` |

### 2. `IJ.run` for 3D Fast Filters

This command string was executed successfully in Fiji batch mode:

```groovy
IJ.run(imp, "3D Fast Filters",
    "filter=Mean radius_x_pix=1.0 radius_y_pix=1.0 radius_z_pix=1.0 Nb_cpus=1")
```

Use the direct `FastFilters3D.filter*ImageStack(...)` API when you want explicit
control over the returned `ImageStack`.

### 3. Threshold to binary and label 3D objects

Use `ImageHandler` and `ImageLabeller` when the image contains bright objects on
a dark background.

```groovy
import mcib3d.image3d.ImageHandler
import mcib3d.image3d.ImageLabeller

ImageHandler handler = ImageHandler.wrap(filteredImp)
def binary = handler.thresholdAboveInclusive(80f)
binary.setVoxelSize(handler)

ImageLabeller labeller = new ImageLabeller()
labeller.setMinSize(20)
// Optional:
// labeller.setMaxsize(50000)

def labels = labeller.getLabels(binary)
labels.setVoxelSize(handler)
ImagePlus labelImp = labels.getImagePlus()
labelImp.setCalibration(filteredImp.getCalibration())
```

Use `getLabelsFloat(binary)` instead of `getLabels(binary)` when you expect more
than `65,535` objects.

### 4. Volume measurements from a label image

```groovy
import ij.measure.ResultsTable
import mcib_plugins.analysis.SimpleMeasure

SimpleMeasure measure = new SimpleMeasure(labelImp)
ResultsTable volumeTable = measure.getResultsTable("Volume")
volumeTable.show("Results")
```

This table is the same measurement family exposed by `Plugins > 3DSuite > Analysis > 3D Volume`.

### 5. Intensity measurements against a separate signal image

```groovy
import ij.measure.ResultsTable
import mcib3d.geom2.measurements.MeasureIntensity
import mcib_plugins.analysis.SimpleMeasure

SimpleMeasure measure = new SimpleMeasure(labelImp)
List<Double[]> rows = measure.getMeasuresStats(signalImp)
String[] headers = new MeasureIntensity().getNamesMeasurement()

ResultsTable intensityTable = new ResultsTable()
rows.each { row ->
    intensityTable.incrementCounter()
    headers.eachWithIndex { name, i ->
        intensityTable.setValue(name, intensityTable.getCounter() - 1, row[i])
    }
}
intensityTable.show("Results")
```

`signalImp` should match the label image in size and stack layout.

### 6. 3D watershed from an automatic seed image

The suite's `3D Watershed` plugin computes automatic seeds with the
`MaximumLocal` filter when no seed image is provided. The same path can be used
directly in a batch script:

```groovy
import ij.ImagePlus
import ij.ImageStack
import mcib3d.image3d.processing.FastFilters3D
import mcib3d.image3d.regionGrowing.Watershed3D

ImageStack seedStack = FastFilters3D.filterIntImageStack(
    imp.getStack(),
    4,      // MaximumLocal
    2f, 2f, 2f,
    1,
    true
)

Watershed3D watershed = new Watershed3D(
    imp.getStack(),
    seedStack,
    80d,    // image threshold
    180     // seeds threshold
)
watershed.setLabelSeeds(true)
watershed.setAnim(false)

ImagePlus labelImp = watershed.getWatershedImage3D().getImagePlus()
```

Use `filterFloatImageStack(...)` instead of `filterIntImageStack(...)` for a
32-bit source stack.

### 7. 3D spot segmentation

Use `Segment3DSpots` when you need seed-aware segmentation of spot-like objects.
The seed image can come from `MaximumLocal` filtering or from a separate seed
stack that you prepared earlier.

```groovy
import mcib3d.image3d.ImageHandler
import mcib3d.image3d.segment.LocalThresholderConstant
import mcib3d.image3d.segment.Segment3DSpots
import mcib3d.image3d.segment.SpotSegmenterClassical

Segment3DSpots spots = new Segment3DSpots(
    ImageHandler.wrap(rawImp),
    ImageHandler.wrap(seedImp)
)
spots.setSeedsThreshold(15f)
spots.setBigLabel(false)
spots.setUseWatershed(true)
spots.setVolumeMin(1)
spots.setVolumeMax(1000000)
spots.setLocalThresholder(new LocalThresholderConstant(65f))
spots.setSpotSegmenter(new SpotSegmenterClassical())
spots.segmentAll()

ImagePlus labelImp = spots.getLabeledImage().getImagePlus()
```

The installed plugin also exposes these local thresholders:

- `LocalThresholderConstant`
- `LocalThresholderDiff`
- `LocalThresholderMean`
- `LocalThresholderGaussFit`

And these spot segmenters:

- `SpotSegmenterClassical`
- `SpotSegmenterMax`
- `SpotSegmenterBlock`

### 8. 3D nuclei segmentation

Use `Segment3DNuclei` for the suite's nuclei-specific workflow:

```groovy
import ij.process.AutoThresholder
import mcib3d.image3d.ImageHandler
import mcib3d.image3d.segment.Segment3DNuclei

Segment3DNuclei nuclei = new Segment3DNuclei(ImageHandler.wrap(imp))
nuclei.setMethod(AutoThresholder.Method.Otsu)
nuclei.setSeparate(true)
nuclei.setManual(0f)

ImagePlus labelImp = nuclei.segment().getImagePlus()
```

`setManual(0f)` keeps the automatic threshold path. Use a positive value when
you need to override the threshold chosen by the selected ImageJ method.

## Source-Grounded And Display-Dependent Commands

### 9. 3D Manager V4 macro extensions

The installed `MacroV4.ijm` file exposes the V4 macro extension names below:

```ijm
run("3D Manager V4 Macros");
Ext.Manager3DV4_ImportImage();
Ext.Manager3DV4_MeasureList();
Ext.Manager3DV4_NbObjects(nb);
Ext.Manager3DV4_Measure(0, "Volume(Unit)", value);
Ext.Manager3DV4_MeasureIntensity(0, "CMX(unit)", value);
Ext.Manager3DV4_DistanceList();
Ext.Manager3DV4_Distance2(0, 1, "DistCenterCenterPix", value);
```

Rules:

- The current image must be a labelled object image before `Ext.Manager3DV4_ImportImage()`.
- Object indices are zero-based.
- Load the manager in a display-backed Fiji session. In this repo's container,
  the macro loader initializes the 3D viewer and the extension does not
  register in true headless mode.
- Use `Ext.Manager3DV4_MeasureList()` and `Ext.Manager3DV4_DistanceList()` to
  print the names accepted by `Measure(...)` and `Distance2(...)`.

### 10. Legacy manager macros

The official docs still include examples with the older manager:

```ijm
run("3D Manager");
Ext.Manager3D_AddImage();
Ext.Manager3D_Measure();
```

Use the V4 extension names for new scripted work unless you specifically need
the older manager instance.

## Excluded Or Unverified

The following are intentionally excluded from this file:

- macro parameter strings for `3D Simple Segmentation`
- macro parameter strings for `3D Watershed`
- macro parameter strings for `3D Spot Segmentation`
- macro parameter strings for `3D Nuclei Segmentation`
- undocumented measurement-name strings beyond those returned by the V4 listing calls

For these features, use the GUI plus macro recording, or inspect the plugin
source before writing new automation.
