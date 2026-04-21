# OrientationJ - UI Guide

This guide keeps to the OrientationJ menu surface that is either documented on the official EPFL page or confirmed in the current source tree.

## Installation

Install OrientationJ from the BIG-EPFL update site:

1. Open `Help > Update...`
2. Click `Manage update sites`
3. Enable `BIG-EPFL`
4. Close the update-site dialog
5. Click `Apply changes`
6. Restart Fiji after the downloads finish

Manual install from the official EPFL page is also supported by placing `OrientationJ_.jar` into Fiji's `plugins` directory.

## Menu Layout

Source menu path:

- `Plugins > OrientationJ > OrientationJ Analysis`
- `Plugins > OrientationJ > OrientationJ Distribution`
- `Plugins > OrientationJ > OrientationJ Directions`
- `Plugins > OrientationJ > OrientationJ Measure`
- `Plugins > OrientationJ > OrientationJ Corner Harris`
- `Plugins > OrientationJ > OrientationJ Dominant Direction`
- `Plugins > OrientationJ > OrientationJ Vector Field`
- `Plugins > OrientationJ > OrientationJ Test Image`

This skill documents the validated surfaces for Analysis, Distribution, Vector Field, Corner Harris, and Dominant Direction. `OrientationJ Measure` is documented as a manual ROI-driven tool. `OrientationJ Directions` was not validated in this repo pass.

## Input Requirements

Common requirement from the source and validated pass:

- open image must be active
- image must be grayscale
- supported bit depths are `8-bit`, `16-bit`, or `32-bit`

Practical note:

- the validated repo workflow used a single-slice TIFF
- Distribution, Vector Field, and Dominant Direction can also produce per-slice outputs for stack inputs

## Analysis

Menu path: `Plugins > OrientationJ > OrientationJ Analysis`

Documented purpose on the EPFL page:

- compute local orientation properties from the structure tensor
- display orientation, coherency, energy, and color survey outputs

Source-confirmed controls:

- `Local window sigma`
- `Gradient`
- `Orientation unit`: `rad` or `deg`
- feature checkboxes for:
  - `Gradient-X`
  - `Gradient-Y`
  - `Energy`
  - `Orientation`
  - `Coherency`
  - `Color-survey`
- color-space choice: `HSB` or `RGB`
- survey channel selectors for hue/red, saturation/green, and brightness/blue

Source-confirmed survey channel choices:

- `Gradient-X`
- `Gradient-Y`
- `Orientation`
- `Coherency`
- `Energy`
- `Constant`
- `Original-Image`

Expected outputs:

- color survey image
- orientation image
- coherency image
- energy image

## Distribution

Menu path: `Plugins > OrientationJ > OrientationJ Distribution`

Documented purpose on the EPFL page:

- build an orientation histogram from pixels that pass `min-coherency` and `min-energy`

Documented threshold meaning on the EPFL page:

- `min-coherency` is a percentage because coherency ranges from `0` to `1`
- `min-energy` is a percentage of the image's maximum energy

Source-confirmed controls:

- `Min. Coherency`
- `Min. Energy`
- feature checkboxes for:
  - `Binary Mask`
  - `Orientation Mask`
  - `Histogram`
  - `Table`

Expected outputs:

- histogram plot window
- distribution table
- optional selected-mask windows according to the UI and source surface

Practical note from the validated repo pass:

- histogram plot and distribution table were exported successfully through `IJ.run(...)`
- separate `Binary Mask` and `Orientation Mask` windows were not observed through the validated Groovy launcher path

## Vector Field

Menu path: `Plugins > OrientationJ > OrientationJ Vector Field`

Documented purpose on the EPFL page:

- evaluate direction on regular image patches and visualize vectors

Source-confirmed controls:

- `Grid size`
- `Length vector`
- `Scale vector (%)`
- `Show Table`
- `Overlay`

Source-confirmed vector-length choices:

- `Maximum`
- `~ Energy`
- `~ Coherency`
- `~ Ene. x Coh.`

Expected outputs:

- vector table
- overlay on the active image

## Corner Harris

Menu path: `Plugins > OrientationJ > OrientationJ Corner Harris`

Documented purpose on the EPFL page:

- compute the Harris index and detect local maxima as corners

Source-confirmed controls:

- `Harris-index`
- `k`
- `Window size`
- `Min. level`
- `Show Table`
- `Overlay`

Expected outputs:

- Harris index image
- corner table
- overlay on the active image

## Dominant Direction

Menu path from source: `Plugins > OrientationJ > OrientationJ Dominant Direction`

Documented purpose in source and README:

- compute one dominant orientation and coherency per slice

Expected output in the validated repo pass:

- results table with `Slice`, `Orientation [Degrees]`, and `Coherency [%]`

## Measure

Menu path: `Plugins > OrientationJ > OrientationJ Measure`

Documented purpose on the EPFL page:

- measure orientation and coherency inside user-defined ROIs

Source-confirmed behavior:

- requires an active grayscale image
- uses the current ROI
- optional `sigma` parameter applies a Laplacian-of-Gaussian prefilter
- writes tab-separated measurements to the ImageJ log

This skill treats `Measure` as UI-first because ROI placement is interactive.

## Test Image

Menu path: `Plugins > OrientationJ > OrientationJ Test Image`

Purpose:

- create synthetic chirp or stack test images for demos and method checks

This skill does not use the synthetic test image as its validation artifact because the checked-in workflow was verified on a real repo image.
