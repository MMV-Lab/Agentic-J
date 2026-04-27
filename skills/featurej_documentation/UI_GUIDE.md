# FeatureJ - UI Guide

This guide keeps to the FeatureJ menu surface that is either documented on the
official FeatureJ pages or confirmed in the installed `plugins.config`.

## Installation

Install FeatureJ from the `ImageScience` update site:

1. Open `Help > Update...`
2. Click `Manage update sites`
3. Enable `ImageScience`
4. Click `Apply changes`
5. Restart Fiji

Manual installation is also possible by placing `FeatureJ_.jar` in Fiji's
`plugins/` directory and `imagescience.jar` in Fiji's `jars/` directory.

## Menu Layout

Verified menu paths:

- `Plugins > FeatureJ > FeatureJ Derivatives`
- `Plugins > FeatureJ > FeatureJ Edges`
- `Plugins > FeatureJ > FeatureJ Hessian`
- `Plugins > FeatureJ > FeatureJ Laplacian`
- `Plugins > FeatureJ > FeatureJ Options`
- `Plugins > FeatureJ > FeatureJ Panel`
- `Plugins > FeatureJ > FeatureJ Statistics`
- `Plugins > FeatureJ > FeatureJ Structure`
- `Help > About Plugins > FeatureJ...`

## Input Requirements

Common requirement from the official docs and installed plugin source:

- the active image must be grayscale
- supported ImageJ types are `8-bit`, `16-bit`, and `32-bit` grayscale
- stacks, hyperstacks, and grayscale 5D images are accepted

Practical note:

- `Hessian` and `Structure` return `2` eigenimages in 2D and `3` in 3D
- `Edges` and `Laplacian` switch between 2D and 3D behavior based on whether the `z` dimension has size `1`

## Derivatives

Menu path: `Plugins > FeatureJ > FeatureJ Derivatives`

Purpose:

- compute Gaussian-scaled partial derivatives up to order `10` in `x`, `y`, and `z`

Verified controls:

- `x-Order`
- `y-Order`
- `z-Order`
- `Smoothing scale`

Expected output:

- one derivative image

## Edges

Menu path: `Plugins > FeatureJ > FeatureJ Edges`

Purpose:

- compute a Canny-style edge response from the gradient magnitude, optional non-maximum suppression, and optional thresholding

Verified controls:

- `Compute gradient-magnitude image`
- `Smoothing scale`
- `Suppress non-maximum gradients`
- `Lower threshold value`
- `Higher threshold value`

Expected output:

- one image window
- continuous gradient magnitude if thresholds are empty
- binary edge map if one or two thresholds are supplied

## Laplacian

Menu path: `Plugins > FeatureJ > FeatureJ Laplacian`

Purpose:

- compute the Laplacian of the image and optionally detect zero-crossings

Verified controls:

- `Compute Laplacian image`
- `Smoothing scale`
- `Detect zero-crossings`

Expected output:

- one image window
- signed Laplacian response if zero-crossings are disabled
- binary zero-crossing map if enabled

## Hessian

Menu path: `Plugins > FeatureJ > FeatureJ Hessian`

Purpose:

- compute eigenvalues of the Hessian tensor

Verified controls:

- `Largest eigenvalue of Hessian tensor`
- `Middle eigenvalue of Hessian tensor`
- `Smallest eigenvalue of Hessian tensor`
- `Absolute eigenvalue comparison`
- `Smoothing scale`

Expected outputs:

- in 2D: largest and smallest eigenvalue images
- in 3D: largest, middle, and smallest eigenvalue images

## Structure

Menu path: `Plugins > FeatureJ > FeatureJ Structure`

Purpose:

- compute eigenvalues of the structure tensor

Verified controls:

- `Largest eigenvalue of structure tensor`
- `Middle eigenvalue of structure tensor`
- `Smallest eigenvalue of structure tensor`
- `Smoothing scale`
- `Integration scale`

Expected outputs:

- in 2D: largest and smallest eigenvalue images
- in 3D: largest, middle, and smallest eigenvalue images

## Statistics

Menu path: `Plugins > FeatureJ > FeatureJ Statistics`

Purpose:

- compute gray-value statistics over the full image or an ROI

Verified metric controls:

- `Minimum`
- `Maximum`
- `Mean`
- `Median`
- `Elements`
- `Mass`
- `Variance`
- `Mode`
- `S-deviation`
- `A-deviation`
- `L1-norm`
- `L2-norm`
- `Skewness`
- `Kurtosis`

Verified additional controls:

- `Clear previous results`
- `Image name displaying`
- `Channel numbering`
- `Time frame numbering`
- `Slice numbering`
- `Decimal places`

ROI note:

- area ROIs are supported
- line ROIs are not supported

Expected output:

- entries appended to the ImageJ results table

## Options

Menu path: `Plugins > FeatureJ > FeatureJ Options`

Purpose:

- set persistent package-wide defaults

Verified controls:

- `Isotropic Gaussian image smoothing`
- `Close input images after processing`
- `Save result images before closing`
- `Progress indication`
- `Log messaging`

Behavior note:

- these settings are written to ImageJ preferences and affect later manual FeatureJ runs

## Panel

Menu path: `Plugins > FeatureJ > FeatureJ Panel`

Purpose:

- open a quick-launch panel for the main FeatureJ tools

This skill does not treat the panel itself as an automation target.

## About / Help

Menu path: `Help > About Plugins > FeatureJ...`

Purpose:

- show package information and provide a path to the FeatureJ documentation

This skill treats the menu entry as documentation surface, not as a scripted workflow step.
