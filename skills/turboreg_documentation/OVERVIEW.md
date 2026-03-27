# TurboReg — Overview

## What TurboReg Does

TurboReg is an ImageJ plugin from the Biomedical Imaging Group (BIG) at EPFL
that automatically aligns (registers) a **source** image or stack to a
**target** image. It uses a pyramid-based intensity optimisation approach to
find the transformation that minimises the mean-square difference between the
warped source and the target. Sub-pixel accuracy is achieved through cubic-spline
interpolation and multi-resolution refinement.

**Author:** Philippe Thévenaz, EPFL BIG
**Publication:** Thévenaz P, Ruttimann UE, Unser M. "A Pyramid Approach to
Subpixel Registration Based on Intensity." IEEE Transactions on Image Processing,
vol. 7, no. 1, pp. 27–41, January 1998.
https://bigwww.epfl.ch/thevenaz/turboreg/

---

## Key Capabilities

| Capability | Details |
|---|---|
| Transformation types | Translation, Rigid Body, Scaled Rotation, Affine, Bilinear |
| Registration modes | Manual, Automatic, Batch |
| Image types | Grayscale (8/16/32-bit), RGB stacks |
| Masking | Optional second-slice mask in grayscale stacks |
| Batch mode | Register every slice of a source stack to a single target |
| Sub-pixel accuracy | Cubic-spline interpolation (Accurate mode) |
| Scripting | Callable from IJ Macro and Groovy via `IJ.run("TurboReg ", "...")` |
| Plugin-to-plugin | Callable from another plugin; results retrievable programmatically |
| Companion plugin | StackReg — sequential slice-to-slice alignment within a stack |

---

## Five Transformation Types

| Type | Description | Landmarks needed | Degrees of freedom |
|---|---|---|---|
| **Translation** | Pure shift, no rotation or scaling | 1 per image | 2 (Δx, Δy) |
| **Rigid Body** | Translation + rotation, no scale change | 3 per image (1 for translation, 2 for angle) | 3 (Δx, Δy, θ) |
| **Scaled Rotation** | Translation + rotation + isotropic scale | 2 per image | 4 |
| **Affine** | Translation + rotation + shear + anisotropic scale | 3 per image | 6 |
| **Bilinear** | Curved mapping (straight lines → conic sections) | 4 per image | 8 |

---

## Three Operating Modes

| Mode | Description |
|---|---|
| **Manual** | User sets landmarks; no automatic refinement. Useful when automatic mode fails or when landmarks are known precisely. |
| **Automatic** | Landmarks are refined automatically to minimise mean-square error. Quality can be set to Fast (nearest-neighbour) or Accurate (cubic spline). Most common mode. |
| **Batch** | Source must be a stack; each slice is registered in turn to the same target. Output is a registered stack. Not available for RGB stacks. |

---

## Input and Output Types

| Situation | Input | Output |
|---|---|---|
| Grayscale single image | 8/16/32-bit ImagePlus | Float 32-bit registered image (+ mask slice) |
| RGB stack | RGB ImagePlus | RGB registered image (no mask support) |
| Batch (grayscale stack) | Stack of grayscale slices | Float 32-bit registered stack |
| With mask | 2-slice stack (image + mask) | Registered image + warped mask |

**Output is always float 32-bit** in automatic and batch modes.

---

## Masking

If the source or target is a two-slice grayscale stack, the second slice acts
as a registration mask:
- Pixels with value `0` in the second slice are **excluded** from registration
- Pixels with non-zero values in both source and target masks are **included**
- The mask is warped with nearest-neighbour interpolation and returned as the
  second slice of the output

RGB stacks do not support masking.

---

## Critical Scripting Notes

1. **The command name has a trailing space:** `IJ.run("TurboReg ", "...")`.
   Without the space, the plugin is not found and the call silently fails.
2. **TurboReg is NOT macro-recordable.** The parameter string must be written
   manually or copied from the official documentation/examples.
3. **`-window` takes the image title** (as a quoted string) or the numeric
   window ID — not the variable name.
4. **Default landmark positions** should be image-centred for translation;
   for other types use positions that span the image (see GROOVY_SCRIPT_API.md).

---

## Practical tip: phase images and edge-localised samples

If your sample is mostly on the **edge** of the field of view (large empty background elsewhere), TurboReg may converge to the identity transform or produce unstable fits.

Two robust improvements:

1) **Register on an edge-enhanced copy** (recommended)
- Build a temporary registration image (do not overwrite your raw data)
- Convert to 8-bit and apply an edge-emphasis filter such as *Difference-of-Gaussians (DoG)* (or *Process › Find Edges*)
- Run TurboReg on these enhanced images to give the optimiser strong features to lock onto

2) **Move landmarks toward the borders**
- For `rigidBody` / `affine`, prefer landmarks near corners/edges (inset ~10%) instead of centred landmarks.

---

## Installation

### Via Fiji Update Sites (recommended)

1. **Help › Update…**
2. Click **Manage Update Sites**
3. Tick **BIG-EPFL**
4. Click **Close → Apply Changes → Restart Fiji**

TurboReg will then be available under **Plugins › Registration › TurboReg**.

### Manual installation

Download from https://bigwww.epfl.ch/thevenaz/turboreg/turboreg.zip and place
`TurboReg_.class` (or the JAR) in Fiji's `plugins/` folder, then restart.

---

## Related Plugins

| Plugin | Purpose |
|---|---|
| **StackReg** | Sequential slice-to-slice alignment within a single stack. Uses TurboReg internally. |
| **MultiStackReg** | Registers one stack using the registration computed from another stack. Uses TurboReg as backend. |

---

## Conditions of Use

TurboReg is free for research use. It must not be redistributed without consent
of EPFL. Any publication using TurboReg must cite the Thévenaz 1998 paper.
