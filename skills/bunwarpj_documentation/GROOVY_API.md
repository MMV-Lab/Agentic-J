# bUnwarpJ - Groovy API

This file separates bUnwarpJ's scripting surface into three buckets:

- Container-validated direct API
- Official-doc GUI-oriented macro syntax
- Explicit exclusions for this repo's headless workflow

Primary sources:

- Official plugin page: https://imagej.net/BUnwarpJ
- Fiji Javadocs:
  - https://javadoc.scijava.org/Fiji/bunwarpj/bUnwarpJ_.html
  - https://javadoc.scijava.org/Fiji/bunwarpj/Param.html
  - https://javadoc.scijava.org/Fiji/bunwarpj/Transformation.html

## Container-Validated Direct API

Use this path for Groovy automation in this repo.

### Required imports

```groovy
import bunwarpj.Param
import bunwarpj.Transformation
import bunwarpj.bUnwarpJ_
import ij.IJ
import ij.ImagePlus
import ij.plugin.Duplicator
```

### `Param` constructor

```groovy
def params = new Param(
    mode,
    imgSubsampleFactor,
    minScaleDeformation,
    maxScaleDeformation,
    divergenceWeight,
    curlWeight,
    landmarkWeight,
    imageWeight,
    consistencyWeight,
    stopThreshold
)
```

| Argument | Type | Accepted values | Meaning |
| --- | --- | --- | --- |
| `mode` | `int` | `0 = Fast`, `1 = Accurate`, `2 = Mono` | Registration mode |
| `imgSubsampleFactor` | `int` | `0` to `7` | Subsampling factor, where `0` keeps full resolution |
| `minScaleDeformation` | `int` | `0 = Very Coarse`, `1 = Coarse`, `2 = Fine`, `3 = Very Fine` | Initial deformation scale |
| `maxScaleDeformation` | `int` | `0 = Very Coarse`, `1 = Coarse`, `2 = Fine`, `3 = Very Fine`, `4 = Super Fine` | Final deformation scale |
| `divergenceWeight` | `double` | `>= 0` | Divergence regularization |
| `curlWeight` | `double` | `>= 0` | Curl regularization |
| `landmarkWeight` | `double` | `>= 0` | Landmark constraint weight |
| `imageWeight` | `double` | `>= 0` | Image similarity weight |
| `consistencyWeight` | `double` | `>= 0` | Bidirectional consistency weight |
| `stopThreshold` | `double` | `> 0` | Relative stop criterion per level |

### `computeTransformationBatch(...)`

```groovy
Transformation transform = bUnwarpJ_.computeTransformationBatch(
    targetImp,
    sourceImp,
    null,
    null,
    params
)
```

Use `null` masks when no mask image is provided.

Expected inputs:

- `targetImp` and `sourceImp` are 2D `ImagePlus` objects.
- Use single-plane images in this repo's scripted workflow.
- `Mono` mode defines only the direct source-to-target transformation.

### Get the registered results

```groovy
ImagePlus direct = transform.getDirectResults()
ImagePlus inverse = transform.getInverseResults()
```

Guidance:

- `getDirectResults()` returns the registered source image in target space.
- `getInverseResults()` is available for `Fast` and `Accurate` modes.
- In `Mono` mode, treat only the direct result as defined.

### Save elastic transformation files

```groovy
transform.saveDirectTransformation("/path/direct_elastic.txt")
transform.saveInverseTransformation("/path/inverse_elastic.txt")
```

Guidance:

- Always use `saveDirectTransformation(...)` for the source-to-target transform.
- Use `saveInverseTransformation(...)` only after bidirectional registration (`Fast` or `Accurate`).
- Do not call `saveInverseTransformation(...)` in `Mono` mode.

### Reapply a saved direct elastic transform

```groovy
def sourceCopy = new Duplicator().run(sourceImp)
bUnwarpJ_.applyTransformToSource("/path/direct_elastic.txt", targetImp, sourceCopy)
// `sourceCopy` is now the warped image. Use it directly:
sourceCopy.setTitle("warped")
IJ.saveAsTiff(sourceCopy, "/path/warped.tif")
```

