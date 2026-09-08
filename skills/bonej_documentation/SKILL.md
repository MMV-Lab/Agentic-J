---
name: bonej_documentation
description: >-
  BoneJ is a Fiji/ImageJ plugin suite for trabecular bone and porous-structure analysis from binary 2D and 3D images. This skill documents the validated Groovy automation path in this repo: clearing the shared BoneJ table, running Thickness, Area/Volume fraction, Connectivity (Modern), Surface fraction, Fractal dimension, Anisotropy, Skeletonise, and Analyse Skeleton through SciJava CommandService, plus a validated lower-level surface-area path for the local Fiji runtime. Read the files listed at the end of this SKILL for exact class calls, menu paths, and scope limits.
---

## Primary Use Case in This Skill Set

Binary 3D stack
  -> BoneJ Thickness
  -> Area/Volume fraction
  -> optional Connectivity (Modern)
  -> CSV summary + thickness maps

Additional validated coverage:

- Surface fraction
- Fractal dimension
- Anisotropy on a representative 3D directional structure
- Surface area through marching-cubes + boundary-size ops
- Skeletonise
- Analyse Skeleton

## Verified Automation Boundary

- Container-validated:
  - `org.bonej.wrapperPlugins.tableTools.SharedTableCleaner`
  - `org.bonej.wrapperPlugins.ThicknessWrapper`
  - `org.bonej.wrapperPlugins.ElementFractionWrapper`
  - `org.bonej.wrapperPlugins.ConnectivityWrapper`
  - `org.bonej.wrapperPlugins.SurfaceFractionWrapper`
  - `org.bonej.wrapperPlugins.FractalDimensionWrapper`
  - `org.bonej.wrapperPlugins.AnisotropyWrapper`
  - `org.bonej.wrapperPlugins.SkeletoniseWrapper`
  - `org.bonej.wrapperPlugins.AnalyseSkeletonWrapper`
  - `convertService.convert(imagePlus, ImgPlus.class)` for ImgPlus-only wrappers
- lower-level surface-area path:
  - `opService.convert().bit(...)`
  - `Functions.unary(..., MarchingCubes.class, ...)`
  - `Functions.unary(..., BoundarySize.class, ...)`
- Official-doc or UI-only surface not adopted as a direct runnable wrapper API in this skill:
  - `org.bonej.wrapperPlugins.SurfaceAreaWrapper`
  - legacy UI tools such as `Slice Geometry`

## Scope Limits

- This skill assumes BoneJ is installed from the BoneJ update site in Fiji.
- The checked-in Groovy workflow expects an 8-bit binary stack for final measurements. It can threshold a non-binary input for convenience, but threshold choice is outside BoneJ's measurement model.
- In this Fiji runtime, `SurfaceAreaWrapper` canceled silently on validated 3D binary inputs. The checked-in scripting path therefore uses BoneJ's underlying marching-cubes and boundary-size ops instead of the wrapper itself.
- `AnisotropyWrapper` is sensitive to sample geometry. It failed on a duplicated single-slice validation stack and succeeded on a genuine 3D directional rod lattice.
- This skill does not document a macro-recorded `IJ.run(...)` string for the modern BoneJ wrappers. The validated scripting path is `CommandService`.

## File Index

| File | Contents |
|------|----------|
| `SCRIPT_API.md` | Validated BoneJ `CommandService` calls, the lower-level surface-area workaround, parameter names, and runtime caveats |
| `GROOVY_WORKFLOW_THICKNESS_AND_FRACTION.groovy` | Runnable Fiji workflow for binary-stack preparation, Thickness, Area/Volume fraction, optional Connectivity, and CSV export |
| `GROOVY_WORKFLOW_STRUCTURE_METRICS.groovy` | Runnable Fiji workflow for Surface fraction, Fractal dimension, optional Anisotropy, and validated manual Surface area export |
| `UI_GUIDE.md` | Verified BoneJ menu paths, input rules, and UI scope notes |
| `UI_WORKFLOW_THICKNESS_AND_FRACTION.md` | Manual step-by-step workflow for Thickness plus Area/Volume fraction, with optional Connectivity |
