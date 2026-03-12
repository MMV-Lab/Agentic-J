# BigStitcher — Overview

BigStitcher is a Fiji plugin for reconstructing very large tiled and multi-view microscopy datasets (especially light-sheet datasets) into a globally aligned volume. It supports stitching tiles, registering multiple acquisition angles/timepoints, and exporting fused outputs for downstream analysis. It is designed to handle datasets from small examples up to terabyte scale through BigDataViewer-backed storage.

## Typical inputs
- Multi-tile microscopy images (2D or 3D), often TIFF or Bio-Formats-readable files
- Multi-channel, multi-angle, multi-timepoint acquisitions
- Optional existing BigStitcher/BigDataViewer project XML

## Typical outputs
- BigStitcher project metadata (`.xml` + associated data)
- Pairwise shift and global optimization alignment state
- Fused image outputs (e.g., TIFF stacks)
- Optional deconvolved/further refined reconstructions

## Automation in Groovy
**PARTIALLY**

Evidence shows macro-recordable/batch-processing commands are available and can be called from scripts via `run("...")`/`IJ.run(...)`. However, BigStitcher is a multi-step workflow and many options are dataset-specific; practical automation usually requires recording commands first and adapting parameters.

## Installation required
`BigStitcher` is **not installed** in the current environment (checked via plugin directory scan). Install via:
- `Help > Update... > Manage update sites > BigStitcher` (enable), then restart Fiji.

## Known limitations / unsupported cases
- Headless macros are sensitive to exact parameter strings and file patterns.
- Some advanced steps are spread between **Plugins > BigStitcher > Batch Processing** and **Plugins > Multiview Reconstruction > Batch Processing**.
- Not all GUI interactions are equally convenient in headless mode; manual QC is still important.

## Citation
- Hörl D, Rojas Rusak F, Preusser F, et al. **BigStitcher: reconstructing high-resolution image datasets of cleared and expanded samples.** *Nature Methods* (2019). DOI: `10.1038/s41592-019-0501-0`

## Evidence sources
- https://imagej.net/plugins/bigstitcher/
- https://imagej.net/plugins/bigstitcher/headless
- https://github.com/JaneliaSciComp/BigStitcher
