# Bio-Formats — Overview

## What is Bio-Formats?

Bio-Formats is a Java library and Fiji plugin for **reading and writing life sciences
image file formats**. Its primary purpose is to convert proprietary microscopy data into
an open standard called the OME data model, particularly the OME-TIFF file format. It
parses both pixel data and acquisition metadata, standardising them into a common
representation regardless of the source instrument.

Developed by the Open Microscopy Environment (OME) consortium — including teams at the
University of Dundee and Glencoe Software — it supports **more than 150 proprietary file
formats**. Bio-Formats is bundled with Fiji by default and is the engine behind
`File › Open` for most microscopy formats. It is also available as a standalone tool set
(`bftools`) for headless conversion on servers and compute clusters.

- **Current version**: 8.4.0 (released January 14, 2026)
- **License**: GNU GPL v2 (commercial via Glencoe Software)
- **DOI**: https://doi.org/10.1083/jcb.201004104
- **Downloads**: https://www.openmicroscopy.org/bio-formats/downloads/
- **Documentation**: https://bio-formats.readthedocs.io/en/v8.4.0/
- **Source code**: https://github.com/ome/bioformats

---

## Representative Supported Formats (Input)

Bio-Formats reads more than 150 formats. A few key ones:

| Vendor / Domain        | Format examples                                       |
|------------------------|------------------------------------------------------|
| Zeiss                  | `.czi`, `.lsm`, `.zvi`                               |
| Leica                  | `.lif`, `.lif2`, `.lof`                              |
| Nikon                  | `.nd2`, `.nd`                                        |
| Olympus                | `.oif`, `.oib`                                       |
| PerkinElmer            | `.flex`, `.operaflex`                                |
| Metamorph              | `.stk`, `.nd`                                        |
| Imaris                 | `.ims`                                               |
| FluoView               | `.fv2`, `.oib`                                       |
| Cellomics / Columbus   | `.c01`                                               |
| DICOM (microscopy)     | `.dcm`, `.dicom`                                     |
| Standard open formats  | `.tif`/`.tiff`, `.ome.tiff`, `.ome.xml`, `.png`      |

For the full list: https://bio-formats.readthedocs.io/en/v8.4.0/supported-formats.html

---

## Writable Output Formats

Bio-Formats can write to a smaller set of formats:

| Extension(s)                            | Format                        | Notes                    |
|-----------------------------------------|-------------------------------|--------------------------|
| `.ome.tif`, `.ome.tiff`                 | OME-TIFF                      | Recommended output       |
| `.ome.btf`, `.ome.tf2`, `.ome.tf8`      | OME-TIFF BigTIFF              | No 4 GB size limit       |
| `.tif`, `.tiff`, `.tf2`, `.tf8`, `.btf` | Plain TIFF / BigTIFF          |                          |
| `.ome`, `.ome.xml`                      | OME-XML                       |                          |
| `.png`                                  | Animated PNG                  |                          |
| `.jpg`, `.jpeg`, `.jpe`                 | JPEG                          | Lossy                    |
| `.jp2`                                  | JPEG-2000                     |                          |
| `.avi`                                  | AVI                           | Movie                    |
| `.mov`                                  | QuickTime                     | Movie                    |
| `.eps`, `.epsi`                         | Encapsulated PostScript       |                          |
| `.ids`, `.ics`                          | Image Cytometry Standard      |                          |
| `.ch5`                                  | CellH5                        |                          |

> **BigTIFF note**: extensions `.tf2`, `.tf8`, and `.btf` automatically select
> the 64-bit BigTIFF variant, which lifts the 4 GB size limit of standard TIFF.
> You can also force BigTIFF with the `-bigtiff` flag on bfconvert.

---

## Use Cases

1. **Open a proprietary microscopy file in Fiji** — drag-and-drop or use the
   Bio-Formats Importer to import `.czi`, `.nd2`, `.lif`, `.oif` etc. with full
   calibration and channel metadata preserved.

