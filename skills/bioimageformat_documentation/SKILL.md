---
name: bioimageformat_documentation
description: Bio-Formats is a Fiji plugin for **reading and writing microscopy image formats**. 
 Reads and writes **150+ proprietary microscopy image formats** (.czi, .nd2, .lif, .oif,
 .ims, .stk, …) and converts them to open formats, primarily OME-TIFF. Preserves full
 acquisition metadata via the OME data model. The definitive tool for opening files from
 Zeiss, Nikon, Leica, Olympus, Olympus, PerkinElmer, and many others in Fiji/ImageJ. Read the files listed at the end of this SKILL for verified commands, GUI walkthroughs, scripting examples, and common pitfalls. 
---


# Bio-Formats — Agent Skill Reference

## Identity

| Property          | Value                                                                     |
|-------------------|---------------------------------------------------------------------------|
| Plugin name       | Bio-Formats                                                               |
| Fiji menu path    | Plugins › Bio-Formats › …                                                 |
| Version (current) | 8.4.0 (released 2026-01-14)                                               |
| Bundled with Fiji | Yes — included by default; update via Help › Update › Manage Update Sites |
| License           | GNU GPL v2                                                                |
| DOI               | https://doi.org/10.1083/jcb.201004104                                     |

## What it does

Reads and writes **150+ proprietary microscopy image formats** (.czi, .nd2, .lif, .oif,
.ims, .stk, …) and converts them to open formats, primarily OME-TIFF. Preserves full
acquisition metadata via the OME data model. The definitive tool for opening files from
Zeiss, Nikon, Leica, Olympus, Olympus, PerkinElmer, and many others in Fiji/ImageJ.

---

## Three Automation Pathways — Choose the Right One

| Pathway | When to use | Language |
|---------|-------------|----------|
| **IJ Macro** (`IJ.run`) | Simple scripts inside Fiji; recording macros | ImageJ Macro |
| **Groovy API** (`BF.openImagePlus`) | Complex scripts inside Fiji; series selection; virtual stacks | Groovy / Java |

> **Headless warning**: Bio-Formats does NOT work with Fiji's `--headless` flag.
> Use ImageJ Launcher with `-batch` flag for macro-based headless execution.

---

## IJ Macro Quick Reference

```javascript
// Minimum working call (fluorescence)
run("Bio-Formats Importer",
    "open=/path/to/file.czi autoscale color_mode=Composite view=Hyperstack stack_order=XYCZT");

// Batch loop — suppress dialog with windowless=true
for (i = 0; i < list.length; i++) {
    run("Bio-Formats Importer",
        "open=[" + inputDir + list[i] + "] autoscale color_mode=Composite " +
        "view=Hyperstack stack_order=XYCZT windowless=true");
}
```

Key parameters: `open=` · `autoscale` · `color_mode=` · `view=` · `stack_order=` ·
`split_channels` · `split_z` · `split_timepoints` · `open_all_series` · `virtual` ·
`windowless=true` · `rois_import=[ROI manager]`

Paths with spaces → wrap in `[square brackets]`.

---

## Groovy API Quick Reference

```groovy
import loci.plugins.BF
import loci.plugins.in.ImporterOptions

// Minimal
def imps = BF.openImagePlus("/path/to/file.czi")  // returns ImagePlus[]
imps.each { it.show() }

// With options
def opts = new ImporterOptions()
opts.setId("/path/to/file.czi")
opts.setAutoscale(true)
opts.setColorMode(ImporterOptions.COLOR_MODE_COMPOSITE)
opts.setOpenAllSeries(true)
opts.setWindowless(true)
opts.setQuiet(true)
def imps = BF.openImagePlus(opts)      // always an array
imps.each { it.show() }
```

Color mode constants: `COLOR_MODE_DEFAULT` · `COLOR_MODE_COMPOSITE` ·
`COLOR_MODE_COLORIZED` · `COLOR_MODE_GRAYSCALE` · `COLOR_MODE_CUSTOM`

Series selection: `opts.clearSeries(); opts.setSeriesOn(N, true)`

Crop: `opts.setCrop(true); opts.setCropRegion(0, new loci.common.Region(x, y, w, h))`

Virtual stack: `opts.setVirtual(true)`


---

## Critical Pitfalls

1. **`--headless` does not work with Fiji macros** — produces `VerifyError`.
   Use ImageJ Launcher `-batch` flag instead.

2. **`BF.openImagePlus()` returns `ImagePlus[]`** — always an array, never a
   single `ImagePlus`. Must iterate: `imps.each { it.show() }`.

3. **Series indices are 0-based** — both in the Java API and in all bftools flags.

4. **`File › Save As…` TIFF does NOT use Bio-Formats** — writes an ImageJ TIFF,
   not OME-TIFF. Use `Plugins › Bio-Formats › Bio-Formats Exporter` to write OME-TIFF.

5. **Windowless Importer uses last-saved settings per format** — if calling
   `windowless=true` in a macro for a format you have never opened manually before,
   the defaults may be wrong. Always run the format manually once first.

6. **Always use `-no-upgrade` in scripts** — omitting it causes bftools to contact
   `upgrade.openmicroscopy.org.uk` and may abort with an `IOException` on offline
   or restricted networks.

7. **Paths with spaces in macros** → wrap the path in `[square brackets]`:
   `open=[/data/my folder/file.nd2]`

---

## Output Format Decision Guide

| Goal                          | Extension to use               |
|-------------------------------|-------------------------------|
| Standard OME-TIFF             | `.ome.tiff`                   |
| OME-TIFF > 4 GB               | `.ome.btf` or `-bigtiff`      |
| Plain TIFF for compatibility  | `.tiff`                       |
| Lossless, small file          | `.ome.tiff` + `-compression LZW` |
| Multi-resolution pyramid      | `.ome.tiff` + `-noflat -pyramid-resolutions N -pyramid-scale 2` |

---

## Supported Formats Highlights

Input: Zeiss `.czi`/`.lsm`/`.zvi` · Nikon `.nd2`/`.nd` · Leica `.lif`/`.lof` ·
Olympus `.oif`/`.oib` · PerkinElmer `.flex` · Metamorph `.stk` · Imaris `.ims` ·
TIFF · OME-TIFF · DICOM (microscopy) · 150+ formats total.

Output: OME-TIFF · TIFF · BigTIFF · PNG · JPEG · JPEG-2000 · AVI · QuickTime ·
EPS · ICS · OME-XML · CellH5.

Full list: https://bio-formats.readthedocs.io/en/v8.4.0/supported-formats.html

---

## File Inventory

| File                                 | Contents                                                              |
|--------------------------------------|-----------------------------------------------------------------------|
| `OVERVIEW.md`                        | Plugin description, use cases, architecture, installation             |
| `UI_GUIDE.md`                        | Every Import Options dialog parameter and value                       |
| `GROOVY_SCRIPT_API.md`               | Full Groovy/Java API (`BF`, `ImporterOptions`) + IJ Macro reference   |
| `WORKFLOW_BATCH_CONVERT.groovy`      | Ready-to-use Groovy batch conversion script (runs in Fiji Script Editor) |
| `SKILL.md`                           | This quick-reference card                                             |
| `UI_WORKFLOW.md`                     | Step-by-step GUI walkthrough: import, multi-series, export, config    |
