# Bio-Formats — UI Guide

All Bio-Formats plugins are under **Plugins › Bio-Formats ›** in Fiji.

---

## Plugins Available

| Plugin                              | Purpose                                                                          |
|-------------------------------------|----------------------------------------------------------------------------------|
| **Bio-Formats Importer**            | Import files into Fiji; shows the Import Options dialog                          |
| **Bio-Formats Exporter**            | Export the current image to a Bio-Formats-supported format                       |
| **Bio-Formats Remote Importer**     | Import from a remote URL (less robust than local files)                          |
| **Bio-Formats Windowless Importer** | Import using last-used settings for that format; suppresses the dialog           |
| **Bio-Formats Macro Extensions**    | Prints macro extension commands to the Log window                                |
| **Stack Slicer**                    | Split a stack across channels, focal planes, or timepoints; also used internally |
| **Bio-Formats Plugins Configuration** | Configure per-format behaviour; enable/disable formats; set windowless mode   |
| **Bio-Formats Plugins Shortcut Window** | Quick-launch buttons; supports drag-and-drop                                 |

---

## Opening Files

There are three ways to trigger Bio-Formats:

1. **Plugins › Bio-Formats › Bio-Formats Importer** — always shows the Import Options dialog.
2. **Drag and drop** onto the Bio-Formats Plugins Shortcut Window.
3. **File › Open** — Fiji automatically delegates to Bio-Formats if the format is
   not handled by another plugin.

If you see the Bio-Formats Import Options dialog, Bio-Formats is handling the file.
If you do not see it, Fiji used a different plugin (e.g. for plain TIFFs).

---

## Bio-Formats Import Options Dialog

The dialog appears when opening a file through the Importer plugin (unless the
format is set to "Windowless" in the Configuration dialog). Settings are remembered
per format.

### Pixel Import Section

| Option                       | Values / Notes                                                                                          |
|------------------------------|---------------------------------------------------------------------------------------------------------|
| **Autoscale**                | checkbox — adjusts the display range to the minimum and maximum pixel values in the dataset             |
| **Color Mode**               | `Default` · `Composite` · `Colorized` · `Grayscale` · `Custom` — see below                             |
| **Split channels**           | checkbox — opens each channel as a separate ImagePlus window                                            |
| **Split focal planes**       | checkbox — opens each Z-slice as a separate ImagePlus window                                            |
| **Split timepoints**         | checkbox — opens each timepoint as a separate ImagePlus window                                          |
| **Swap dimensions**          | checkbox — lets you rearrange the order of XYZCT dimensions                                             |
| **Open all series**          | checkbox — opens every series in the file simultaneously                                                |
| **Concatenate series**       | checkbox — combine compatible series into one stack                                                     |
| **Stitch tiles**             | checkbox — attempt to stitch tiles from a tiled dataset                                                 |
| **Group files with similar names** | checkbox — combine related files (e.g., time series saved as individual files) into one dataset    |
| **Ungroup files**            | checkbox — force each file in a grouped dataset to open separately                                      |
| **Open files individually**  | checkbox — open multi-file datasets one file at a time                                                  |
| **Specify ranges**           | checkbox — specify which Z, C, and T planes to open (enables begin/step/end controls per dimension)     |
| **Crop on import**           | checkbox — specify X, Y, width, height of a region to import                                           |

### Color Mode Values

| Value         | Description                                                                              |
|---------------|------------------------------------------------------------------------------------------|
| `Default`     | Use the mode last set for this format; typically opens as a composite or grayscale stack |
| `Composite`   | Multi-channel composite image; recommended for fluorescence data                         |
| `Colorized`   | Channels are pseudo-coloured using metadata LUTs                                         |
| `Grayscale`   | All channels displayed in grayscale                                                      |
| `Custom`      | Manually assign RGB values per channel (`series_N_channel_N_red/green/blue` in macros)   |

### View Stack With Section

| Option              | Description                                                                       |
|---------------------|-----------------------------------------------------------------------------------|
| `Hyperstack`        | Multi-dimensional hyperstack with separate C/Z/T sliders (recommended)            |
| `Standard ImageJ`   | Flattened linear stack; use with `Stack order: Default` if channels are interleaved |
| `Browser`           | Opens in the Data Browser (if available)                                          |

### Stack Order

Controls the order in which planes are assigned to stack positions when using "Standard ImageJ" view:

