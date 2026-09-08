# ImageJ: Morphological operations

## Introduction

ImageJ's **Process → Binary** submenu contains various useful commands for working with binary images, including some of the morphological operations we've looked at.

However, there are other useful morphological operations lurking elsewhere -- although most require extra plugins, or switching to Fiji.

## Erosion, dilation, opening & closing

**Process → Binary** contains the commands **Erode**, **Dilate**, **Open** and **Close-** commands.

These are relevant here, but my advice is to avoid them.
By default they work with fixed 3×3 pixel neighborhoods, but they *could* do something different if someone has been messing about with the **Iterations (1-100)** or **Count (1-8)** options under **Process → Binary → Options...** -- and this unpredictability could well cause trouble.

To perform erosion, dilation, opening and closing with more control and possibly larger neighborhoods, I strongly prefer to use the **Process → Filters → Maximum...** and **Process → Filters → Minimum...** commands, combining them if necessary.

> **📌 Morphological operations in Fiji**
>
> Fiji contains **Process → Morphology → Gray Morphology**, which provides a more flexible implementation of erosion, dilation, opening and closing using a variety of shapes for both grayscale and binary images.
>
> You can also find the plugin for ImageJ at https://imagej.nih.gov/ij/plugins/gray-morphology.html

## Outlines, holes & skeletonization

The **Process → Binary → Outline** command, predictably, removes all the interior pixels from
2D binary objects, leaving only the perimeters (the figureA).

**Process → Binary → Fill Holes** would then fill these interior pixels in again, or indeed fill in any background pixels that are completely surrounded by foreground pixels (the figureB).

**Process → Binary → Skeletonize** shaves off all the outer pixels of an object until only a connected central line remains (the figureC).

> **📌 Analyzing skeletons**
>
> If you are analyzing linear structures (e.g. blood vessels, neurons), then this command or those in Fiji's **Plugins → Skeleton →** submenu may be helpful.

![The effects of the **Outline**, **Fill holes** and **Skeletonize** commands.](assets/2.5/gen_fig-outline-fill-skeleton.png)

*Figure —* The effects of the **Outline**, **Fill holes** and **Skeletonize** commands.

> **❓ Question**
> The outline of an object in a binary image can also be determined by applying one other morphological operation to a duplicate of the image, and then using the **Image Calculator**.
> How?

<details>
<summary>Show solution</summary>

To outline the objects in a binary image, you can simply calculate the difference between the original image and an eroded (or dilated, if you want the pixels just beyond the objects) duplicate of the image.

</details>

## Other morphological operations

ImageJ doesn't contain an implementation of morphological reconstruction, and therefore doesn't support all the extra operations that derive from it.

However, there's an extremely library called [**MorphoLibJ**](https://imagej.net/plugins/morpholibj) that can be added to ImageJ or Fiji, which contains morphological reconstruction and much more.

Check out the excellent documentation at https://imagej.net/plugins/morpholibj for more details.
