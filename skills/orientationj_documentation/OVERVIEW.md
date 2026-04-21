# OrientationJ — OVERVIEW

## What It Is
OrientationJ is a Fiji/ImageJ plugin developed at the Biomedical Imaging Group
(BIG, EPFL) for **local orientation and coherency analysis** in grayscale images.
It is based on the structure tensor: at each pixel, a local window is used to
estimate the dominant orientation, a coherency score (how strongly aligned the
neighborhood is), and an energy score (how much signal is present).

The plugin ships several modes that turn these per-pixel quantities into
different outputs:

- **Analysis** — dense per-pixel orientation, coherency, and energy images plus a color survey
- **Distribution** — global orientation histogram, weighted by coherency
- **Vector Field** — direction vectors on a regular grid overlaid on the source
- **Corner Harris** — Harris corner index image and detected-corner overlay
- **Dominant Direction** — one dominant angle and coherency value per slice
- **Measure** — ROI-based orientation/coherency reading to the log (interactive)

---

## Typical Inputs and Use Cases

### Collagen fibre alignment (SHG / fluorescence)
- **Input:** 8-bit or 16-bit grayscale image of collagen fibres, often from second-harmonic generation or picrosirius-stained histology
- **Pipeline:** `OrientationJ Analysis` → coherency + color survey; optional `OrientationJ Distribution` for a histogram peak
- **Goal:** Quantify fibre alignment in tumour stroma, wound tissue, or ECM remodelling
- **Key parameters:** `tensor` 1.0–3.0 depending on fibre thickness, `min-coherency` 10–30% to suppress background

### Actin / cytoskeleton orientation
- **Input:** Fluorescence image of phalloidin- or lifeact-stained cells
- **Pipeline:** `OrientationJ Analysis` for per-cell orientation map; `OrientationJ Vector Field` for overlay figures
- **Goal:** Show cytoskeletal alignment across a monolayer or within individual cells
- **Key parameters:** smaller `tensor` (0.5–1.0) to preserve fine filament directions

### Muscle fibre / myofibril orientation
- **Input:** Brightfield or fluorescence image of skeletal or cardiac muscle sections
- **Pipeline:** `OrientationJ Dominant Direction` for one angle per field of view; `OrientationJ Distribution` for a tissue-level histogram
- **Goal:** Compare fibre organisation across conditions; single-number summary per slice

### Extracellular matrix anisotropy
- **Input:** 2D projection of an ECM or fibrous scaffold image
- **Pipeline:** `OrientationJ Distribution` → histogram spread as a proxy for anisotropy
- **Goal:** Quantify isotropy vs. alignment; narrow peak = strongly aligned, broad peak = disordered

### Plant tissue and fibre crops
- **Input:** Brightfield or fluorescence image of plant cell walls, xylem, or fibres
- **Pipeline:** `OrientationJ Analysis` + `OrientationJ Distribution`
- **Goal:** Quantify microfibril or vessel orientation

### Materials science — fibre and grain alignment
- **Input:** SEM, TEM, or optical micrograph of fibres, textiles, or polycrystalline grains
- **Pipeline:** `OrientationJ Analysis` for maps; `OrientationJ Vector Field` for figures
- **Goal:** Characterise directional anisotropy in non-biological samples

### Corner detection on oriented structures
- **Input:** Grayscale image where junctions or intersections matter
- **Pipeline:** `OrientationJ Corner Harris`
- **Goal:** Combined orientation + Harris response for structured-feature detection

---

## Input Image Requirements

| Requirement | Details |
|-------------|---------|
| Dimensionality | 2D single plane; some modes work slice-wise on stacks |
| Bit depth | 8-bit, 16-bit, or 32-bit grayscale |
| Channels | Single-channel grayscale only; RGB is rejected |
| Stacks | Distribution, Vector Field, and Dominant Direction produce per-slice outputs |

---

## Output Types

