# Bio-Formats — Groovy & Java Scripting API

Bio-Formats exposes a high-level scripting interface accessible from all scripting
languages supported by Fiji: **Groovy, Jython, JavaScript, BeanShell, Java**.
This interface is NOT available from the ImageJ Macro Language; use the
`IJ.run("Bio-Formats Importer", "...")` macro approach documented in the IJ Macro
section below for macros.

---

## Core Classes

| Class                              | Package                    | Purpose                                           |
|------------------------------------|----------------------------|---------------------------------------------------|
| `BF`                               | `loci.plugins`             | Top-level entry point; `openImagePlus()` method   |
| `ImporterOptions`                  | `loci.plugins.in`          | Controls all import settings                      |
| `Region`                           | `loci.common`              | Crop region: `(x, y, width, height)`              |

---

## Minimal Import (Groovy)

```groovy
import loci.plugins.BF

def path = "/path/to/myFile.czi"
def imps = BF.openImagePlus(path)  // returns ImagePlus[]
imps.each { imp ->
    imp.show()
}
```

`BF.openImagePlus()` always returns an **array** (`ImagePlus[]`), even for a single
image. Iterate over it.

---

## Full Import with ImporterOptions (Groovy)

```groovy
import loci.plugins.BF
import loci.plugins.in.ImporterOptions

def options = new ImporterOptions()
options.setId("/path/to/myFile.czi")         // path to the file — required
options.setAutoscale(true)                    // autoscale display range
options.setColorMode(ImporterOptions.COLOR_MODE_COMPOSITE)  // see color modes below
options.setOpenAllSeries(true)               // open every series in the file
options.setWindowless(true)                  // suppress all dialogs
options.setQuiet(true)                       // suppress log messages

def imps = BF.openImagePlus(options)         // ImagePlus[]
imps.each { imp ->
    imp.show()
    println "Opened: ${imp.getTitle()} — ${imp.getWidth()} x ${imp.getHeight()}"
}
```

---

## ImporterOptions Method Reference

All `set*()` methods return `void`. All `is*()` / `get*()` methods are also available
for reading current values.

### File Identity

| Method                       | Type     | Description                          |
|------------------------------|----------|--------------------------------------|
| `setId(String path)`         | required | Absolute path to the input file      |
| `setLocation(String loc)`    | String   | `"Local"`, `"HTTP"`, `"OMERO"`       |

### Display / Stack Format

| Method                              | Type    | Description                                                              |
|-------------------------------------|---------|--------------------------------------------------------------------------|
| `setAutoscale(boolean)`             | boolean | Adjust display range to min/max pixel values in dataset                  |
| `setColorMode(String mode)`         | String  | Use `ImporterOptions.COLOR_MODE_*` constants (see below)                 |
| `setStackFormat(String format)`     | String  | `"Hyperstack"`, `"Standard ImageJ"`, `"Browser"` (display mode)         |
| `setStackOrder(String order)`       | String  | `"Default"`, `"XYZCT"`, `"XYCZT"`, `"XYCTZ"`, `"XYTZC"`, `"XYTCZ"`, `"XYZTC"` |
| `setVirtual(boolean)`               | boolean | Open as a virtual (disk-resident, read-only) stack                       |

### Series Selection

| Method                              | Type    | Description                                         |
|-------------------------------------|---------|-----------------------------------------------------|
| `setOpenAllSeries(boolean)`         | boolean | Open every series in the file                       |
| `setSeriesOn(int series, boolean)`  | boolean | Enable/disable a specific series by 0-based index   |
| `clearSeries()`                     | void    | Deselect all series                                 |
| `setConcatenate(boolean)`           | boolean | Concatenate compatible series into one stack        |

### Splitting

| Method                       | Type    | Description                                             |
|------------------------------|---------|---------------------------------------------------------|
| `setSplitChannels(boolean)`  | boolean | Open each channel as a separate ImagePlus               |
| `setSplitFocalPlanes(boolean)` | boolean | Open each Z plane as a separate ImagePlus             |
| `setSplitTimepoints(boolean)` | boolean | Open each timepoint as a separate ImagePlus            |

### Dimension Ranges (per series, 0-indexed)

