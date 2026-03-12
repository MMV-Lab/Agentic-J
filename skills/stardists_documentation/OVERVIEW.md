# StarDist — OVERVIEW

## What It Is
StarDist is an ImageJ/Fiji plugin for cell and nuclei detection in microscopy images.
It uses deep-learning models with **star-convex polygon shape priors** to detect
object instances. Each detected object is described as a star-convex polygon defined
by radial distances from a predicted centre point — making it well-suited for round
and moderately convex objects. The plugin applies already-trained models (built-in
or custom) to new images; training requires the separate Python package.

Developed by Uwe Schmidt and Martin Weigert at MPI-CBG.

> **2D only:** The Fiji plugin currently supports **2D images and 2D+time (timelapse)**
> data only. For 3D volumetric data, use the Python package directly.

---

## Typical Inputs and Use Cases

### Fluorescence nuclei segmentation (DAPI / Hoechst)
- **Input:** 8-bit or 16-bit single-channel fluorescence image; round nuclei, bright on dark background
- **Model:** `Versatile (fluorescent nuclei)` — trained on DSB 2018 challenge data
- **Goal:** Detect and segment individual cell nuclei; count cells; measure area, intensity
- **When it works well:** Round to slightly oval nuclei with good contrast; crowded fields; touching nuclei
- **Key parameters:** `probThresh` ~0.5, `nmsThresh` ~0.4, `normalizeInput` true

### H&E histology — nuclei in tissue sections
- **Input:** RGB or single-channel brightfield image of haematoxylin-eosin stained tissue
- **Model:** `Versatile (H&E nuclei)` — trained on MoNuSeg 2018 and TCGA archive data
- **Goal:** Detect and count nuclei in tissue sections; support pathology workflows
- **When it works well:** Dense tissue with varied nuclear morphology; multiple cell types
- **Key parameters:** `probThresh` ~0.692 (model default), `nmsThresh` ~0.3

### Cell counting in culture / well-plate assays
- **Input:** Single-channel fluorescence images of labelled nuclei
- **Pipeline:** StarDist 2D → ROI Manager → Measure (area, mean intensity, etc.)
- **Goal:** Automated cell counting across many images; exportable counts per image
- **When it works well:** Consistent staining; single focal plane; no large debris

### Time-lapse / timelapse cell tracking (semi-automated)
- **Input:** Multi-frame 2D+time image stack
- **Pipeline:** StarDist 2D applied frame by frame → track detections downstream
- **Goal:** Count cells at each time point; provide input to a tracking algorithm
- **Key parameters:** `roiPosition`: `"Stack"` or `"Hyperstack"` to propagate ROIs across frames

### Batch processing of imaging screens
- **Input:** Directory of 2D TIFF files (e.g. from high-content screening)
- **Pipeline:** Script iterates over files; StarDist run on each; results saved per file
- **Goal:** Unattended analysis of hundreds or thousands of images
- **Script approach:** Jython `command.run(StarDist2D, ...)` or IJ Macro `Command From Macro`

### Custom model application (user-trained)
- **Input:** Any 2D microscopy image; model trained by user in Python
- **Model:** Exported `.zip` file loaded from disk or URL
- **Goal:** Apply a model trained on the user's own annotated data for specialised objects
- **Notes:** Custom models are loaded via `modelFile` parameter (path to `.zip`) and
  `modelChoice` set to `"Model (.zip) from File"` or `"Model (.zip) from URL"`

---

## Input Image Requirements

| Requirement | Details |
|-------------|---------|
| Dimensionality | 2D single plane, or 2D+time (multi-frame) |
| Bit depth | 8-bit or 16-bit; 32-bit and RGB accepted but may require tuning |
| Channels | Single channel only per run; extract channel before running |
| Image type | Grayscale for fluorescence models; RGB for H&E model |
| 3D stacks | NOT supported in the Fiji plugin; use Python package instead |

---

## Output Types

