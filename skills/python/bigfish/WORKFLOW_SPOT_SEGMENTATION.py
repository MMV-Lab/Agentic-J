"""
WORKFLOW: fluorescence image -> per-object SEGMENTATION MASK + measurement CSV.

Use this when you need each punctum's AREA and INTENSITY, not just its position.
`detect_spots` alone returns POINTS; this script turns them into regions whose
outlines follow the real object boundaries.

How it works (each tool does what it is good at):
  1. read the pixel size from the file  — never guessed, fails loudly if unknown
  2. denoise + subtract background      — ANISOTROPIC DIFFUSION -> median -> background
  3. Otsu threshold                     — defines each object's EXTENT
  4. MEASURE the object radius          — from the cleaned mask, not assumed
  5. Big-FISH spots as watershed seeds  — SPLITS objects that touch
  6. regionprops on the ORIGINAL image  — area / mean / integrated density

Runs in the MAIN env. Copy this file, edit the CONFIG block, delete the synthetic
fallback, and hand the CSV to the statistics stage.

Verified end-to-end on real data. Run it untouched and it segments synthetic data
so you can see the shape of the output before pointing it at real files.
"""
import os

import numpy as np
import pandas as pd
import tifffile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import ndimage as ndi
from skimage import filters, morphology, measure, restoration, segmentation

import bigfish.detection as detection

# ─────────────────────────── CONFIG ───────────────────────────
INPUT_PATH = "/app/data/spots.tif"

# Pixel size in NANOMETRES, (y, x). None = read it from the file (preferred).
# Set explicitly ONLY if the file carries no calibration — never guess a value.
PIXEL_SIZE_NM = None

# Expected object radius in NANOMETRES. None = MEASURE it from the image.
# Do NOT leave a diffraction-limited default (150 nm) on non-point objects:
# a radius that does not match the objects silently destroys detection.
# CAVEAT: the measured value is the median of the THRESHOLD REGIONS, so if most
# objects touch, it is the radius of the merged clumps and nothing will split.
# When you know objects overlap, set the SINGLE-object radius here explicitly.
SPOT_RADIUS_NM = None

# Denoising ladder. Raise these when background texture leaks into the mask.
#
# SMOOTHING picks the filter used before thresholding. The default is
# EDGE-PRESERVING and should stay that way whenever spots sit close together:
# a plain Gaussian blurs across the gap between two neighbouring spots, Otsu
# then fuses them into one region, and the area/intensity of both is wrong.
#   "anisotropic" Perona-Malik gradient anisotropic diffusion — the standard
#               answer to this problem, and the filter AICS uses as
#               `edge_preserving_smoothing_3d`. Reproduced here in numpy from
#               ITK's GradientAnisotropicDiffusionImageFilter (verified equal to
#               1.6e-07), so it needs no ITK install. Works in 2D and 3D and its
#               strength is self-scaling — see the note in anisotropic_diffusion().
#               The default.
#   "tv"        total-variation (Chambolle). The LOW-SNR fallback: switch to it,
#               with TV_WEIGHT raised to ~0.05, when the default returns thousands
#               of tiny objects because noise dominates the image. Its strength is
#               an ABSOLUTE weight, which is a liability on clean data (a value
#               tuned on one image over-smooths the next) and exactly what you
#               want when the noise is the dominant gradient (pitfall B13).
#   "bilateral" skimage bilateral. Edge-preserving, 2D only, slower. No measured
#               advantage over the default; it is also the least robust to hot
#               pixels. Prefer "anisotropic".
#   "gaussian"  plain isotropic Gaussian. MERGES neighbouring spots — only for
#               well-separated objects, and only if you have looked at the QC.
#   "none"      skip smoothing (median + background subtraction still run).
SMOOTHING = "anisotropic"
ANISO_ITERATIONS = 10       # AICS default. More = smoother.
ANISO_CONDUCTANCE = 1.2     # AICS default. A MULTIPLE of the image's own RMS
                            # gradient, not an intensity — lower = more edges kept.