| Method                             | Type | Description                                     |
|------------------------------------|------|-------------------------------------------------|
| `setSpecifyRanges(boolean)`        | bool | Enable custom begin/step/end for each dimension |
| `setZBegin(int series, int value)` | int  | First Z plane to open (0-indexed)               |
| `setZEnd(int series, int value)`   | int  | Last Z plane to open (0-indexed, inclusive)     |
| `setZStep(int series, int value)`  | int  | Z step size                                     |
| `setCBegin(int series, int value)` | int  | First channel to open                           |
| `setCEnd(int series, int value)`   | int  | Last channel to open                            |
| `setCStep(int series, int value)`  | int  | Channel step size                               |
| `setTBegin(int series, int value)` | int  | First timepoint to open                         |
| `setTEnd(int series, int value)`   | int  | Last timepoint to open                          |
| `setTStep(int series, int value)`  | int  | Timepoint step size                             |

### Crop on Import

| Method                                    | Type   | Description                               |
|-------------------------------------------|--------|-------------------------------------------|
| `setCrop(boolean)`                        | bool   | Enable cropping                           |
| `setCropRegion(int series, Region r)`     | Region | Set the crop rectangle for a given series |

`Region` constructor: `new Region(int x, int y, int width, int height)`

### File Grouping

| Method                     | Type    | Description                                           |
|----------------------------|---------|-------------------------------------------------------|
| `setGroupFiles(boolean)`   | boolean | Group files with similar names into one dataset       |
| `setUngroupFiles(boolean)` | boolean | Force individual opening of grouped datasets          |
| `setStitchTiles(boolean)`  | boolean | Attempt to stitch tiles                               |
| `setMustGroup(boolean)`    | boolean | Throw an error if file cannot be grouped              |

### Metadata

| Method                       | Type    | Description                                     |
|------------------------------|---------|-------------------------------------------------|
| `setShowMetadata(boolean)`   | boolean | Show key/value metadata in a Results window     |
| `setShowOMEXML(boolean)`     | boolean | Display the OME-XML document in a window        |
| `setShowROIs(boolean)`       | boolean | Import embedded ROIs                            |
| `setROIsMode(String mode)`   | String  | `"ROI manager"` or `"Overlay"`                  |

### Miscellaneous

| Method                       | Type    | Description                                                    |
|------------------------------|---------|----------------------------------------------------------------|
| `setWindowless(boolean)`     | boolean | Suppress all dialogs (required for batch scripting)            |
| `setQuiet(boolean)`          | boolean | Suppress log/console messages                                  |
| `setSwapDimensions(boolean)` | boolean | Allow dimension swapping                                       |
| `setUpgradeCheck(boolean)`   | boolean | Check for a newer version of Bio-Formats online; set to false in scripts |

---

## Color Mode Constants

Use these string constants with `setColorMode()`:

| Constant                                  | Value String  | Description                                        |
|-------------------------------------------|---------------|----------------------------------------------------|
| `ImporterOptions.COLOR_MODE_DEFAULT`      | `"Default"`   | Use last saved mode for this format                |
| `ImporterOptions.COLOR_MODE_COMPOSITE`    | `"Composite"` | Multi-channel composite (recommended for fluorescence) |
| `ImporterOptions.COLOR_MODE_COLORIZED`    | `"Colorized"` | Pseudo-colour from metadata LUTs                   |
| `ImporterOptions.COLOR_MODE_GRAYSCALE`    | `"Grayscale"` | All channels in grayscale                          |
| `ImporterOptions.COLOR_MODE_CUSTOM`       | `"Custom"`    | Manual RGB assignment per channel                  |

---

## Recipes

### Open a specific series only

```groovy
import loci.plugins.BF
import loci.plugins.in.ImporterOptions

def options = new ImporterOptions()
options.setId("/path/to/multiSeries.lif")
options.setWindowless(true)
// Open only series 2 (0-indexed)
options.clearSeries()
options.setSeriesOn(2, true)

def imps = BF.openImagePlus(options)
imps[0].show()
```

### Open a crop region from a large image

```groovy
import loci.plugins.BF
import loci.plugins.in.ImporterOptions
import loci.common.Region

def options = new ImporterOptions()
options.setId("/path/to/largeScan.tiff")
options.setWindowless(true)
options.setCrop(true)
options.setCropRegion(0, new Region(0, 0, 512, 512))  // top-left 512x512 of series 0

def imps = BF.openImagePlus(options)
imps[0].show()
```

