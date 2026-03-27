# Bio-Formats — GUI Workflow: Importing and Exporting Microscopy Files

This walkthrough guides you through three common Bio-Formats workflows in the Fiji
GUI: opening a proprietary microscopy file with full metadata, navigating a
multi-series file, and exporting to OME-TIFF. Each section is self-contained.

---

## Before You Start — Checklist

- [ ] Fiji is installed and up to date (Bio-Formats is bundled by default)
- [ ] To verify Bio-Formats is present: **Plugins › Bio-Formats** should appear in the menu
- [ ] To update Bio-Formats to the latest release:
  1. **Help › Update…**
  2. Click **Manage Update Sites**
  3. Tick the **Bio-Formats** checkbox
  4. **Close → Apply Changes → Restart Fiji**
- [ ] You know whether your file contains multiple series (e.g. a Leica `.lif` with
  multiple acquisitions, or a Nikon `.nd2` with multiple fields)
- [ ] For large files (> 2 GB): check available RAM via **Edit › Options › Memory & Threads**

---

## Workflow A — Opening a Single Proprietary File

This is the standard path for opening a `.czi`, `.nd2`, `.oif`, `.lsm`, or similar file.

### Step 1 — Open the Bio-Formats Importer

There are two equivalent ways:

- **Option 1**: **Plugins › Bio-Formats › Bio-Formats Importer** → navigate to your file and click Open
- **Option 2**: **File › Open** → navigate to your file and click Open (Fiji delegates automatically to Bio-Formats if the format is not handled by another plugin)

> **How to tell Bio-Formats handled it**: if the Bio-Formats Import Options dialog
> appears, Bio-Formats is processing the file. If no dialog appears and the image
> opens directly, a different plugin handled it (common for plain TIFFs).

---

### Step 2 — The Import Options Dialog

The **Bio-Formats Import Options** dialog appears. Review the sections below and
adjust settings to match your data type and goal.

---

### Step 3 — Set the Color Mode

The **Color Mode** dropdown controls how channels are represented:

| Color Mode  | When to use                                                                       |
|-------------|-----------------------------------------------------------------------------------|
| `Default`   | Let Bio-Formats use whatever mode it last used for this format                   |
| `Composite` | **Recommended for multi-channel fluorescence**: opens all channels as a composite hyperstack with independent LUTs |
| `Colorized`  | Pseudo-colours each channel using the LUT metadata stored in the file            |
| `Grayscale` | All channels are displayed in grayscale; useful for quantitative work            |
| `Custom`    | Manually assign RGB values per channel after import                               |

**For fluorescence microscopy (most common case):** select **Composite**.

---

### Step 4 — Set the View Format

The **View Stack With** dropdown controls how the multi-dimensional data is
arranged in Fiji:

- **Hyperstack** — opens with independent C, Z, and T sliders (recommended)
- **Standard ImageJ** — flattened linear stack; use only if a downstream plugin
  requires a flat stack

Leave **Stack order** at `XYCZT` unless you have a specific reason to change it.
This is the standard order for fluorescence microscopy (channels iterate fastest,
then Z, then T).

---

### Step 5 — Memory and Virtual Stack

For very large files (whole-slide images, long time series):

- Tick **Open as virtual stack** — planes are loaded from disk on demand rather
  than all at once. The image is read-only in virtual mode.
- Alternatively, increase maximum memory: **Edit › Options › Memory & Threads**
  and restart Fiji.

---

### Step 6 — Metadata Options (Optional)

| Option                  | When to use                                                                    |
|-------------------------|--------------------------------------------------------------------------------|
| **Display metadata**    | Tick to open a Results window listing all key/value acquisition metadata       |
| **Show OME-XML**        | Tick to display the full OME-XML document (useful for debugging metadata)       |
| **Show ROIs**           | Tick if the file contains embedded ROI annotations you want to import          |
| **ROIs import mode**    | Choose **ROI manager** to load ROIs into the ROI Manager, or **Overlay** to display them on the image |

---

### Step 7 — Other Import Options

| Option                        | When to use                                                                       |
|-------------------------------|-----------------------------------------------------------------------------------|
| **Autoscale**                 | Tick to auto-set display range to min/max pixel values in the dataset (display only, does not alter pixel values) |
| **Split channels**            | Opens each channel as a separate ImagePlus window instead of a composite stack    |
| **Split focal planes**        | Opens each Z section as a separate ImagePlus window                               |
| **Split timepoints**          | Opens each timepoint as a separate ImagePlus window                               |
| **Group files with similar names** | If your acquisition saved each channel as a separate file (e.g. `img_C00.tif`, `img_C01.tif`), tick this to group them |
| **Crop on import**            | Specify X, Y, width, height to import only a region (useful for very large images)|
| **Specify ranges**            | Specify begin/step/end for Z, C, and T to import a subset of planes               |

---

### Step 8 — Click OK

Click **OK** to start the import. Bio-Formats reads the file, sets pixel
calibration (µm/pixel) and channel names from the metadata, and opens the image
as a hyperstack.

**Check after opening:**
- Window title shows the filename and series name
- Pixel size is set: **Image › Properties…** should show µm values, not "pixels"
- Channel count, Z count, T count shown in the title bar match the expected
  acquisition dimensions

---

### Step 9 — Inspect the Image

- Use the **C / Z / T sliders** at the bottom of the hyperstack window to navigate
- Toggle composite channels via the checkboxes at the bottom (each channel has its own LUT)
- View channel metadata: **Image › Show Info…** (`Ctrl+I`)
- View pixel calibration: **Image › Properties…** (`Ctrl+Shift+P`)

---

## Workflow B — Opening a Multi-Series File (e.g. Leica .lif)