| Value     | Meaning                          |
|-----------|----------------------------------|
| `Default` | Order as specified in the file   |
| `XYZCT`   | Z fastest, then C, then T        |
| `XYCZT`   | C fastest, then Z, then T        |
| `XYCTZ`   | C fastest, then T, then Z        |
| `XYTZC`   | T fastest, then Z, then C        |
| `XYTCZ`   | T fastest, then C, then Z        |
| `XYZTC`   | Z fastest, then T, then C        |

### Metadata Section

| Option                        | Description                                                              |
|-------------------------------|--------------------------------------------------------------------------|
| **Display metadata**          | Show acquisition metadata (key/value pairs) in a separate Results window |
| **Show OME-XML metadata**     | Display the full OME-XML document in a separate window                   |
| **Show ROIs**                 | Import ROIs embedded in the file                                         |
| **ROIs import mode**          | `ROI manager` · `Overlay` — where to put imported ROIs                   |

### Memory Section

| Option           | Description                                                               |
|------------------|---------------------------------------------------------------------------|
| **Open as virtual stack** | Load planes from disk on demand instead of into RAM (read-only) |

---

## Multi-Series Files (Series Options Dialog)

When a file contains multiple series (e.g., a Leica `.lif` with many acquisitions),
a second **Bio-Formats Series Options** dialog appears after the Import Options dialog.
It shows all series in the file with thumbnail previews and lets you select which
ones to open.

---

## Bio-Formats Plugins Configuration Dialog

**Plugins › Bio-Formats › Bio-Formats Plugins Configuration**

### Formats Tab

Lists all supported formats. For each:
- **Enabled** checkbox — toggles whether Bio-Formats handles this format
- **Windowless** checkbox — when ticked, this format skips the Import Options
  dialog and uses the last-saved settings for that format
- Format-specific options (e.g. QuickTime: choose library)

Use this to disable a format if your file is being detected incorrectly (e.g. a
TIFF that Bio-Formats misidentifies).

### Libraries Tab

Shows which optional helper libraries are available (e.g. native decoders).

### General Tab

- **Slice label pattern** — controls the text displayed on each slice.
  Available tokens:
  - `%s` — series index (1-based)
  - `%n` — series name
  - `%c` — channel index (1-based)
  - `%w` — channel name
  - `%z` — Z index (1-based)
  - `%t` — T index (1-based)
  - `%A` — acquisition timestamp

---

## Bio-Formats Exporter

**Plugins › Bio-Formats › Bio-Formats Exporter**

Saves the current image using Bio-Formats. The output format is determined by
the file extension you enter in the save dialog.

> **Important**: `File › Save As…` does NOT invoke Bio-Formats. It saves an
> ImageJ-specific TIFF. To write OME-TIFF you must use the Bio-Formats Exporter.

Supported output extensions:

| Extension                            | Format                  |
|--------------------------------------|-------------------------|
| `.ome.tif`, `.ome.tiff`              | OME-TIFF (standard)     |
| `.ome.btf`, `.ome.tf2`, `.ome.tf8`   | OME-TIFF (BigTIFF)      |
| `.tif`, `.tiff`                      | TIFF (standard, ≤4 GB)  |
| `.tf2`, `.tf8`, `.btf`               | BigTIFF                 |
| `.png`                               | Animated PNG            |
| `.jpg`, `.jpeg`, `.jpe`              | JPEG                    |
| `.jp2`                               | JPEG-2000               |
| `.avi`                               | AVI                     |
| `.mov`                               | QuickTime               |
| `.eps`, `.epsi`                      | EPS                     |
| `.ids`, `.ics`                       | ICS                     |
| `.ome`, `.ome.xml`                   | OME-XML                 |

---

## Common Troubleshooting

| Symptom                                         | Cause / Fix                                                                                        |
|-------------------------------------------------|----------------------------------------------------------------------------------------------------|
| Import Options dialog does not appear           | File format is set to Windowless in the Configuration dialog, or Fiji used a different plugin      |
| Multi-channel fluorescence image opens flat     | Change Color Mode to `Composite` and view to `Hyperstack`                                          |
| File contains many series but only one opens    | Tick "Open all series" or select the correct series in the Series Options dialog                   |
| Channels appear interleaved in standard stack   | Use View `Standard ImageJ` + `Stack order: Default`, then Image › Hyperstack › Stack to Hyperstack |
| Memory error on large file                      | Enable "Open as virtual stack"; increase max memory via Edit › Options › Memory & Threads          |
| Wrong format detected                           | Use Plugins Configuration to disable the conflicting format                                        |
| Olympus `.oif` channels incorrect               | Known limitation: reassign LUTs manually or use Custom color mode with RGB values                  |