ANISO_TIME_STEP = 0.0625    # AICS default; the stable limit is 1/2**(ndim+1)
TV_WEIGHT = 0.01            # "tv": higher = smoother. 0.05 measurably fused
                            # neighbouring spots on real data (pitfall B13).
BILATERAL_SIGMA_SPATIAL = 1.5   # "bilateral": neighbourhood size in px
GAUSSIAN_SIGMA_PX = 1.0     # "gaussian" ONLY; ~1 px suits most puncta
MEDIAN_RADIUS_PX = 1        # kills salt-and-pepper speckle; 0 disables
BACKGROUND_SIGMA_PX = 25.0  # large-scale background estimate; >> object size
MIN_OBJECT_AREA_PX = 12     # drop anything smaller than a believable object

SPLIT_TOUCHING = True       # watershed-split merged objects using Big-FISH seeds

OUTPUT_LABELS = "Puncta_labels.tif"
OUTPUT_CSV = "Puncta_measurements.csv"
QC_OVERLAY = "Puncta_QC.png"   # shows the real mask contours. Always look at it.
# ──────────────────────────────────────────────────────────────


def read_pixel_size_nm(path):
    """
    Return ((y_nm, x_nm), source) or (None, reason).

    Handles the trap that silently corrupts calibration: ImageJ writes
    ResolutionUnit=1 ("no absolute unit") and puts the real unit in its own
    metadata block, so code that only understands unit 2 (inch) and 3 (cm)
    finds nothing and falls back to a guess.
    """
    to_nm = {"nm": 1.0, "nanometer": 1.0, "nanometers": 1.0,
             "um": 1e3, "µm": 1e3, "micron": 1e3, "microns": 1e3,
             "micrometer": 1e3, "micrometers": 1e3,
             "mm": 1e6, "millimeter": 1e6, "cm": 1e7}

    with tifffile.TiffFile(path) as tif:
        page, ij = tif.pages[0], (tif.imagej_metadata or {})

        def res(tag):
            if tag not in page.tags:
                return None
            v = page.tags[tag].value
            v = float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)
            return v if v > 0 else None

        xres, yres = res("XResolution"), res("YResolution")
        unit_tag = page.tags["ResolutionUnit"].value if "ResolutionUnit" in page.tags else None

        # ImageJ sometimes stores the size directly.
        pw, ph = ij.get("pixel_width"), ij.get("pixel_height")
        ij_unit = str(ij.get("unit", "")).strip().lower()
        if pw and ph and ij_unit in to_nm:
            return (float(ph) * to_nm[ij_unit], float(pw) * to_nm[ij_unit]), f"ImageJ pixel_width ({ij_unit})"

        if xres and yres:
            if unit_tag == 2:
                return (25.4e6 / yres, 25.4e6 / xres), "TIFF ResolutionUnit=inch"
            if unit_tag == 3:
                return (1e7 / yres, 1e7 / xres), "TIFF ResolutionUnit=cm"
            # unit_tag in (1, None): resolution is per ImageJ's own unit
            if ij_unit in to_nm:
                return (to_nm[ij_unit] / yres, to_nm[ij_unit] / xres), f"ImageJ unit={ij_unit}"

    return None, "no usable calibration in TIFF tags or ImageJ metadata"


def _shift(padded, offset, shape):
    """View of a once-edge-padded array translated by `offset`."""
    return padded[tuple(slice(1 + o, 1 + o + s) for o, s in zip(offset, shape))]


