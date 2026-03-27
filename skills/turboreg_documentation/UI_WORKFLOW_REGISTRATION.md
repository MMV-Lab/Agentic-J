# TurboReg — GUI Workflow: Registering Two Images

This walkthrough covers three common registration scenarios: automatic
single-image alignment, batch stack alignment, and manual alignment with
saved landmarks. Each section is self-contained.

---

## Before You Start — Checklist

- [ ] TurboReg is installed: **Plugins › Registration › TurboReg** appears in the menu
  - If not: **Help › Update… → Manage Update Sites → tick BIG-EPFL → Apply Changes → Restart**
- [ ] At least two images are open in Fiji (TurboReg requires a source and a target)
- [ ] Both images are grayscale (8, 16, or 32-bit) or both are RGB — mixing types is not recommended
- [ ] Images are the same bit depth if possible; convert via **Image › Type** if needed
- [ ] You know which image is the moving image (source) and which is the fixed reference (target)

---

## Workflow A — Automatic Single-Image Registration

The most common use case: align one image to another automatically.

### Step 1 — Open Both Images

Open your source and target images via **File › Open** or drag-and-drop.
Both must be visible as separate image windows.

---

### Step 2 — Launch TurboReg

**Plugins › Registration › TurboReg**

The TurboReg dialog opens. If you see an error instead, fewer than two images
are open — go back to Step 1.

---

### Step 3 — Assign Source and Target

In the dialog:
- **Target** dropdown: select your fixed reference image
- **Source** dropdown: select the image you want to align

The dialog will overlay coloured landmark crosses on both open images.

---

### Step 4 — Choose the Transformation Type

Select the transformation that matches how your images differ:

| Images differ by… | Choose |
|---|---|
| Pure XY shift (no rotation) | **Translation** |
| Shift + rotation, same scale | **Rigid Body** |
| Shift + rotation + uniform zoom | **Scaled Rotation** |
| Shear, non-uniform zoom, rotation | **Affine** |
| Perspective or non-linear warping | **Bilinear** |

> Start with **Translation** or **Rigid Body** unless you know the images have
> scaling differences. Higher-order transformations have more degrees of freedom
> and can overfit if the overlap region is small.

---

### Step 5 — Set Quality

Set **Quality** to **Accurate** for most registration tasks. This enables
cubic-spline interpolation and full pyramid refinement.

Use **Fast** only for a quick preview — the output uses nearest-neighbour
interpolation and is not suitable for quantitative analysis.

---

### Step 6 — (Optional) Adjust Initial Landmarks

TurboReg places landmarks at default positions. For most datasets with
reasonable initial alignment, the defaults are sufficient.

If images are severely misaligned:
1. Select the **move-points tool** in the TurboReg toolbar
2. In both the source and target images, drag each landmark to a corresponding
   anatomical or structural feature
3. Use arrow keys for sub-pixel adjustment of individual landmarks
4. Press **Tab** to cycle between landmarks

Setting better initial positions significantly improves registration success
when images are far from aligned.

---

### Step 7 — Click Automatic

Click the **Automatic** button. TurboReg will:
1. Preprocess both images using a multi-resolution pyramid
2. Iteratively refine the landmark positions to minimise mean-square error
3. Apply the final transformation to produce a warped source image

A progress bar appears in the main ImageJ window during processing. Wait until
it completes — for large images this can take several seconds.

---

### Step 8 — Inspect the Result

A new image window opens containing the warped source (float 32-bit). To check
alignment quality:

1. Open **Image › Color › Merge Channels…** and overlay the registered source
   with the target in different channels (e.g. red and green)
2. Check for residual misalignment: perfectly registered images show a grey
   overlay with no colour fringing at edges of structures
3. Alternatively use **Image › Stacks › Images to Stack** and toggle between
   slices to blink-compare the two images

If registration is poor, go back and adjust the initial landmarks (Step 6)
and try again.

---

### Step 9 — Save the Result

The output image is a float 32-bit ImagePlus. Save it via:
- **File › Save As › Tiff…** — preserves full precision
- **Image › Type › 16-bit** first if your downstream workflow requires 16-bit,
  then **File › Save As › Tiff…**

---

## Workflow B — Batch Stack Registration

Register every slice of a source stack to a single target image.

### Step 1 — Prepare Images

Ensure:
- The **target** is a single 2D image (or two-slice stack if using a mask)
- The **source** is a **grayscale** stack (multiple slices to register)
- The source is NOT an RGB stack (batch mode does not support RGB)

---

### Step 2 — Launch TurboReg

**Plugins › Registration › TurboReg**

---

### Step 3 — Assign Source and Target

Select the stack as **Source** and the reference image as **Target**.

---

### Step 4 — Choose Transformation Type and Quality

Choose the transformation and set Quality to **Accurate**, same as Workflow A.

---

### Step 5 — (Optional) Adjust Landmarks

Adjust initial landmarks if needed, as in Workflow A Step 6. The same
landmarks and transformation are used as starting conditions for every slice.

---

### Step 6 — Click Batch

Click the **Batch** button instead of Automatic. TurboReg will register each
slice in sequence. A progress indicator updates per slice.

> **Note:** Each slice is registered independently to the same target. The
> landmark refinement starts from the default (or manually set) positions for
> every slice — it does not carry over refined positions from the previous slice.

---

### Step 7 — Inspect and Save

The output is a float 32-bit stack with the same number of slices as the source.
Inspect via **Image › Stacks › Orthogonal Views** or by scrolling through slices.
Save as TIFF.

---

## Workflow C — Manual Registration with Saved Landmarks

Use this when you want to apply a known, previously saved transformation —
for example applying the same registration to multiple channels.

### Step 1 — Load Both Images and Launch TurboReg

As in Workflow A Steps 1–3.

---

### Step 2 — Load a Saved Landmark Configuration

Click **Load…** and select a previously saved landmark file (`.txt`).

TurboReg checks that the stored image dimensions match the currently open images.
If they do not match, the load is rejected with an error message.

---

### Step 3 — Click Manual

Click **Manual** to apply the transformation defined by the loaded landmarks
without any automatic refinement. The warped source is produced immediately.

---

### Step 4 — (Optional) Save a New Configuration

After any automatic registration, tick **Save on Exit** in the dialog before
closing to save the refined landmark positions. These can be reloaded in a
later session to apply the exact same transformation to other images.

---

## Workflow D — Registering RGB Images

TurboReg supports RGB stacks but with limitations:
- Only **one colour plane** is used for intensity-based optimisation
- The computed transformation is then applied to all three planes
- **Masking is not supported** for RGB stacks
- **Batch mode is not available** for RGB stacks

The workflow is identical to Workflow A — simply open an RGB image as source
and another as target. TurboReg handles the colour decomposition internally.

---

## Tips for Better Registration

- **Normalise intensity** if the two images have different brightness ranges
  before registration — mean-square minimisation is sensitive to intensity offsets
- **Crop to the overlap region** using Image › Crop before launching TurboReg
  when images only partially overlap; this focuses the optimisation on the
  relevant area and avoids background confusing the algorithm
- **Use Translation first** as a sanity check before trying higher-order
  transformations — if translation alone fails, something more fundamental
  is wrong (wrong image pair, inverted intensity, etc.)
- **Rigid Body is the safest choice** for most microscopy applications where
  the physical scale has not changed between acquisitions