Multi-series files contain multiple independent acquisitions in a single file.
Common examples: Leica `.lif`, `.lof`; some Nikon `.nd2`; Olympus `.oib`.

### Step 1 — Open the Importer

**Plugins › Bio-Formats › Bio-Formats Importer** → select the file.

---

### Step 2 — Import Options Dialog

Set Color Mode, View, and other options as in Workflow A (Step 3–7). Then click **OK**.

---

### Step 3 — Series Options Dialog

A second dialog appears: **Bio-Formats Series Options**. It shows every series in
the file with a thumbnail, name, and dimensions.

| What you see                  | What to do                                                           |
|-------------------------------|----------------------------------------------------------------------|
| A list of named series        | Tick only the series you want to open                                |
| Thumbnails are blank          | Normal — thumbnails may not render for all formats                   |
| Hundreds of series (e.g. HCS) | Use **Open all series** in the Import Options dialog instead of selecting manually |

Select the series you want and click **OK**. Each selected series opens as a
separate image window.

---

### Step 4 — Open All Series at Once (Alternative)

To skip the Series Options dialog and open every series automatically:

1. In the **Import Options** dialog (Step 2), tick **Open all series**
2. Click **OK** — all series open simultaneously without further prompting

---

### Step 5 — Identify Which Series is Which

When many series are open, use **Window** menu to switch between them. Series names
come from the file metadata (e.g. the experiment/acquisition name you gave in the
microscope software). The title bar of each window shows the series name.

---

## Workflow C — Exporting to OME-TIFF

> **Important**: `File › Save As › Tiff…` does NOT produce OME-TIFF. It writes an
> ImageJ-specific TIFF that strips acquisition metadata. To preserve metadata in a
> portable open format, always use the Bio-Formats Exporter.

### Step 1 — Prepare the Image

Make sure the image you want to export is the active window.

---

### Step 2 — Open the Bio-Formats Exporter

**Plugins › Bio-Formats › Bio-Formats Exporter**

---

### Step 3 — Choose the Output File

In the save dialog, type the output filename with the appropriate extension.
The extension determines the output format:

| Goal                                      | Extension to type                   |
|-------------------------------------------|-------------------------------------|
| Standard OME-TIFF (≤ 4 GB)               | `experiment.ome.tiff`               |
| OME-TIFF for large files (> 4 GB)        | `experiment.ome.btf`                |
| Plain TIFF (no OME metadata)             | `experiment.tiff`                   |
| JPEG (lossy)                             | `experiment.jpg`                    |
| PNG                                      | `experiment.png`                    |

Click **Save**.

---

### Step 4 — Verify the Output

Open the saved file back in Fiji to verify:

1. **File › Open** → select your `.ome.tiff`
2. The Import Options dialog should appear (confirming Bio-Formats is reading it)
3. Check **Image › Properties…** — pixel calibration should be preserved
4. Check **Image › Show Info…** — acquisition metadata should be present

Alternatively, use `showinf` from bftools on the command line to inspect the
metadata without opening the full image:
```
showinf -nopix -no-upgrade /path/to/experiment.ome.tiff
```

---

## Workflow D — Configuring Bio-Formats Plugin Behaviour

Use this when a file is opening incorrectly or you want to suppress the Import
Options dialog for a specific format.

### Step 1 — Open the Configuration Dialog

**Plugins › Bio-Formats › Bio-Formats Plugins Configuration**

---

### Step 2 — Formats Tab

- **Disable a format**: if a file is being detected as the wrong format, find the
  incorrect format in the list and untick its **Enabled** checkbox. Bio-Formats
  will then fall through to the next matching reader.
- **Enable Windowless for a format**: tick the **Windowless** checkbox next to a
  format to suppress the Import Options dialog for that format — it will use the
  last-saved settings silently. Useful for formats you always open with the same
  settings.

---

### Step 3 — General Tab

Configure the **Slice label pattern** — the text displayed on each slice in the
image window. Available tokens:

| Token | Meaning                  |
|-------|--------------------------|
| `%s`  | Series index (1-based)   |
| `%n`  | Series name              |
| `%c`  | Channel index (1-based)  |
| `%w`  | Channel name             |
| `%z`  | Z index (1-based)        |
| `%t`  | T index (1-based)        |
| `%A`  | Acquisition timestamp    |

Example pattern: `%n - z%z c%w t%t` produces labels like `DAPI - z3 cDAPI t1`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Import Options dialog does not appear | Format is set to Windowless in the Configuration dialog, or another plugin handled the file | Check Formats tab in Configuration; disable Windowless for this format |
| Multi-channel image opens as a flat grayscale stack | Color Mode was left as `Default` with a format that previously used Grayscale | Re-open with Color Mode = Composite |
| Pixel calibration shows "pixels" instead of µm | File metadata does not contain pixel size information | Set manually via Image › Properties… |
| Memory error on a large file | Not enough RAM loaded at once | Enable **Open as virtual stack**; increase heap in Edit › Options › Memory & Threads |
| File opens but all channels are white or black | Autoscale was not ticked, and pixel values are outside the default 0–255 display range | Tick Autoscale on import, or adjust display range with Image › Adjust › Brightness/Contrast |
| Wrong series opens for a multi-series file | Only one series was selected in the Series Options dialog | Re-open and tick the correct series, or tick Open all series |
| Saving as `.tiff` strips the metadata | Used File › Save As instead of Bio-Formats Exporter | Re-open original file and use Plugins › Bio-Formats › Bio-Formats Exporter with `.ome.tiff` extension |
| `VerifyError` when running Bio-Formats from the command line | Fiji was launched with `--headless` flag | Use ImageJ Launcher with `-batch` flag instead: `./ImageJ-linux64 -macro myMacro.ijm -batch` |