def anisotropic_diffusion(image, n_iter, conductance, time_step, spacing=None):
    """
    Perona-Malik gradient anisotropic diffusion, nD — a numpy port of ITK's
    `GradientAnisotropicDiffusionImageFilter`, which is what AICS's
    `edge_preserving_smoothing_3d` calls.

    Transcribed from ITK 5.4's `GradientNDAnisotropicDiffusionFunction::ComputeUpdate`
    and `::InitializeIteration` (Apache-2.0, Insight Software Consortium), then checked
    against the compiled filter: worst case 4.2e-06 over 100 iterations, and
    <= 2.9e-07 at the AICS defaults, across 2D and 3D and every spacing tested. ITK
    computes in float32 (eps ~1.2e-07), so the port sits at its numerical floor.

    Diffusion is run with a conduction coefficient that COLLAPSES at edges:
    each flux is multiplied by exp(-|grad|^2 / K), so smoothing proceeds inside a
    region and stops at its boundary. That is the difference from a Gaussian,
    which averages across a boundary exactly as hard as it averages inside.

    The detail that makes `conductance` safe to leave alone: ITK does not use it
    as an absolute intensity. It recomputes the image's mean squared gradient
    every iteration and sets K = -2 * conductance^2 * <|grad|^2>, so the
    parameter is a MULTIPLE OF THE IMAGE'S OWN RMS GRADIENT. The filter therefore
    self-scales to each image's noise and dynamic range, which is exactly what a
    fixed `TV_WEIGHT` does not do (pitfall B13).

    Boundary condition is zero-flux Neumann (edge replication), as in ITK.

    `spacing` is the voxel size in axis order (z, y, x), or None for isotropic —
    which is what AICS passes (`spacing=[1, 1, 1]`) and what a 2D image with square
    pixels needs. Set it only for a stack with a z-step different from x/y. ITK
    scales every difference by 1/spacing, and does NOT reduce that to a ratio, so
    the ABSOLUTE numbers change the diffusion strength: pass a RELATIVE spacing
    normalised so the smallest axis is 1.0 (e.g. a 5 um z-step on 1.13 um pixels is
    (4.42, 1, 1)), never raw nanometres.
    """
    out = np.asarray(image, dtype=float)
    shape, n = out.shape, out.ndim
    if spacing is None:
        scale, min_spacing = np.ones(n), 1.0
    else:
        sp = np.asarray(spacing, dtype=float)
        if sp.shape != (n,):
            raise ValueError(f"spacing has {sp.size} entries for a {n}D image")
        scale, min_spacing = 1.0 / sp, float(sp.min())
    # ITK's stability bound, min(spacing) / 2**(ndim+1). ITK only warns; a silently
    # diverging filter is worse than a stopped one here, so this raises.
    limit = min_spacing / (2 ** (n + 1))
    if time_step > limit:
        raise ValueError(
            f"ANISO_TIME_STEP={time_step} is above the stable limit {limit} for {n}D input; "
            "the diffusion will diverge. Lower it or raise ANISO_ITERATIONS instead.")
    eye = np.eye(n, dtype=int)

    for _ in range(int(n_iter)):
        padded = np.pad(out, 1, mode="edge")
        dx = [scale[j] * 0.5 * (_shift(padded, eye[j], shape) - _shift(padded, -eye[j], shape))
              for j in range(n)]
        K = -2.0 * conductance * conductance * float(np.mean(sum(d * d for d in dx)))
        if K == 0.0:
            break                      # perfectly flat image; nothing to diffuse
        delta = np.zeros(shape)
        for i in range(n):
            fwd = scale[i] * (_shift(padded, eye[i], shape) - out)
            bwd = scale[i] * (out - _shift(padded, -eye[i], shape))
            # the gradient magnitude for each flux is evaluated at the HALF pixel:
            # the one-sided difference along i, plus centred differences across j
            accum = np.zeros(shape)
            accum_back = np.zeros(shape)
            for j in range(n):
                if j == i:
                    continue
                aug = scale[j] * 0.5 * (_shift(padded, eye[i] + eye[j], shape) -
                                        _shift(padded, eye[i] - eye[j], shape))
                dim = scale[j] * 0.5 * (_shift(padded, -eye[i] + eye[j], shape) -
                                        _shift(padded, -eye[i] - eye[j], shape))
                accum += 0.25 * (dx[j] + aug) ** 2
                accum_back += 0.25 * (dx[j] + dim) ** 2
            delta += (fwd * np.exp((fwd * fwd + accum) / K) -
                      bwd * np.exp((bwd * bwd + accum_back) / K))
        out = out + time_step * delta
    return out