### Open as virtual stack (large dataset, limited RAM)

```groovy
import loci.plugins.BF
import loci.plugins.in.ImporterOptions

def options = new ImporterOptions()
options.setId("/path/to/bigDataset.nd2")
options.setWindowless(true)
options.setVirtual(true)                           // disk-resident, read-only
options.setColorMode(ImporterOptions.COLOR_MODE_COMPOSITE)

def imps = BF.openImagePlus(options)
imps[0].show()
```

### Batch open all series in a file

```groovy
import loci.plugins.BF
import loci.plugins.in.ImporterOptions

def options = new ImporterOptions()
options.setId("/path/to/experiment.lif")
options.setWindowless(true)
options.setOpenAllSeries(true)
options.setColorMode(ImporterOptions.COLOR_MODE_COMPOSITE)

def imps = BF.openImagePlus(options)
println "Opened ${imps.length} series"
imps.each { imp ->
    println "  ${imp.getTitle()}"
    imp.show()
}
```

### Batch process a directory (Groovy)

```groovy
import loci.plugins.BF
import loci.plugins.in.ImporterOptions
import ij.IJ
import java.io.File

def inputDir  = new File("/data/raw_nd2/")
def outputDir = new File("/data/converted/")
outputDir.mkdirs()

inputDir.listFiles().findAll { it.name.endsWith(".nd2") }.each { f ->
    def options = new ImporterOptions()
    options.setId(f.absolutePath)
    options.setWindowless(true)
    options.setQuiet(true)
    options.setColorMode(ImporterOptions.COLOR_MODE_COMPOSITE)

    def imps = BF.openImagePlus(options)
    imps.each { imp ->
        def outPath = new File(outputDir, imp.getTitle().replaceAll("[^\\w.]", "_") + ".tif")
        IJ.saveAsTiff(imp, outPath.absolutePath)
        imp.close()
    }
}
println "Done."
```

---

## IJ Macro Language API

The IJ Macro Language cannot call `BF.openImagePlus()` directly. Instead, use
`IJ.run()` with a parameter string:

```javascript
// Open with default settings
run("Bio-Formats Importer", "open=/path/to/file.czi autoscale color_mode=Default view=Hyperstack stack_order=XYCZT");

// Composite mode, standard recommendation for fluorescence
run("Bio-Formats Importer", "open=/path/to/file.czi autoscale color_mode=Composite view=Hyperstack stack_order=XYCZT");

// Split channels
run("Bio-Formats Importer", "open=/path/to/file.czi autoscale color_mode=Default split_channels view=Hyperstack stack_order=XYCZT");

// Import ROIs to ROI manager
run("Bio-Formats Importer", "open=/path/to/file.czi autoscale color_mode=Composite rois_import=[ROI manager] view=Hyperstack stack_order=XYCZT");

// Paths with spaces must use square brackets
run("Bio-Formats Importer", "open=[/path/with spaces/file.nd2] autoscale color_mode=Composite view=Hyperstack stack_order=XYCZT");

// Batch loop — windowless suppresses all dialogs during iteration
for (i = 0; i < list.length; i++) {
    run("Bio-Formats Importer",
        "open=[" + inputDir + list[i] + "] autoscale color_mode=Composite " +
        "view=Hyperstack stack_order=XYCZT windowless=true");
    // ... process ...
    close("*");
}
```

### Confirmed Macro Parameter Keys

| Parameter                            | Example value            | Notes                                                              |
|--------------------------------------|--------------------------|--------------------------------------------------------------------|
| `open=`                              | `/path/to/file`          | Path; wrap in `[...]` if it contains spaces                        |
| `autoscale`                          | flag (no value)          | Autoscale display range                                            |
| `color_mode=`                        | `Default`, `Composite`, `Colorized`, `Grayscale`, `Custom` |                           |
| `view=`                              | `Hyperstack`, `Standard` |                                                                    |
| `stack_order=`                       | `XYCZT`, `XYZCT`, etc.   |                                                                    |
| `split_channels`                     | flag                     | Open each channel separately                                       |
| `split_z`                            | flag                     | Open each Z plane separately                                       |
| `split_timepoints`                   | flag                     | Open each timepoint separately                                     |
| `rois_import=`                       | `[ROI manager]`          | Where to import embedded ROIs                                      |
| `windowless=true`                    | `true`                   | Suppress dialogs; uses last-saved settings for that format         |
| `group_files`                        | flag                     | Group files with similar names                                     |
| `open_all_series`                    | flag                     | Open all series in the file                                        |
| `virtual`                            | flag                     | Open as virtual stack                                              |
| `concatenate`                        | flag                     | Concatenate compatible series                                      |

