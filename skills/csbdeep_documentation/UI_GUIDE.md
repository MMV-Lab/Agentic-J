# CSBDeep UI Guide

## Installation

1. Open `Help > Update...`
2. Click `Manage update sites`
3. Enable `CSBDeep`
4. Apply changes and restart Fiji
5. If inference fails, inspect `Edit > Options > TensorFlow...`

## Verified Menu Paths

These menu paths are present in the plugin metadata and source code:

- `Plugins > CSBDeep > Run your network`
- `Plugins > CSBDeep > Run your IsoNet`
- `Plugins > CSBDeep > Demo > 3D Denoising - Tribolium`
- `Plugins > CSBDeep > Demo > 3D Denoising - Planaria`
- `Plugins > CSBDeep > Demo > Deconvolution - Microtubules`
- `Plugins > CSBDeep > Demo > Surface Projection - Flywing`
- `Plugins > CSBDeep > Demo > Isotropic Reconstruction - Retina`
- `Edit > Options > TensorFlow...`

## Generic Dialog Controls

The `Run your network` dialog exposes the same fields as the `GenericNetwork` command:

- input image
- input normalization toggle
- lower and upper normalization percentiles
- clip normalization
- number of tiles
- tile-size multiple
- overlap between tiles
- batch size
- model ZIP file
- model ZIP URL
- TensorFlow input mapping button
- progress dialog toggle

The `Run your IsoNet` dialog adds:

- scale factor of Z-axis

## Demo Dialog Controls

The demo wrappers expose a smaller subset:

- `NetTribolium` and `NetPlanaria`: number of tiles, progress dialog
- `NetTubulin`: number of tiles, batch size, progress dialog
- `NetProject`: number of tiles, progress dialog
- `NetIso`: number of tiles, Z scale factor, batch size, progress dialog

## When To Use Which Command

| Command | Choose it when |
|---------|----------------|
| `Run your network` | You have your own exported model ZIP or a direct model ZIP URL |
| `Run your IsoNet` | You have an anisotropic 3D stack and a model meant for isotropic reconstruction |
| Demo wrappers | You want to test the plugin installation or inspect a canned example model |

## Scope Notes

- Use the base CSBDeep menus in this guide for CARE-style image restoration.
- Use separate workflows for `StarDist`, `N2V`, and `DenoiSeg`.
- In this repo's container, both the Tribolium demo path and the generic restoration path produce output datasets under headless validation.