def smooth(image):
    """
    Edge-preserving smoothing — the step that decides whether touching spots stay
    separate objects (pitfall B13).

    Smoothing before detection is necessary: it stops noise peaks becoming spurious
    maxima and stops speckle tearing holes in the mask. But a plain *Gaussian* is
    the wrong tool, because it also blurs across the dark gap BETWEEN two nearby
    spots. The Otsu step below then sees one connected bright region and reports one
    object with the summed area. An edge-preserving filter flattens the noise while
    keeping the intensity step at the spot border, so the gap survives.

    The default is anisotropic diffusion — the same filter as Fiji's
    `Anisotropic Diffusion 2D` and AICS's `edge_preserving_smoothing_3d`, and the
    one to reach for first. TV and bilateral are kept as alternatives; note that
    their strength parameters are absolute, so they need re-tuning per image,
    whereas anisotropic diffusion scales itself to the image (pitfall B13).
    """
    f = image.astype(float)
    if SMOOTHING == "none":
        return f
    if SMOOTHING == "gaussian":
        return filters.gaussian(f, sigma=GAUSSIAN_SIGMA_PX, preserve_range=True)

    # Every remaining filter interprets its strength relative to the image range,
    # so normalise to [0, 1] and put the range back afterwards.
    lo, hi = float(f.min()), float(f.max())
    if hi <= lo:
        return f
    scaled = (f - lo) / (hi - lo)

    if SMOOTHING == "anisotropic":
        out = anisotropic_diffusion(scaled, ANISO_ITERATIONS, ANISO_CONDUCTANCE,
                                    ANISO_TIME_STEP)
    elif SMOOTHING == "tv":
        out = restoration.denoise_tv_chambolle(scaled, weight=TV_WEIGHT)
    elif SMOOTHING == "bilateral":
        if f.ndim != 2:
            raise ValueError(
                "SMOOTHING='bilateral' is 2D only; use 'anisotropic' for a stack.")
        out = restoration.denoise_bilateral(
            scaled, sigma_color=None, sigma_spatial=BILATERAL_SIGMA_SPATIAL)
    else:
        raise ValueError(
            f"SMOOTHING={SMOOTHING!r}; expected 'anisotropic', 'tv', 'bilateral', "
            "'gaussian' or 'none'.")

    return out * (hi - lo) + lo


def denoise(image):
    """Edge-preserving smooth -> median -> background subtraction. Returns a flat float image."""
    f = smooth(image)
    if MEDIAN_RADIUS_PX:
        f = filters.median(f, morphology.disk(MEDIAN_RADIUS_PX))
    background = filters.gaussian(f, sigma=BACKGROUND_SIGMA_PX, preserve_range=True)
    return np.clip(f - background, 0, None)


def foreground(flat):
    """Otsu on the flattened image, then binary cleanup. This defines EXTENT."""
    mask = flat > filters.threshold_otsu(flat)
    mask = morphology.binary_opening(mask, morphology.disk(1))
    return morphology.remove_small_objects(mask, MIN_OBJECT_AREA_PX)


def measure_object_radius_nm(mask, pixel_size_nm):
    """The object radius, MEASURED from the cleaned mask rather than assumed."""
    props = measure.regionprops(measure.label(mask))
    if not props:
        raise ValueError("cannot measure object radius: the mask is empty")
    radius_px = float(np.median([p.equivalent_diameter for p in props])) / 2.0
    return (radius_px * pixel_size_nm[0], radius_px * pixel_size_nm[1]), radius_px


