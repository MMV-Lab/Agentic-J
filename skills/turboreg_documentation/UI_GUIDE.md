# TurboReg — UI Parameter Guide

## Requirements to Launch

TurboReg requires **at least two images** to be open in ImageJ/Fiji when it is
launched. If fewer than two images are available, TurboReg will display an error
message instead of the dialog.

---

## The TurboReg Dialog

**Menu:** Plugins › Registration › TurboReg

The main dialog contains the following controls:

---

### Source Image

A dropdown listing all currently open images and stacks. The source is the image
that will be moved/warped to match the target.

- If you select the current target as source, TurboReg will reassign the source
  to a different open image automatically (an image cannot be registered to itself).

---

### Target Image

A dropdown listing all currently open images and stacks. The target is the
fixed reference image that the source will be aligned to.

- The output warped image will have the same dimensions as the target.
- If the target is a two-slice grayscale stack, the second slice defines a mask.

---

### Transformation Type

Five options, each unlocking a different number of landmark points:

| Option | Landmarks | Typical use |
|---|---|---|
| **Translation** | 1 | Correcting simple XY drift |
| **Rigid Body** | 3 (1 for translation + 2 for rotation angle) | Correcting drift + rotation with no size change |
| **Scaled Rotation** | 2 | Correcting drift + rotation + uniform zoom |
| **Affine** | 3 | Correcting shear, non-uniform scaling, rotation, and shift |
| **Bilinear** | 4 | Correcting non-linear perspective-like distortion |

Changing the transformation type **resets all landmarks to their default positions**.

---

### Mode Buttons

| Button | Behaviour |
|---|---|
| **Automatic** | Refines the current landmark positions to minimise mean-square error between target and warped source. Use this for standard registration. |
| **Manual** | Applies the transformation based on the current landmark positions as-is, without automatic refinement. |
| **Batch** | Registers every slice of the source stack to the target image in sequence. The source must be a grayscale stack. |

---

### Quality

| Setting | Interpolation | Automatic mode accuracy |
|---|---|---|
| **Fast** | Nearest-neighbour | Coarser landmark refinement |
| **Accurate** | Cubic spline | Full subpixel refinement |

> **Note:** Automatic registration with **Fast** quality is disabled if either
> image dimension is too small for the pyramid algorithm to function. In that
> case use Accurate, or use Manual mode.

---

### Landmark Points

Landmarks are displayed as coloured crosses overlaid on the source and target
images. Their meaning depends on the transformation type:

**Translation:** one green cross in each image. Drag to set the corresponding
point that should map from source to target.

**Rigid Body:** three landmarks per image. The **green cross** determines the
translation (where the centre of mass maps to). The **blue** and **brown**
crosses determine the rotation angle — only their angular position matters,
not their exact distance.

**Scaled Rotation:** two landmarks per image. The pair defines both the
translation and the scale/rotation.

**Affine:** three landmarks forming a triangle (simplex) in each image.

**Bilinear:** four landmarks per image.

**Moving a landmark:**
- Select the move-points tool (arrow icon in TurboReg toolbar)
- Click near the landmark you want to move — the nearest one is highlighted
- Drag to the new position, or use keyboard arrow keys for fine control
- Press **Tab** to cycle through landmarks

> **Note:** Landmarks cannot be dragged outside the image frame interactively.
> To place a landmark outside the frame, save the configuration, edit the
> coordinate values in the text file, and reload it.

---

### Save Now… / Load…

| Button | Action |
|---|---|
| **Save Now…** | Saves the current landmark configuration to a text file. The file records image dimensions and landmark coordinates. |
| **Load…** | Restores a landmark configuration from a previously saved file. Image dimensions must match; a mismatch is rejected. |

The saved file can be edited in a text editor to adjust landmark coordinates,
which is the only way to place landmarks outside image boundaries.

---

### Save on Exit (checkbox)

When ticked, the refined landmark positions produced by automatic registration
are saved to a file when the plugin closes. Useful for applying the same
registration to another image later.

---

### Credits…

Displays plugin version, author, and a link to the EPFL BIG TurboReg page.

---

## Image Magnification Controls

Zoom controls in the TurboReg toolbar:

- **Click** with the magnification tool to zoom in
- **Ctrl+Click** to zoom out
- Arrow keys move the selected landmark by one pixel at a time when the
  move-points tool is active

---

## Viewing Registration Results

After clicking **Automatic** or **Batch**, TurboReg opens a new image window
containing the warped source. The result is always a float 32-bit image (or
RGB if source was RGB). The original source and target images are not modified.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| TurboReg shows error on launch | Fewer than 2 images are open | Open at least 2 images before launching |
| Automatic mode disabled (greyed) | Image too small for pyramid, quality set to Fast | Set Quality to **Accurate** |
| Batch button greyed out | Source is not a stack, or source is an RGB stack | Convert source to a grayscale stack first |
| Output is all black or inverted | Source and target intensity ranges differ | Normalise both images before registration |
| Landmarks reset unexpectedly | Transformation type was changed | Changing type always resets landmarks; set type first |
| Registration result is poor | Landmark initial positions are far from correct | Move landmarks closer to corresponding features manually before clicking Automatic |