| Output | How to obtain | What it contains |
|--------|--------------|-----------------|
| Label Image | `outputType = "Label Image"` | Integer label image; each object has a unique value |
| ROI Manager | `outputType = "ROI Manager"` | All detections as polygon ROIs in the ROI Manager |
| Both | `outputType = "Both"` | Label image + ROI Manager entries simultaneously |
| Probability/Score Image | `showProbAndDist = true` | Per-pixel detection probability (0–1) |
| Distance Image | `showProbAndDist = true` | Per-pixel radial distance predictions |

---

## Automation Level
**Fully scriptable** via two approaches:
- **IJ Macro:** `run("Command From Macro", "command=[de.csbdresden.stardist.StarDist2D], args=[...]")`
  — works in `.ijm` macros; image referenced by window title string
- **Jython/Groovy (SciJava):** `command.run(StarDist2D, False, "input", imp, ...)`
  — more robust; image passed as object; preferred for batch processing

Both approaches expose all the same parameters.

---

## Built-in Models

| Model name (exact string) | Trained on | Best for |
|--------------------------|-----------|---------|
| `Versatile (fluorescent nuclei)` | DSB 2018 nuclei segmentation challenge subset | Fluorescence nuclei (DAPI, Hoechst, etc.) |
| `DSB 2018 (from StarDist 2D paper)` | DSB 2018 challenge data | Fluorescence nuclei (alternative tuning) |
| `Versatile (H&E nuclei)` | MoNuSeg 2018 + TCGA archive | H&E histology nuclei |

---

## Installation

**Required update sites (all three must be enabled):**

1. Start Fiji.
2. **Help ▶ Update… ▶ Manage update sites**
3. Tick all three:
   - **CSBDeep**
   - **StarDist**
   - **TensorFlow** (may be labelled TF or TensorFlow depending on Fiji version)
4. Click **Close ▶ Apply changes**
5. Restart Fiji.

> If `StarDist` is missing from the list, click **Update URLs** to refresh.
> On some systems: Edit ▶ Options ▶ TensorFlow → select a CPU version if GPU/CUDA is unavailable.

---

## Known Limitations

- **2D only:** The Fiji plugin does not support 3D stacks. Process stacks slice-by-slice or use the Python package.
- **Single channel per run:** Multi-channel images must have the target channel extracted or selected before running.
- **Star-convex shape assumption:** Objects with highly concave shapes (e.g. U-shaped cells, ring-like structures) will not be well-segmented.
- **Large images:** May cause out-of-memory errors. Increase `nTiles` to process the image in a grid of tiles.
- **Custom models:** Must be exported as `.zip` from the Python training code. Model `.zip` paths with spaces may need special handling.
- **Boundary objects:** Objects at the image edge are excluded by default (`excludeBoundary = 2`). Set to `0` to keep edge objects.
- **GPU requirement:** Optional. The plugin runs on CPU. GPU (CUDA) can be enabled via TensorFlow options for faster inference.

---

## Citation

> Schmidt, U., Weigert, M., Broaddus, C., & Myers, G. (2018).
> Cell Detection with Star-Convex Polygons.
> In *Medical Image Computing and Computer-Assisted Intervention – MICCAI 2018*
> (pp. 265–273). Springer. doi:10.1007/978-3-030-00934-2_30

> Weigert, M., Schmidt, U., Haase, R., Sugawara, K., & Myers, G. (2020).
> Star-convex Polyhedra for 3D Object Detection and Segmentation in Microscopy.
> *IEEE Winter Conference on Applications of Computer Vision (WACV)*. (3D extension)

---

## Links

| Resource | URL |
|----------|-----|
| ImageJ wiki page | https://imagej.net/plugins/stardist |
| GitHub (plugin) | https://github.com/stardist/stardist-imagej |
| GitHub (Python package + training) | https://github.com/stardist/stardist |
| FAQ | https://stardist.net/docs/faq.html |
| Image.sc forum (tag: stardist) | https://forum.image.sc/tag/stardist |
| Batch script example (Jython) | https://gist.github.com/maweigert/8dd6ef139e1cd37b2307b35fb50dee4a |
