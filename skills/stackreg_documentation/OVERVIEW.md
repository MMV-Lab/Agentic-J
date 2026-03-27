# StackReg — Overview

## What StackReg Does

StackReg is an ImageJ plugin from EPFL BIG that registers — aligns — every
slice of a stack to the previous slice, proceeding by **propagation**. The
currently active slice when the plugin is launched serves as the **anchor**:
it is not transformed, and all other slices are aligned outward from it in
both directions. This makes it ideal for time-lapse series, serial section
stacks, and any multi-frame acquisition where drift accumulates gradually
from frame to frame.

**Author:** Philippe Thévenaz, EPFL BIG
**Publication:** Thévenaz P, Ruttimann UE, Unser M. "A Pyramid Approach to
Subpixel Registration Based on Intensity." IEEE Transactions on Image Processing,
vol. 7, no. 1, pp. 27–41, January 1998.
**Homepage:** https://bigwww.epfl.ch/thevenaz/stackreg/
**Last updated:** September 30, 2024

---

## Relationship to TurboReg

StackReg is a **front-end to TurboReg**. It does not implement its own
registration algorithm — instead it calls TurboReg internally for every
pairwise slice registration. This has two important consequences:

1. **TurboReg must be installed** for StackReg to work. Both are available
   via the BIG-EPFL update site.
2. StackReg writes **temporary files** into ImageJ's temp directory
   (`StackRegSource`, `StackRegTarget`, and colour channel variants) so that
   TurboReg can access the image data. Any existing files with those names
   in the temp directory will be silently overwritten.

| Feature | TurboReg | StackReg |
|---|---|---|
| Purpose | Align ONE source image to ONE target | Align ALL slices of a stack sequentially |
| Registration strategy | Source → Target (user-defined pair) | Slice N+1 → Slice N (propagation from anchor) |
| Macro-recordable | ❌ No | ✅ Yes |
| Bilinear transform | ✅ Available | ❌ Not available |
| Modifies original | No (produces new image) | Yes — original stack is REPLACED |
| Color support | RGB via single-channel optimization | Grayscale via PCA of colour channels |

---

## Key Behaviour: Propagation and Anchor

Registration proceeds slice by slice starting from the anchor (current slice
at launch time). Each slice is aligned to the immediately preceding registered
slice — not to the anchor directly. This means:

- Small inter-frame errors **do not accumulate** for small stacks
- For very long stacks, small per-frame errors can compound — the first and
  last slices may still be misaligned relative to each other even though each
  adjacent pair is well aligned
- **Setting the anchor** to a central, representative, high-quality slice
  (rather than the first or last) minimises worst-case cumulative error

---

## Four Transformation Types

StackReg offers four of TurboReg's five types. Bilinear is excluded because
a composition of two bilinear transformations is generally not bilinear, making
propagation mathematically inconsistent.

| Type | Degrees of freedom | Typical use |
|---|---|---|
| **Translation** | 2 (Δx, Δy) | Pure XY drift correction |
| **Rigid Body** | 3 (Δx, Δy, θ) | Drift + rotation, no scale change |
| **Scaled Rotation** | 4 (Δx, Δy, θ, λ) | Drift + rotation + uniform zoom |
| **Affine** | 6 (full 2D linear) | Drift + rotation + shear + anisotropic scale |

---

## Input Requirements

| Requirement | Details |
|---|---|
| Minimum slices | 1 (a single-slice image can be processed but nothing changes) |
| Supported types | 8-bit, 16-bit, 32-bit grayscale; stacks of RGB-colour images |
| NOT supported | RGB-stack (3-component, one slice per colour channel); HSB-stack |
| Stack of RGB images | Supported — StackReg builds a grayscale PCA projection internally |

> **RGB-stack vs stack of RGB images:** An RGB-stack has 3 slices (one per
> colour channel). A stack of RGB images has N slices each of which is a
> full-colour image. The former is NOT supported; the latter IS.

---

## Output Behaviour

- The **original stack is destroyed** and replaced in-place by the registered stack
- The image name and type are preserved
- Registration quality is always **Accurate** (cubic-spline interpolation via TurboReg)
- Areas of the image that fall outside the frame after transformation are
  filled with **zeroes** (black)

---

## Scripting

**StackReg IS macro-recordable**, making it significantly easier to script
than TurboReg. The recorded call is:

```groovy
IJ.run("StackReg ", "transformation=[Rigid Body]")
```

The trailing space in `"StackReg "` is **mandatory** (same pattern as TurboReg).

---

## Installation

### Via Fiji Update Sites (recommended)

1. **Help › Update…**
2. Click **Manage Update Sites**
3. Tick **BIG-EPFL** (this installs both StackReg and TurboReg together)
4. Click **Close → Apply Changes → Restart Fiji**

StackReg will then be available under **Plugins › Registration › StackReg**.
TurboReg will also be installed as a dependency.

---

## Related Plugins

| Plugin | Purpose | Note |
|---|---|---|
| **TurboReg** | Pairwise image registration (source → target) | Required dependency of StackReg |
| **MultiStackReg** | Applies registration computed on one stack to another | Useful for multi-channel workflows |
| **HyperStackReg** | Extends StackReg to multi-channel hyperstacks | Selects specific channels for registration computation |

---

## Citation

Any publication using StackReg must cite:

Thévenaz P, Ruttimann UE, Unser M. "A Pyramid Approach to Subpixel
Registration Based on Intensity." IEEE Transactions on Image Processing,
vol. 7, no. 1, pp. 27–41, January 1998.
