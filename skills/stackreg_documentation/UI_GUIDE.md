# StackReg — UI Parameter Guide

## Requirements to Launch

StackReg requires:
- **At least one image or stack** to be open and active in Fiji
- The active image must be a supported type (grayscale or stack of RGB images)
- **TurboReg must be installed** — StackReg calls it internally and will fail
  with an error if TurboReg is absent

If the active image is an unsupported type (RGB-stack, HSB-stack), StackReg
will display an explicit error message.

---

## Menu Path

**Plugins › Registration › StackReg**

---

## The StackReg Dialog

The dialog is minimal — it contains only two controls plus the standard OK/Cancel:

---

### Transformation (scroll list)

The single most important parameter. Selects the geometric model used for
each pairwise slice registration.

| Option | Description | Choose when… |
|---|---|---|
| **Translation** | Pure XY shift, no rotation or scaling | Images differ only by lateral drift |
| **Rigid Body** | XY shift + rotation, distances preserved | Drift + slight rotation, no size change |
| **Scaled Rotation** | XY shift + rotation + isotropic scale | Drift + rotation + uniform zoom/shrink |
| **Affine** | XY shift + rotation + shear + anisotropic scale | Complex geometric distortion between frames |

> **Bilinear is not available.** Bilinear transformations cannot be composed
> (propagated) from one slice to the next, so StackReg excludes this option
> that is present in TurboReg.

**How to choose:**

Start with **Translation** if you only expect XY drift (e.g. stage drift in a
time-lapse). Use **Rigid Body** if rotation between frames is possible (e.g.
slight sample rotation). Only use **Affine** if you have reason to believe the
imaging geometry is changing between frames — it has the most degrees of freedom
and can overfit on featureless images.

---

### Credits (checkbox)

When ticked and OK is clicked, an information panel is shown instead of running
the registration. Untick it to run normally.

---

### Anchor Slice

The anchor is **not a dialog control** — it is set implicitly by which slice
is currently displayed when StackReg is launched. Before opening the dialog:

1. Use the slice slider at the bottom of the stack window to navigate to the
   desired anchor slice
2. The currently displayed slice becomes the anchor — it will not be
   transformed, and all other slices will be registered relative to it

> **Best practice:** choose a central slice with good contrast and
> representative structure as the anchor. This minimises worst-case cumulative
> registration error across the full stack.

---

## Registration Process

After clicking OK:

1. StackReg iterates through all slices in the stack
2. For each adjacent pair, it calls TurboReg internally, writing temporary
   files (`StackRegSource`, `StackRegTarget`) to the ImageJ temp directory
3. The currently-being-registered slice is displayed during processing
4. When complete, the display returns to the anchor slice
5. The **original stack data is replaced in-place** — the registration result
   occupies the same image window

No new window is opened. The registered stack retains the original name and bit depth.

---

## Colour Image Handling

When the active stack contains **RGB colour images** (not to be confused with
an RGB-stack):

- StackReg performs a **principal component analysis (PCA)** across all colour
  channels of the entire stack to create an intermediate grayscale representation
  that maximises contrast
- Registration is computed on this grayscale representation
- The resulting geometric transformation is then applied to all three colour
  channels independently
- If the stack is pseudo-colour, it is re-quantized to restore pseudo-colours
  after transformation

---

## Temporary Files

StackReg writes these files to the ImageJ temp directory during processing:

| Filename | Content |
|---|---|
| `StackRegSource` | Current source slice (float TIFF) |
| `StackRegTarget` | Current target slice (float TIFF) |
| `StackRegSourceR` | Red channel of source (colour stacks only) |
| `StackRegSourceG` | Green channel of source (colour stacks only) |
| `StackRegSourceB` | Blue channel of source (colour stacks only) |

> **Warning:** Any existing files with these names in the temp directory will
> be silently overwritten. To find the temp directory location, run
> `print(getDirectory("temp"));` in the ImageJ Script Editor.

---

## Output

- **In-place replacement** of the active stack with the registered version
- Image name and type preserved
- Pixel type preserved (8-bit input stays 8-bit output, etc.)
- Out-of-frame areas (from transformation) filled with **zeroes**
- Registration quality is always **Accurate** (cubic-spline interpolation)

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Error on launch: plugin not found | TurboReg is not installed | Install via BIG-EPFL update site |
| Error on launch: unsupported image type | Active image is an RGB-stack (3 slices = 3 colour channels) | Convert to a grayscale stack or use a stack of RGB images |
| Black borders appear after registration | Transformation moved content outside frame | Expected behaviour; crop if needed |
| Drift not corrected for late slices | Propagation error accumulates over long stacks | Change anchor to a central representative slice |
| Registration makes things worse | Initial per-frame misalignment too large for Rigid Body/Affine | Try Translation first; ensure images are roughly pre-aligned |
| Colour stack registered in wrong channel | PCA selects channels automatically | Ensure all channels are informative; consider converting to grayscale for registration and applying transform separately |
