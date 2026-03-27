---
name: image_publication_standarts
description: This SKILL covers best practices for preparing microscopy images for publication, including resolution, compression, metadata, and file formats. It provides guidelines for ensuring that images are clear, accurate, and compliant with journal requirements. ONLY to be used by the imagej_coder agent when the task explicitly involves saving final output images for publication or user inspection. Do NOT load or apply these standards for preprocessing steps or intermediate image manipulations.
---

─────────────────────────────
IMAGE PUBLICATION STANDARDS 
──────────────────────────────
When saving images for publication or user inspection, you MUST follow these rules:

IMAGE FORMAT & SAVING:
1. ALWAYS save images with LOSSLESS compression (TIFF format, NO JPEG).
  - Use: `IJ.saveAs(imp, "Tiff", path)`
  - NEVER use lossy formats unless explicitly requested.

2. SCALE BARS (Minimal requirement):
  - ALWAYS add scale bars to final output images before saving.
  - Use: `IJ.run(imp, "Scale Bar...", "width=50 height=4 font=14 color=White background=None location=[Lower Right]")`
  - Adjust width based on image calibration (use 10-20% of image width).
  - Document the scale bar settings in your script description.

3. IMAGE ADJUSTMENTS:
  - If you adjust brightness/contrast, DOCUMENT the exact values in the script description.
  - Example: "Applied B&C: min=100, max=4095"
  - For image comparisons, apply the SAME adjustments to all images.
  - Use: `IJ.run(imp, "Brightness/Contrast...", "...")` with explicit min/max values.

MULTI-CHANNEL IMAGES:
4. When processing multi-channel images:
  - ALWAYS save individual grayscale channels separately in addition to merged RGB.
  - Save channels to: processed_images/channels/[channel_name].tif
  - Save merged to: processed_images/montages/merged.tif
  - Example code:
    ```groovy
    for (int i = 1; i <= nChannels; i++) {
        imp.setC(i)
        def channel = new Duplicator().run(imp, i, i, 1, 1, 1, 1)
        IJ.saveAs(channel, "Tiff", channelsDir + "channel_" + i + ".tif")
    }
    ```

5. COLOR-BLIND ACCESSIBILITY:
  - For merged multi-channel images, use green/magenta or cyan/red/yellow.
  - AVOID red/green combinations alone.
  - If creating pseudocolored images, ALSO save a grayscale version.

ANNOTATIONS:
6. When adding annotations (arrows, ROIs, labels):
  - Ensure annotations are LEGIBLE (minimum line width: 2, minimum font size: 12).
  - Use high-contrast colors (white on dark backgrounds, black on light).
  - Never obscure key data with annotations.
  - Document all annotations in the script description.

METADATA PRESERVATION:
7. When duplicating or processing images:
  - PRESERVE calibration: `imp2.setCalibration(imp.getCalibration())`
  - PRESERVE slice labels if present
  - For batch processing, verify calibration is maintained

DOCUMENTATION REQUIREMENTS:
8. Your script description MUST include:
  - All image adjustment parameters (threshold values, filter sizes, B&C settings)
  - Scale bar settings (width, font, position)
  - Channel information (which channel is what marker/staining)
  - Output file locations and formats
  - Example: "Segmented nuclei using Otsu threshold (value=1200). Applied Gaussian blur σ=2. 
              Added 50μm scale bar (white, lower right). Saved as 16-bit TIFF to processed_images/."