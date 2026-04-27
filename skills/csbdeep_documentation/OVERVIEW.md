# CSBDeep Overview

## What This Skill Covers

This skill covers the base CSBDeep Fiji plugin exposed under `Plugins > CSBDeep`:

- `Run your network`
- `Run your IsoNet`
- the built-in demo wrappers for Tribolium, Planaria, Microtubules, Flywing projection, and Retina IsoNet

It does not cover the related `StarDist`, `N2V`, or `DenoiSeg` workflows beyond noting that they are distributed from the same update site family.

## Typical Inputs And Use Cases

| Mode | Typical input | Typical use |
|------|---------------|-------------|
| `GenericNetwork` | 2D or 3D image compatible with the exported model ZIP | CARE-style denoising, restoration, or other model-specific image-to-image prediction |
| `GenericIsotropicNetwork` | Anisotropic 3D stack with coarse Z sampling | Isotropic reconstruction with a model that expects the IsoNet rotation / merge pipeline |
| `NetTribolium` / `NetPlanaria` | Demo-friendly 2D or 3D grayscale image | Quick installation check or denoising demo |
| `NetTubulin` | 2D or 3D image compatible with the demo model | Microtubule deconvolution demo |
| `NetProject` | 3D grayscale X-Y-Z stack | Surface projection demo |
| `NetIso` | 3D anisotropic stack | Retina isotropic reconstruction demo |

## Input Image Requirements

| Command | Input requirements |
|---------|--------------------|
| `GenericNetwork` | The dataset shape must match the exported model's expected input tensor after CSBDeep dimension mapping |
| `GenericIsotropicNetwork` | Input must be a stack with a meaningful Z axis; the command rotates and upsamples along Z before inference |
| `NetTribolium` | Source tests accept XY and XYZ inputs; channel / time layouts outside the model shape are rejected |
| `NetPlanaria` | Source tests accept XY and XYZ inputs; use grayscale image data |
| `NetTubulin` | Source tests cover XY and XYZ inputs |
| `NetProject` | Source code validates for a 3D grayscale X-Y-Z image |
| `NetIso` | Use anisotropic 3D data and set the Z scale factor to the physical anisotropy |

## Output Types

| Command family | Output type |
|----------------|-------------|
| `GenericNetwork` and demo wrappers | One `Dataset` named `output` |
| `GenericIsotropicNetwork` and `NetIso` | One merged isotropic `Dataset` named `output` |

For the demo wrappers, upstream tests expect the output spatial axes to match the input after singleton dimensions are handled. Some probabilistic demo networks can expand the channel dimension.

## Automation Level

CSBDeep is scriptable through SciJava command classes and `CommandService`. The base plugin is not documented here as an `IJ.run(...)` macro surface. For this skill, treat the Groovy / SciJava path as the authoritative automation interface.

## Installation

1. Open `Help > Update...`
2. Click `Manage update sites`
3. Enable `CSBDeep`
4. Apply changes and restart Fiji
5. If model execution still fails, inspect `Edit > Options > TensorFlow...` and select a TensorFlow runtime compatible with the models you need

## Known Limitations

- The base CARE commands in this skill are documented as SciJava command classes, not macro strings.
- `GenericNetwork` requires a compatible exported CSBDeep SavedModel ZIP or a model URL that points to one.
- `GenericIsotropicNetwork` is a specialized path for anisotropic Z restoration; it is not a drop-in replacement for every generic model.
- In this repo's current Fiji container, `NetTribolium` and `GenericNetwork` both produce non-null output datasets under headless validation.
- `fiji-linux-x64 --headless --run ...` works for CSBDeep scripts in this container, but file and string arguments must be quoted inside the parameter list.
- `StarDist`, `N2V`, and `DenoiSeg` are related CSBDeep-family plugins but are not documented by this skill.

## Citation And Links

- CSBDeep Fiji plugin page: `https://imagej.net/plugins/csbdeep`
- CARE Fiji page: `https://imagej.net/plugins/care`
- Source repository: `https://github.com/CSBDeep/CSBDeep_fiji`
- CSBDeep project site: `https://csbdeep.bioimagecomputing.com/`
- Suggested scientific citation: Martin Weigert et al., *Content-Aware Image Restoration: Pushing the Limits of Fluorescence Microscopy*, Nature Methods 15(12), 2018