| Output | Produced by | What it contains |
|--------|-------------|------------------|
| Orientation image (float32) | Analysis | Per-pixel dominant angle, ~±90° (`radian=off`) or ~±π/2 (`radian=on`) |
| Coherency image (float32) | Analysis | Per-pixel coherency, 0 (isotropic) to 1 (perfectly aligned) |
| Energy image (float32) | Analysis | Per-pixel local gradient energy, rescaled |
| Color survey (RGB) | Analysis | Orientation encoded as hue, coherency as saturation, source as brightness (HSB default) |
| Histogram plot + table | Distribution | Orientation histogram weighted by coherency; one column per slice |
| Vector overlay + table | Vector Field | Direction vectors on a regular grid; table has X, Y, DX, DY, orientation, coherency, energy |
| Harris index image | Corner Harris | Per-pixel Harris corner response |
| Corner table + overlay | Corner Harris | Detected-corner coordinates plus flattenable overlay |
| Dominant Direction table | Dominant Direction | One row per slice with angle and coherency percentage |
| ImageJ log text | Measure | Tab-separated ROI measurements written to the log |

---

## Automation Level

- **`IJ.run()` macro-recordable** for Analysis, Distribution, Vector Field, Corner Harris, and Dominant Direction. Each command accepts a parameter string.
- **ROI-dependent for `Measure`** — the plugin reads the active ROI and writes measurements to the log; not covered by a checked-in workflow in this skill.
- **`Directions`** menu entry is exposed in `plugins.config` but is not validated in this skill.
- **Headless Fiji note** — image outputs export cleanly, but IJ1 table windows from Vector Field, Corner Harris, and Dominant Direction do not always materialise as `TextWindow` objects. GUI-backed Fiji is more reliable for table export; Dominant Direction has a direct class-level fallback (`computeSpline(...)`).

---

## Installation

**Fiji (recommended):**
1. `Help > Update...`
2. Click **Manage update sites**
3. Enable **BIG-EPFL**
4. Click **Apply changes**, then **Restart Fiji**

**Manual install:**
Download `OrientationJ_.jar` from the BIG-EPFL page and place it in Fiji's
`plugins/` directory, then restart Fiji.

Update site URL: `https://sites.imagej.net/BIG-EPFL/`

---

## Known Limitations

- **Grayscale only** — RGB inputs are rejected by the main analysis path. Convert with `Image > Type > 8-bit` (or similar) before running.
- **Distribution `binary mask` / `orientation mask` keys** are exposed in the dialog but do not produce separate output windows through the `IJ.run(...)` path in the validated Groovy launcher. Rely on the histogram plot and distribution table instead.
- **Vector Field and Corner Harris overlays** are drawn on the active source image. To save the visualisation, flatten the source with `imp.flatten()` after the run.
- **Gradient index `5` (`Hessian`)** is present in the source UI but is not included in this skill's checked-in gradient choices. Indices `0`–`4` (`Cubic Spline`, `Finite Difference`, `Fourier`, `Riesz Filters`, `Gaussian`) are the adopted surface.
- **`OrientationJ Measure`** requires an existing ROI and writes to the log. There is no batch ROI-creation workflow in this skill.
- **Headless tables** — IJ1 `TextWindow` outputs from Vector Field, Corner Harris, and Dominant Direction are not always materialised headlessly; Dominant Direction uses a direct CSV fallback based on the plugin class.
- **`OrientationJ Directions`** (clustering / direction grouping) is listed in the menu but is not validated in this skill.

---

## Citation

> Rezakhaniha, R., Agianniotis, A., Schrauwen, J. T. C., Griffa, A., Sage, D.,
> Bouten, C. V. C., van de Vosse, F. N., Unser, M., & Stergiopulos, N. (2012).
> Experimental investigation of collagen waviness and orientation in the arterial
> adventitia using confocal laser scanning microscopy.
> *Biomechanics and Modeling in Mechanobiology*, 11(3–4), 461–473.

> Püspöki, Z., Storath, M., Sage, D., & Unser, M. (2016).
> Transforms and Operators for Directional Bioimage Analysis: A Survey.
> In *Focus on Bio-Image Informatics*, Advances in Anatomy, Embryology and Cell
> Biology, vol. 219 (pp. 69–93). Springer.

## Links

| Resource | URL |
|----------|-----|
| Project homepage | http://bigwww.epfl.ch/demo/orientation/ |
| Plugin documentation | http://bigwww.epfl.ch/demo/orientation/OrientationJ.html |
| ImageJ wiki page | https://imagej.net/plugins/orientationj |
| BIG-EPFL update site | https://sites.imagej.net/BIG-EPFL/ |