Behavior:

- `applyTransformToSource(...)` updates `sourceCopy` **in place** and returns
  `null` / `void`. **Do NOT capture or use its return value.**

  ```groovy
  // WRONG — returns null in this build, downstream code will fail with
  //         "bUnwarpJ returned null warped image(s)":
  def warped = bUnwarpJ_.applyTransformToSource(transformPath, targetImp, sourceCopy)

  // CORRECT — call for the side effect; sourceCopy IS the warped image:
  bUnwarpJ_.applyTransformToSource(transformPath, targetImp, sourceCopy)
  // sourceCopy is now warped; save/show it directly.
  ```
- The transformed copy matches the target image geometry.
- This is the safer scripted reapply path than the title-based macro methods.

### Minimal complete example

```groovy
import bunwarpj.Param
import bunwarpj.bUnwarpJ_
import ij.IJ
import ij.plugin.Duplicator

def target = IJ.openImage("/data/target.tif")
def source = IJ.openImage("/data/source.tif")

def params = new Param(
    1,      // Accurate
    0,      // full resolution
    1,      // Coarse
    3,      // Very Fine
    0.0,    // divergence
    0.0,    // curl
    0.0,    // landmark
    1.0,    // image similarity
    10.0,   // consistency
    0.01    // stop threshold
)

def transform = bUnwarpJ_.computeTransformationBatch(target, source, null, null, params)
def direct = transform.getDirectResults()

transform.saveDirectTransformation("/data/direct_elastic.txt")
IJ.saveAsTiff(direct, "/data/registered_source.tif")

def reapplied = new Duplicator().run(source)
bUnwarpJ_.applyTransformToSource("/data/direct_elastic.txt", target, reapplied)
IJ.saveAsTiff(reapplied, "/data/reapplied_source.tif")
```

### `alignImagesBatch(...)`

```groovy
def results = bUnwarpJ_.alignImagesBatch(targetImp, sourceImp, null, null, params)
def direct = results[0]
```

Use this shortcut when you only need the registered image result and do not need
to save transformation files. In `Mono` mode, the second array slot is `null`.

## Official-Doc Macro Syntax

The plugin page documents the main dialog as an ImageJ macro call:

```groovy
IJ.run("bUnwarpJ",
    "source_image=Source " +
    "target_image=Target " +
    "registration=Accurate " +
    "image_subsample_factor=0 " +
    "initial_deformation=[Very Coarse] " +
    "final_deformation=Fine " +
    "divergence_weight=0 " +
    "curl_weight=0 " +
    "landmark_weight=0 " +
    "image_weight=1 " +
    "consistency_weight=10 " +
    "stop_threshold=0.01 " +
    "save_transformations " +
    "save_direct_transformation=/path/source_to_target.txt " +
    "save_inverse_transformation=/path/target_to_source.txt")
```

Use this syntax only when Fiji can construct the bUnwarpJ dialog and operate on
named image windows.

### Official title-based macro calls

The plugin page also documents title-based static calls such as:

```javascript
call("bunwarpj.bUnwarpJ_.loadElasticTransform",
     "/path/source_to_target.txt",
     "target-image.tif",
     "source-image.tif");
```

These methods are useful in interactive Fiji sessions where the target and source
windows are already shown and their titles are stable.

## Exclusions and Caveats

- bUnwarpJ is a 2D registration plugin. It does not perform 3D registration.
- If you pass stacks in the GUI, bUnwarpJ treats the second slice as a mask rather
  than a 3D volume.
- In this repo's headless Groovy execution, `IJ.run("bUnwarpJ", "...")` is not the
  recommended automation path because it constructs `MainDialog`.
- Title-based methods such as `loadElasticTransform(...)` and `loadRawTransform(...)`
  depend on open window titles and are not the primary scripted workflow here.
- Raw-transform conversion, comparison, composition, and inversion utilities are
  documented on the official plugin page but are outside this skill's validated
  workflow.