2. **Batch convert a folder of proprietary files to OME-TIFF** — use `bfconvert`
   from the command line (or drive it from Python `subprocess`) to convert an
   entire experiment to a portable open format.

3. **Extract metadata without loading pixels** — use `showinf -nopix` to read
   acquisition metadata, OME-XML, pixel dimensions and channel names without
   ever loading the image data into memory.

4. **Open only specific series or channels** — multi-series files (e.g. Leica
   `.lif` with dozens of acquisitions) can be opened one series at a time via
   the Importer dialog, the `ImporterOptions` API, or bfconvert `-series N`.

5. **Convert a large whole-slide image to a tiled pyramid OME-TIFF** — use
   `bfconvert -noflat -pyramid-resolutions N -pyramid-scale 2` to create a
   properly tiled, multi-resolution pyramid for downstream analysis.

6. **Automate format conversion in a pipeline** — drive `bfconvert` via Python
   `subprocess` as part of a larger analysis workflow, without requiring Fiji
   to be running.

---

## Architecture: Three Automation Pathways

Bio-Formats supports three distinct automation pathways. The right one depends
on where your code runs:

### Pathway 1 — Fiji Plugin (GUI + IJ Macro)

Bio-Formats is bundled with Fiji. The importer is integrated with `File › Open`
and exposes an `IJ.run()` macro interface:

```
run("Bio-Formats Importer", "open=/path/to/file autoscale color_mode=Composite view=Hyperstack stack_order=XYCZT");
```

This is the only pathway available from the **ImageJ Macro Language**. Note that
Bio-Formats does **not** work in true `--headless` mode — use the ImageJ Launcher
`-batch` flag instead.

### Pathway 2 — Groovy / Java Scripting Within Fiji

All scripting languages supported by Fiji (Groovy, Jython, JavaScript, BeanShell,
Java) can call Bio-Formats directly through the `loci.plugins.BF` class and
`loci.plugins.in.ImporterOptions`:

```groovy
import loci.plugins.BF
import loci.plugins.in.ImporterOptions

def options = new ImporterOptions()
options.setId("/path/to/file")
options.setColorMode(ImporterOptions.COLOR_MODE_COMPOSITE)
def imps = BF.openImagePlus(options)
imps.each { it.show() }
```

This is the preferred pathway for scripted workflows running inside Fiji.
See `GROOVY_SCRIPT_API.md` for the full API reference.

---

## Installation

### In Fiji (bundled by default)

Bio-Formats ships with every Fiji installation. To update to the latest release:

1. **Help › Update…**
2. Click **Manage Update Sites**
3. Tick the **Bio-Formats** checkbox
4. Click **Close**, then **Apply Changes**
5. Restart Fiji

To verify the installed version: **Help › About Plugins › Bio-Formats Plugins…**


---

## Key Limitations

- **No true headless mode**: When used as a Fiji macro, Bio-Formats requires a
  display connection. Running with `--headless` produces a `VerifyError`. Use
  the ImageJ Launcher with the `-batch` flag instead.
- **Windowless Importer uses last-used settings**: If you call the Windowless
  Importer from a macro for a new format, it uses the last-saved settings for
  that format. Always run the format manually at least once first to set defaults.
- **Exporting via File > Save does not invoke Bio-Formats**: To write OME-TIFF
  you must use Plugins › Bio-Formats › Bio-Formats Exporter (or the macro API).
  `File › Save As…` writes an ImageJ-specific TIFF, not OME-TIFF.
- **BF.openImagePlus() returns an array**: The return type is `ImagePlus[]`, not
  a single `ImagePlus`. Always iterate over the array.
- **Series indices are 0-based**: Both the CLI (`-series 0`) and the Java API
  (`setSeriesOn(0, true)`) count from zero.

---

## Citation

Linkert M et al. (2010) Metadata matters: access to image data in the real world.
*Journal of Cell Biology* 189(5): 777–782.
https://doi.org/10.1083/jcb.201004104