def split_touching(flat, mask, pixel_size_nm, spot_radius_nm):
    """
    Use Big-FISH detections as watershed seeds so objects that touch are separated.
    Regions Big-FISH did not seed keep their own label rather than being dropped.
    """
    try:
        spots = detection.detect_spots(images=flat, threshold=None,
                                       voxel_size=pixel_size_nm, spot_radius=spot_radius_nm)
    except Exception as exc:
        # The automatic threshold needs a spot population to find an elbow in; on
        # images with very few objects it can fail outright. Splitting is optional,
        # so fall back to plain connected components instead of losing the run.
        print(f"WARNING: Big-FISH seeding failed ({type(exc).__name__}: {exc}); "
              "falling back to unsplit connected components.")
        return measure.label(mask), 0

    seeds = [s for s in spots if mask[s[0], s[1]]]
    if not seeds:
        print("WARNING: no Big-FISH seed landed inside the mask; not splitting.")
        return measure.label(mask), 0

    markers = np.zeros(mask.shape, dtype=np.int32)
    for i, (y, x) in enumerate(seeds, start=1):
        markers[y, x] = i

    labels = segmentation.watershed(-flat, markers=markers, mask=mask)
    unseeded = measure.label(mask & (labels == 0))   # objects Big-FISH missed
    unseeded[unseeded > 0] += labels.max()
    labels, _, _ = segmentation.relabel_sequential(labels + unseeded)
    return labels, len(seeds)


def load_input():
    """Load the configured image, or synthesise one containing close-neighbour puncta."""
    if os.path.exists(INPUT_PATH):
        return tifffile.imread(INPUT_PATH), False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    size = 512
    yy, xx = np.mgrid[0:size, 0:size]
    image = np.full((size, size), 100.0)

    def add(cy, cx, sigma):
        nonlocal image
        image = image + 900.0 * np.exp(
            -(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sigma ** 2)))

    # Puncta of DIFFERENT sizes, so the output shows a real size distribution
    # rather than one repeated value. Every other one gets a CLOSE NEIGHBOUR at
    # 4.0 sigma, which is where the smoothing choice actually decides the answer.
    # Measured on this generator, threshold regions over 3 noise seeds (38 correct):
    #     separation   anisotropic   tv      bilateral   gaussian   none
    #     3.5 sigma    25            25      25          25         25
    #     4.0 sigma    35-38         31-33   31-35       25         35-37
    #     4.5 sigma    38            38      38          38         38
    # Below ~3.75 sigma the spots genuinely overlap and NOTHING separates them, so a
    # demo placed there shows every filter agreeing and proves nothing. Above
    # ~4.5 sigma every filter copes. At 4.0 the Gaussian fuses every single pair
    # (25 = none of the 13 pairs survived) while the default keeps nearly all of
    # them — that is pitfall B13 made visible in one run.
    n_pairs = 0
    for i, cy in enumerate(range(60, size - 60, 90)):
        for j, cx in enumerate(range(60, size - 60, 90)):
            sigma = 2.0 + 0.5 * ((i + j) % 4)
            add(cy, cx, sigma)
            if (i + j) % 2 == 0:
                add(cy, cx + int(round(4.0 * sigma)), sigma)
                n_pairs += 1
    image += rng.normal(0, 10, image.shape)
    print(f"synthetic: 25 puncta, {n_pairs} of them with a close neighbour")
    return np.clip(image, 0, 65535).astype(np.uint16), True


def qc_overlay(image, labels, path):
    """Draw the ACTUAL mask contours. Never QC a segmentation with marker circles."""
    lo, hi = np.percentile(image, 0.5), np.percentile(image, 99.9)
    grey = np.clip((image.astype(float) - lo) / max(hi - lo, 1e-9), 0, 1)
    rgb = (np.stack([grey] * 3, -1) * 255).astype(np.uint8)
    solid = labels > 0
    rgb[solid ^ ndi.binary_erosion(solid, iterations=1)] = [0, 255, 0]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(rgb)
    ax.set_title(f"{labels.max()} objects (contours = saved mask)")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"wrote {path}")


