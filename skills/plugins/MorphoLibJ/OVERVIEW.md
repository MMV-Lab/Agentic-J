# MorphoLibJ — OVERVIEW

## What It Does
MorphoLibJ is a comprehensive ImageJ/Fiji library that implements mathematical morphology
operators missing from core ImageJ. It covers morphological filtering (erosion, dilation,
opening, closing, top-hats, gradients), morphological reconstruction (hole filling, border
removal), watershed-based segmentation (classic, marker-controlled, morphological), and
quantitative region analysis (area, perimeter, shape indices, 3D measurements). Originally
designed for plant cell images, the algorithms are fully generic and widely used across
biology and materials science.

## Typical Input Data Types
- 8-bit, 16-bit, or 32-bit grayscale images (planar 2D or 3D stacks)
- Binary images (0/255) for reconstruction, distance transforms, size filters
- Label images (integer-valued) for region analysis and label editing
- RGB images supported for morphological filters only

## Typical Output Data Types
- Filtered grayscale images (same bit-depth as input)
- Binary images (morphological reconstruction, fill holes, kill borders)
- Label images (watershed segmentation, connected component labeling)
- ImageJ ResultsTable (region analysis, intensity measurements, overlap measures)
- Distance maps (16-bit or 32-bit float)

## Automation Level
**YES** — almost all plugins are fully scriptable via IJ.run() macro commands or the
Java/Groovy API (inra.ijpb.*). The Morphological Segmentation plugin uses `call()`
macro extensions. A few interactive plugins (Interactive Marker-controlled Watershed,
Interactive Morphological Reconstruction) require user ROI input and cannot be fully
headless, but offer programmatic equivalents.

## Installation
- **Fiji (recommended):** Help > Update… > Manage update sites > activate **IJPB-plugins** > Apply changes > Restart Fiji.
- **ImageJ (plain):** Download the latest MorphoLibJ JAR from https://github.com/ijpb/MorphoLibJ/releases and drop it into the plugins folder, then restart.
- Update site URL: http://sites.imagej.net/IJPB-plugins/

## Known Limitations
- Distance Transform Watershed (2D) requires an 8-bit binary input image.
- Geodesic diameter uses Chamfer approximation — values may be slightly overestimated.
- Morphological Segmentation GUI is macro-recordable but requires `wait(1000)` after `run("Morphological Segmentation")` before calling `call(...)` commands.
- Label images: byte images support max 255 labels; short images max 65535; 32-bit float images ~16 million.
- 3D plugins generally do not provide a Preview option.
- RGB images: only morphological filters (not segmentation or analysis) accept RGB.

## Citation / DOI
> Legland, D., Arganda-Carreras, I., & Andrey, P. (2016).
> MorphoLibJ: integrated library and plugins for mathematical morphology with ImageJ.
> *Bioinformatics*, 32(22), 3532–3534.
> DOI: 10.1093/bioinformatics/btw413

## Source & Documentation
- Project homepage: http://ijpb.github.io/MorphoLibJ/
- GitHub: http://github.com/ijpb/MorphoLibJ
- JavaDoc: http://ijpb.github.io/MorphoLibJ/javadoc/
- ImageJ wiki: https://imagej.net/plugins/morpholibj
