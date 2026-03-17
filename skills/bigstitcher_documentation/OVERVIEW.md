# BigStitcher — Overview

## What BigStitcher Does

BigStitcher is a Fiji plugin for aligning and fusing multi-tile and multi-angle
3D microscopy datasets of arbitrary size — from small confocal stacks to
multi-terabyte cleared-tissue lightsheet acquisitions. It is the successor to the
ImageJ Stitching plugin and shares the BigDataViewer data model, which allows
interactive navigation of datasets that cannot fit in RAM.

**Publication:** Hörl et al., Nature Methods 2019. https://doi.org/10.1038/s41592-019-0501-0

---

## Key Capabilities

| Capability | Details |
|---|---|
| Tile stitching | Phase-correlation pairwise shifts + global optimization |
| Multi-view registration | Interest-point detection + geometric descriptor matching + global optimization |
| ICP refinement | Affine correction of spherical/chromatic aberrations on top of translation stitching |
| Non-rigid refinement | Per-pixel moving-least-squares deformation after affine registration |
| Illumination selection | Automatic selection of best illumination direction per image block (mean intensity, gradient magnitude, or relative FRC) |
| Flat-field correction | On-the-fly virtual correction using dark/bright reference images |
| Image fusion | Weighted average fusion with cosine blending; supports bounding-box sub-volumes |
| Multiview deconvolution | Richardson-Lucy deconvolution with PSF extraction from bead images; GPU-accelerated |
| Brightness/contrast adjustment | Linear intensity normalization across adjacent tiles for seamless fusion |
| FRC quality control | Per-block relative Fourier Ring Correlation to map image quality spatially |
| Virtual fusion | Stream-and-save pipeline for volumes > available RAM (787 GB fused with 1.25 GB RAM) |

---

## Supported Input Formats

BigStitcher reads data through Bio-Formats and therefore supports virtually all
microscopy formats: Zeiss CZI, Nikon ND2, Leica LIF, Olympus OIF, TIFF stacks,
and many more. Internally, data is represented in the **SpimData XML + HDF5**
(or N5/Zarr) format used by BigDataViewer.

**Preferred internal format for processing:** Multi-resolution blocked HDF5 (`.h5` +
`.xml`). BigStitcher offers to re-save single-block files (TIFF stacks) into this
format on import for best performance.

---

## Dataset Concept: SpimData XML

All BigStitcher state is stored in a single XML project file (`.xml`). This file
records:
- Image file locations (HDF5, N5, TIFF, etc.)
- Voxel size and calibration
- View attributes: Channel, Illumination, Angle, Tile, Timepoint
- All registrations (as a list of affine transform matrices per view)
- Detected interest points, bounding boxes, and PSFs

The XML is human-readable and can be edited in a text editor. BigStitcher
automatically saves previous versions as backups so registration steps can be
manually undone.

---

## Two Operating Modes

BigStitcher runs in two modes depending on dataset type:

| Mode | Use case | Menu |
|---|---|---|
| **Stitching mode** | Multiple tiles from a single angle | Plugins › BigStitcher › BigStitcher |
| **MultiView mode** | Multiple angles / illuminations | Switch via mode selector in the BigStitcher window |

---

## Processing Pipeline (Stitching Mode)

```
1. Define dataset          →  Import tiles; re-save as HDF5 if needed (batch/macro command name is version-dependent; on Fiji 2.16.0/1.54p it records as `Define Multi-View Dataset`)
2. Pre-alignment           →  Move to regular grid OR load tile config file
3. (Optional) Illumination selection  →  Discard inferior illuminations
4. (Optional) Flat-field correction   →  Correct camera offset / uneven illumination
5. Pairwise shift calculation  →  Phase correlation between overlapping tile pairs
6. Filter pairwise shifts      →  Discard links with low correlation coefficient
7. Global optimization         →  Globally consistent registration; 2-round optional
8. (Optional) ICP refinement   →  Affine correction for spherical/chromatic aberration
9. Fusion                      →  Write fused image; TIFF stacks or HDF5
```

---

## Automation Pathways

BigStitcher supports **two levels of automation**:

| Pathway | Description |
|---|---|
| **GUI (interactive)** | Full BigStitcher Stitching Explorer + BigDataViewer; all steps performed via dialogs |
| **IJ.run() in Groovy** | Macro-recordable commands under `Plugins › BigStitcher › Batch Processing`. Each pipeline step is a standard `IJ.run()` call callable from Groovy (or any Fiji scripting language). |

---

## Installation

### Via Fiji Update Sites (recommended)
1. **Help › Update…**
2. Click **Manage Update Sites**
3. Tick **BigStitcher**
4. Click **Close → Apply Changes → Restart Fiji**

BigStitcher will then be available under **Plugins › BigStitcher › BigStitcher**.

---

## Key Limitations

- ICP refinement and non-rigid alignment require interest points to be present
  (detected beforehand via Difference-of-Gaussian filtering)
- Deconvolution requires a PSF — either extracted from sub-diffraction beads
  embedded in the sample or supplied as a TIFF stack
- Multi-view registration (aligning angles) requires switching to MultiView mode;
  stitching and multi-view registration are separate pipeline stages
- Chromatic aberration correction via ICP works only if sufficient autofluorescent
  signal is shared between channels (typically a few pixels of residual error only)
- Virtual blocking (image splitting) is required to push ICP/non-rigid refinement
  below the physical tile scale

---

## Example Datasets (for Testing)

| Dataset | Size | URL |
|---|---|---|
| 2D multi-tile (6 tiles, 3 channels) | 2.8 MB | http://preibischlab.mdc-berlin.de/BigStitcher/Grid_2d.zip |
| 3D multi-tile (6 tiles, 3 channels) | 123 MB | http://preibischlab.mdc-berlin.de/BigStitcher/Grid_3d.zip |
| Larger datasets | Various | https://osf.io/bufza/ |

---

## Citation

Hörl D, Rojas Rusak F, Preusser F, et al. BigStitcher: reconstructing
high-resolution image datasets of cleared and expanded samples.
*Nature Methods* **16**, 870–874 (2019).
https://doi.org/10.1038/s41592-019-0501-0