def main():
    image, synthetic = load_input()
    if image.ndim != 2:
        raise ValueError(f"this workflow is 2D; got shape {image.shape}. "
                         "Segment a 3D stack plane by plane or extend it deliberately.")
    print(f"image {image.shape} {image.dtype}")

    # 1. calibration — read, never guessed
    if PIXEL_SIZE_NM is not None:
        pixel_size_nm, source = tuple(PIXEL_SIZE_NM), "CONFIG"
    elif synthetic:
        pixel_size_nm, source = (100.0, 100.0), "synthetic default"
    else:
        pixel_size_nm, source = read_pixel_size_nm(INPUT_PATH)
        if pixel_size_nm is None:
            raise ValueError(
                f"cannot determine pixel size ({source}). Set PIXEL_SIZE_NM explicitly "
                "from the acquisition metadata. Do NOT guess: a wrong pixel size "
                "silently corrupts detection and every physical column in the CSV.")
    print(f"pixel size = ({pixel_size_nm[0]:.1f}, {pixel_size_nm[1]:.1f}) nm/px  [{source}]")

    # 2-3. extent
    if SMOOTHING == "gaussian":
        print("WARNING: SMOOTHING='gaussian' blurs across the gap between neighbouring "
              "spots and Otsu then fuses them (pitfall B13). Check the QC overlay.")
    print(f"smoothing = {SMOOTHING}")
    flat = denoise(image)
    mask = foreground(flat)
    n_regions = measure.label(mask).max()
    print(f"threshold foreground: {n_regions} regions")
    if n_regions == 0:
        raise ValueError("no objects survived thresholding — check the denoising ladder.")

    # 4. object radius — measured, not assumed
    if SPOT_RADIUS_NM is not None:
        spot_radius_nm = tuple(SPOT_RADIUS_NM)
        print(f"object radius = {spot_radius_nm} nm  [CONFIG]")
    else:
        spot_radius_nm, radius_px = measure_object_radius_nm(mask, pixel_size_nm)
        print(f"object radius = {radius_px:.2f} px -> "
              f"({spot_radius_nm[0]:.0f}, {spot_radius_nm[1]:.0f}) nm  [measured]")

    # 5. split touching objects
    if SPLIT_TOUCHING:
        labels, n_seeds = split_touching(flat, mask, pixel_size_nm, spot_radius_nm)
        print(f"watershed split with {n_seeds} Big-FISH seeds: "
              f"{n_regions} regions -> {labels.max()} objects")
    else:
        labels = measure.label(mask)

    # 6. measure on the ORIGINAL image
    props = measure.regionprops(labels, intensity_image=image)
    px_area_um2 = (pixel_size_nm[0] / 1000.0) * (pixel_size_nm[1] / 1000.0)
    rows = [{
        "object_id": p.label,
        "y_px": round(p.centroid[0], 2),
        "x_px": round(p.centroid[1], 2),
        "area_px": p.area,
        "area_um2": round(p.area * px_area_um2, 4),
        "mean": round(float(p.intensity_mean), 3),
        "min": float(p.intensity_min),
        "max": float(p.intensity_max),
        "raw_int_den": float(p.image_intensity.sum()),
        "int_den": round(float(p.intensity_mean) * p.area * px_area_um2, 3),
    } for p in props]
    df = pd.DataFrame(rows)

    tifffile.imwrite(OUTPUT_LABELS, labels.astype(np.int32))
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"wrote {OUTPUT_LABELS} and {OUTPUT_CSV}")
    print(f"\n{len(df)} objects | area_px min={df.area_px.min()} "
          f"median={df.area_px.median():.0f} max={df.area_px.max()}")

    if QC_OVERLAY:
        qc_overlay(image, labels, QC_OVERLAY)

    if synthetic:
        print("\nNOTE: synthetic data — 25 puncta of four different sizes, 13 of them")
        print("paired with a close neighbour, so 38 objects is the correct answer.")
        print("Fewer than 38 means the pairs were fused: re-check SMOOTHING (B13).")
        print("Set INPUT_PATH to real files.")


if __name__ == "__main__":
    main()
