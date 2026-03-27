# StackReg — GUI Workflow: Registering a Time-Lapse Stack

This walkthrough covers three common scenarios: basic automatic stack
registration, multi-channel registration, and the pattern of computing a
registration on one channel and applying it to another using MultiStackReg.

---

## Before You Start — Checklist

- [ ] StackReg is installed: **Plugins › Registration › StackReg** appears in the menu
  - If not: **Help › Update… → Manage Update Sites → tick BIG-EPFL → Apply Changes → Restart**
- [ ] TurboReg is also installed (it is a required dependency — the BIG-EPFL site
  installs both together)
- [ ] Your stack is open as a single image with multiple slices (not as separate windows)
- [ ] The stack is grayscale (8, 16, or 32-bit) or a stack of RGB-colour images
  — NOT an RGB-stack (3-slice stack with one channel per slice)
- [ ] You have identified a good anchor slice — ideally one that is central,
  sharp, and representative of the whole stack

---

## Workflow A — Standard Time-Lapse Registration

### Step 1 — Open Your Stack

Open the stack via **File › Open** or drag-and-drop. The stack must open as a
single window with a slice slider at the bottom. Confirm by checking the title
bar, which should show something like `timelapse.tif [1/120]`.

---

### Step 2 — Navigate to the Anchor Slice

Use the slice slider at the bottom of the stack window to navigate to the slice
you want to use as the registration anchor.

> **Choosing the anchor:** StackReg registers each slice to the previous one
> (propagation). The anchor is the only slice that is not moved. Choosing a
> central, well-focused slice minimises the worst-case accumulated error across
> the full stack. For a 120-frame time-lapse, slice 60 is a better anchor than
> slice 1 or 120.

---

### Step 3 — Launch StackReg

**Plugins › Registration › StackReg**

The StackReg dialog opens with a transformation scroll list.

---

### Step 4 — Choose the Transformation

Select the transformation type that matches how your images move between frames:

| Your imaging situation | Recommended transformation |
|---|---|
| Camera/stage XY drift, no rotation | **Translation** |
| Slight rotation between frames (e.g. animal movement) | **Rigid Body** |
| Zoom change between frames | **Scaled Rotation** |
| General geometric distortion | **Affine** |

For most time-lapse microscopy (stage drift correction), **Translation** or
**Rigid Body** are appropriate. Affine has more degrees of freedom but can
produce artefacts on images with limited content.

---

### Step 5 — Click OK

Click **OK**. StackReg processes the stack silently — the currently registered
slice is shown in the image window during processing. For large stacks this
may take a few minutes.

> **Important:** The original stack data is overwritten in-place. If you want
> to keep the unregistered original, duplicate the stack first:
> **Image › Duplicate… → tick "Duplicate entire stack"**

---

### Step 6 — Inspect the Result

After completion:
- The image window returns to the anchor slice
- Scroll through the stack to verify that structures are stable across frames
- Check for black triangular borders at edges (expected from transformation)

To do a quick quality check, use **Image › Stacks › Z Project…** with
**Projection Type: Standard Deviation**. A well-registered stack produces a
uniform low-variance projection; a poorly registered stack shows bright edges
or duplicated structures.

---

### Step 7 — Save the Result

The registered stack is already in the same image window. Save it via
**File › Save As › Tiff…** to preserve all slices and metadata.

---

## Workflow B — Registering a Colour Time-Lapse

StackReg handles stacks of RGB-colour images automatically.

### Step 1 — Verify the Stack Format

Confirm the stack is a **stack of RGB images**, not an RGB-stack:
- Stack of RGB images: each slice is a full colour image (`[1/N]` in title bar)
- RGB-stack: exactly 3 slices (R, G, B channels) — this format is NOT supported

If your image is in RGB-stack format, convert it first: **Image › Hyperstacks
› Stack to Hyperstack…** or **Image › Color › Make Composite** depending on
your data structure.

---

### Step 2 — Proceed as Workflow A

Follow Steps 2–7 of Workflow A. StackReg detects the colour format
automatically and internally creates a PCA-based grayscale version for
registration computation, then applies the resulting transformation to all
three colour channels.

---

## Workflow C — Register One Channel, Apply to Another (MultiStackReg)

A common microscopy scenario: you have two channels, and channel 1 is
brighter/more stable and better suited for computing registration, but you
also need channel 2 to be registered with the same transformation.

This requires **MultiStackReg**, which builds on StackReg.

### Step 1 — Separate the Channels

With your multi-channel stack open:
**Image › Color › Split Channels**

This produces separate stacks per channel (e.g. `C1-stack.tif`, `C2-stack.tif`).

---

### Step 2 — Register the Reference Channel with StackReg

Select the channel best suited for registration (e.g. the nuclear marker in C1):
1. Navigate to a good anchor slice
2. **Plugins › Registration › StackReg**
3. Choose your transformation type, click **OK**
4. C1 is now registered in-place

---

### Step 3 — Apply the Same Transform to Other Channels

Install MultiStackReg if not present (**Help › Update… → Manage Update Sites
→ tick MultiStackReg**). Then:

1. **Plugins › Registration › MultiStackReg**
2. Set **Stack 1** to your (already registered) C1 stack → Action: **Use as Reference**
3. Set **Stack 2** to C2 → Action: **Align to First Stack**
4. Click **OK**

MultiStackReg reads the transformation computed by StackReg and applies it
to C2, ensuring both channels have identical registration.

---

## Tips and Caveats

**Duplicate before registering:** StackReg replaces the original stack
in-place. Always duplicate your stack if you might need the raw data.

**Anchor choice matters for long stacks:** In a 200-frame time-lapse,
registration error can accumulate from frame to frame. Starting from the
middle (slice 100) rather than frame 1 cuts the maximum propagation distance
in half.

**Z-stacks vs time-lapse:** StackReg works identically on Z-stacks (serial
sections) and time-lapse stacks. The anchor choice is more critical for
Z-stacks because the content can change substantially between sections, making
propagation more prone to failure at large Z distances.

**Translation is fastest and most robust:** For most drift-correction
applications, Translation is sufficient and less likely to overfit than Affine.
Only upgrade to Rigid Body or Affine if Translation clearly fails.

**Check the temp directory:** If StackReg fails partway through a large stack,
check that the ImageJ temp directory has sufficient free space. Each temp file
is a full float-32 copy of one slice.
