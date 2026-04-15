# Labkit — Groovy API Guide

This file contains only the Groovy path used by this skill.

## Plugin Call

```groovy
#@ File classifierFile
#@ CommandService command

import ij.ImagePlus
import sc.fiji.labkit.ui.plugin.SegmentImageWithLabkitIJ1Plugin

def module = command.run(SegmentImageWithLabkitIJ1Plugin, true,
    "input",          imp,
    "segmenter_file", classifierFile,
    "use_gpu",        false
).get()

ImagePlus resultImp = module.getOutput("output")
```

## Preconditions

- The classifier must already exist and must have been saved from the Labkit GUI.
- The target images should be similar to the representative image used for training.
- Brightness and contrast should be normalized across the batch.
- Use a fresh TIFF output path when saving the segmentation result.

## Minimal Pattern

```groovy
#@ File (label = "Input image") inputFile
#@ File (label = "Labkit classifier") classifierFile
#@ File (label = "Output TIFF", style = "save") outputFile
#@ CommandService command

import ij.IJ
import ij.ImagePlus
import sc.fiji.labkit.ui.plugin.SegmentImageWithLabkitIJ1Plugin

ImagePlus imp = IJ.openImage(inputFile.absolutePath)

def module = command.run(SegmentImageWithLabkitIJ1Plugin, true,
    "input",          imp,
    "segmenter_file", classifierFile,
    "use_gpu",        false
).get()

ImagePlus resultImp = module.getOutput("output")
IJ.saveAs(resultImp, "Tiff", outputFile.absolutePath)
```

## Standard ImageJ Helpers

These are standard Fiji/ImageJ calls. They are not Labkit-specific.

| Purpose | Groovy call |
|---------|-------------|
| Open an image from disk | `IJ.openImage(path)` |
| Run the Labkit IJ1 plugin | `command.run(SegmentImageWithLabkitIJ1Plugin, true, ...)` |
| Read the plugin output | `module.getOutput("output")` |
| Save a TIFF result | `IJ.saveAs(resultImp, "Tiff", path)` |
| Close a window without save prompts | `imp.changes = false; imp.close()` |

## What This Guide Does Not Claim

- No scripted training API for creating a classifier.
- No Labkit parameter keys beyond `input`, `segmenter_file`, `use_gpu`, and `output` for this plugin call.
- No macro syntax for saving labelings, saving classifiers, or opening the full Labkit UI from Groovy.

Use `UI_GUIDE.md` and `UI_WORKFLOW_PIXEL_CLASSIFICATION.md` for those steps.