> **Headless warning**: Bio-Formats does NOT work with Fiji's `--headless` option.
> Running with `--headless` produces a `VerifyError`. Use the ImageJ Launcher with
> `-batch` instead (no display required):
> ```
> ./ImageJ-linux64 -macro myMacro.ijm -batch
> ```

---

## Exporting from a Script

There are TWO supported ways to write OME-TIFF from a Groovy script. Both are
verified against Fiji's bundled Bio-Formats. Pick ONE — do not mix them.

### Option 1 — `IJ.run` against the active ImagePlus (recommended for most cases)

```groovy
import ij.IJ

def outPath = "/path/to/output.ome.tiff"          // .ome.tiff or .ome.btf for >4 GB
new java.io.File(outPath).parentFile.mkdirs()
new java.io.File(outPath).delete()                // exporter will NOT overwrite silently

// imp must already be the active/visible image
IJ.run(imp, "Bio-Formats Exporter",
       "save=[" + outPath + "] compression=Uncompressed windowless=true")
```

**Confirmed option keys** (macro-style, same in Groovy):

| Key                         | Values                                            | Notes                                  |
|-----------------------------|---------------------------------------------------|----------------------------------------|
| `save=[<path>]`             | absolute path, wrap in `[ ]` for spaces           | Required                               |
| `compression=`              | `Uncompressed`, `LZW`, `JPEG`, `JPEG-2000`        | Default `Uncompressed`                 |
| `windowless=true`           | flag                                              | Suppress confirm/overwrite dialogs     |
| `export=[<path>]`           | alternative key for older builds                  | Use only if `save=` is silently no-op  |

**Pitfalls:**
- `outfile=` is NOT a real key — the correct key is `save=`.
- `IJ.run("Bio-Formats Exporter", "...")` (no `imp` arg) writes whatever image
  currently holds focus, which is brittle. Always pass `imp` as the first arg.
- The exporter is silent on failure: it can return without writing the file.
  After the call, verify with `assert new File(outPath).exists()`.
- If the file already exists, the exporter aborts with a dialog. Delete or
  rotate the path BEFORE calling, or use `windowless=true` to force overwrite.

### Option 2 — Programmatic `OMETiffWriter` (headless / large stacks / pyramids)

```groovy
import loci.formats.out.OMETiffWriter
import loci.formats.services.OMEXMLService
import loci.common.services.ServiceFactory
import loci.formats.MetadataTools

def outPath = "/path/to/output.ome.tiff"
new java.io.File(outPath).delete()

def service = new ServiceFactory().getInstance(OMEXMLService.class)
def meta    = service.createOMEXMLMetadata()
MetadataTools.populateMetadata(meta, 0, null,
    imp.getStack().getProcessor(1).isLittleEndian() ?: false,
    "XYCZT",
    "uint" + imp.getBitDepth(),
    imp.getWidth(), imp.getHeight(),
    imp.getNSlices(), imp.getNChannels(), imp.getNFrames(),
    imp.getNChannels())

def writer = new OMETiffWriter()
writer.setMetadataRetrieve(meta)
writer.setId(outPath)
def stack = imp.getStack()
for (int i = 1; i <= stack.size(); i++) {
    writer.saveBytes(i - 1, stack.getProcessor(i).getPixels() as byte[])
}
writer.close()
```

Use this when you need true headless writes (no GUI), tiled output, BigTIFF
control, or you are streaming planes from disk and never want the full stack
in memory.

### Do NOT use

- `new loci.plugins.out.Exporter().run(path, imp)` — **the class has no such
  method**. `Exporter.run(String)` exists for GUI invocation only and reads its
  parameters from the macro recorder. Calling `run(path, imp)` raises
  `MissingMethodException` at runtime.
- `IJ.saveAsTiff(imp, path)` — writes ImageJ-flavored TIFF, not OME-TIFF.
  Strips OME metadata.
- `File › Save As › Tiff…` — same as above, not OME-TIFF.
