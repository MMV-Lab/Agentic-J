# Morphological operations

> **📌 Chapter outline**
>
> * **Morphological operations** can be used to refine or modify the shapes of objects in images
> * Many morphological operations can be applied to **binary images** to improve an image segmentation
> * **Grayscale morphological operations** can also be used as processing steps before binarization, or to help identify regional maxima and minima

## Introduction

Image filters and thresholds enable us to detect structures of various shapes and sizes for different applications.
Nevertheless, despite our best efforts, the binary images produced by our thresholds often still contain inaccurate or undesirable detected regions.
They could benefit from some extra cleaning up.

At this stage, we are primarily working with shapes -- morphology -- so most of the techniques we describe here are often called **morphological operations**.

## Morphological operations using rank filters

![Overview of erosion, dilation, opening and closing. The original image is shown at the top, while the processed part is at the bottom in each case.](assets/2.5/gen_fig-erode-dilate-open.png)

*Figure —* Overview of erosion, dilation, opening and closing. The original image is shown at the top, while the processed part is at the bottom in each case.

### Erosion & dilation

Our first two morphological operations, **erosion** and **dilation**, are actually identical to minimum and maximum filtering respectively, described [in the previous chapter](sec_filters_rank).
The names erosion and dilation are used more often when speaking of binary images, but the operations are the same irrespective of the kind of image.

> **📌 Structuring elements**
>
> The neighborhood used to calculate the result for each pixel is defined by a **structuring element**.
> This is similar to a [filter kernel](sec_filters_linear), except that it only has values 0 and 1 (for ignoring or including the neighborhood pixel, respectively).

> **🗒️ Aside**
>
> Here, we assume the background value in our binary image is 0 (black) and foreground is 1 (white).

**Erosion** will make objects in the binary image smaller, because a pixel will be set to the background value if _any_ other pixels in the neighborhood are background.
This can split single objects into multiple pieces.

Conversely, **dilation** makes objects bigger, since the presence of a single foreground pixel anywhere in the neighborhood will result in a foreground output.
This can also cause objects to merge.

![The effects of erosion and dilation on a binary image of small structures.](assets/2.5/gen_fig-erode-dilate-spots.png)

*Figure —* The effects of erosion and dilation on a binary image of small structures.

### Opening & closing

The fact that erosion and dilation alone affect sizes can be a problem: we may like their abilities to merge, separate or remove objects, but prefer that they had less impact upon areas and volumes.
Combining both operations helps achieve this.

**Opening** consists of an erosion followed by a dilation.
It therefore first shrinks objects, and then expands whatever remains to _approximately_ its original size.

Such a process is not as pointless as it may first sound.
If erosion causes very small objects to completely disappear, clearly the dilation cannot make them reappear: they are gone for good.
Barely-connected objects separated by erosion are also not reconnected by the dilation step.

**Closing** is the opposite of opening, i.e. a dilation followed by an erosion, and similarly changes the shapes of objects.
The dilation can cause almost-connected objects to merge, and these often then remain merged after the erosion step.
If you wish to count objects, but they are wrongly subdivided in the segmentation, closing may help make the counts more accurate.

![The effects of opening and closing on a binary image of small structures. Unlike when using erosion or dilation alone, the sizes of objects are largely preserved although the contours are modified. Opening has the effect of completely removing the smallest or thinnest objects.](assets/2.5/gen_fig-open-close-spots.png)

*Figure —* The effects of opening and closing on a binary image of small structures. Unlike when using erosion or dilation alone, the sizes of objects are largely preserved although the contours are modified. Opening has the effect of completely removing the smallest or thinnest objects.

### Boundaries & outlines

We can make use of the operations above to identify outlines in a binary image.
To do this, we first need a clear definition of what we mean by 'outline'.

The **inner boundary** may be defined as *the foreground pixels that are adjacent to background pixels*.
We can determine the inner boundary by
* Duplicating the binary image
* Eroding with a 3×3 structuring element
* Subtracting the eroded image from the original

The **outer boundary** may be defined as *the background pixels that are adjacent to foreground pixels*.
We can determine the outer boundary by
* Duplicating the binary image
* Dilating with a 3×3 structuring element
* Subtracting the original image from the dilated image

> **📌 Thicker boundaries**
>
> There's no reason to limit outlines to being 1 pixel thick.
> Choosing a larger structuring element makes it possible create thicker outlines.
> We might also subtract an eroded image from a dilated image to identify a thicker boundary that contains both inner and outer pixels.
>
> One application of creating thick boundaries in microscopy images of cells is to generate a binary image of the nuclei, and then a second binary image representing a ring around the nucleus.
> This makes it possible to make measurements that are likely to be within the cytoplasm, just outside the nucleus, without the task of identifying the full area of the cell -- which is often difficult if the cell or membrane are not clearly visible.

![Calculating inner and outer boundaries, using erosion or dilation. The radius of the structuring element can be used to tune the boundary thickness.](assets/2.5/gen_fig-binary-outlines.png)

*Figure —* Calculating inner and outer boundaries, using erosion or dilation. The radius of the structuring element can be used to tune the boundary thickness.

### Finding local minima & maxima

Erosion and dilation can be used to find pixels that are **local maxima** or **local minima** very easily, with the caveat that the results are inexact and often unusable.
Nevertheless, the trick works 'well enough' sufficiently often to be worth knowing.

Here, we focus on maxima; the process for detecting local minima is identical, except that either the image should be inverted or erosion used instead of dilation.

A local maximum can be defined as a pixel with a value greater than all its neighbors, or a connected group of pixels with the same higher value than the surrounding pixels.
An easy way to detect these pixels is to dilate the image with 3×3 maximum filter, and check for pixel values that are unchanged (i.e. where the pixel was already a maximum within its neighborhood).

This is inexact because it does not *only* identify maxima; it also detections some 'plateaus' where pixels have identical values to their neighbors.
In practice, this is not always a problem because noise can make plateaus virtually non-existent for many real-world images (at least ones that haven't been clipped).

A bigger problem is that the approach often identifies far too many maxima to be useful (the figure).

![Identifying local maxima with the help of a 3×3 dilation tends to find too many maxima to be useful.](assets/2.5/gen_fig-morph-simple-maxima.png)

*Figure —* Identifying local maxima with the help of a 3×3 dilation tends to find too many maxima to be useful.

We can reduce these by either increasing the size of the maximum filter (therefore requiring pixels to be maximal across a larger region), or by pre-smoothing the image (usually with a [Gaussian filter](sec_filters_gaussian)).
However, tuning the parameters becomes difficult.

We will see an alternative approach that is often more intuitive in sec_h_extrema.

![Identifying local maxima with the help of a larger dilation (here, 7×7 pixels) can sometimes give better results than using a smaller dilation the figure.](assets/2.5/gen_fig-morph-simple-maxima-bigger.png)

*Figure —* Identifying local maxima with the help of a larger dilation (here, 7×7 pixels) can sometimes give better results than using a smaller dilation the figure.

## More morphological operations

### Area opening

**Area opening** is similar to *opening*, except it avoids the need for any kind of maximum or minimum filtering.

It works by identifying [**connected components** in the binary image](sec_binary_labeled), which are contiguous regions of foreground pixels.
For each connected component, the number of pixels is counted to give an area in px².
If the area of a component falls below a specified area threshold, the pixels for that component are set to the background, i.e. the component is removed.

*Area opening* is often preferable to *opening*, because it has *no impact* on the shape of any structures larger than the area threshold.
It simply applies a minimum area threshold, removing everything smaller.

![Using area opening to remove small objects.](assets/2.5/gen_fig-area-open-spots.png)

*Figure —* Using area opening to remove small objects.

### Filling holes

**Filling holes** involves identifying connected components of *background pixels* that are entirely surrounded by foreground pixels.
These components are then 'flipped' to become foreground pixels instead.

Should we then want to identify the holes themselves, we can subtract the original image from the filled image.

![Filling holes in a binary image. Image subtraction makes it possible to extract the holes themselves.](assets/2.5/gen_fig-fill-holes-cell.png)

*Figure —* Filling holes in a binary image. Image subtraction makes it possible to extract the holes themselves.

![Small holes filled.](assets/2.5/gen_2.5_9.png)

*Figure —* Small holes filled.

> **❓ Question**
> We don't always want to fill *all* the holes within a binary image, but rather only the smaller ones.
> Can you think of a way to fill *only holes smaller than 1000 px²*, using area opening?
>
> You'll need at least one operation described in previous chapter.

<details>
<summary>Show solution</summary>

One way to fill holes below a fixed size:

* Invert the binary image
* Perform area opening with an area threshold of 1000 px²
* Invert the result

</details>

### Thinning & skeletonization

**Thinning** and **skeletonization** are related operations that aim to 'thin down' objects in a binary image to just their centerlines.
They are particularly useful with filamental or tube-like structures, such as axons or blood vessels.

![The effects of thinning and skeletonization on a binary image.](assets/2.5/gen_fig-binary-thinning.png)

*Figure —* The effects of thinning and skeletonization on a binary image.

> **📌 What's the difference between thinning & skeletonization?**
>
> The truth is: I'm not entirely sure.
> There is quite a bit of overlap in the literature, and I've seen the same algorithm referred to by both names.
> Furthermore, there are different thinning algorithms that give different results; the situation is similar for skeletonization algorithms.
>
> Software occasionally offers both thinning and skeletonization, but often just offers one or the other.
> It's worth trying any thinning/skeletonization methods available to see which performs best for any particular application.

## Morphological reconstruction

**Morphological reconstruction** is a somewhat advanced technique that underpins several powerful image processing operations.
It's useful with both grayscale and binary images.

Morphological reconstruction requires two images of the same size: a **marker** image and a **mask** image.
The pixel in the *mask* image should all have values greater than or equal to the corresponding pixels in the *marker* image.

The reconstruction algorithm progressively *dilates* the marker image (e.g. applies a 3×3 maximum filter), while constraining the marker to remain 'within' the mask; that is, the pixel values in the marker are never allowed to exceed the values in the mask.
This dilation is repeated iteratively until the marker cannot change any further without exceeding the mask.
The output is the new marker image, after all the dilations have been performed.

Some examples will help demonstrate how this works and why it's useful.
The crucial difference in the methods below is how the marker and mask images are created.

### Hysteresis thresholding

One use of morphological reconstruction is to implement a **double threshold**, also known as **hysteresis thresholding**.

> **🗒️ Aside**
>
> For *low threshold* and *high threshold*, I assume we're detecting light structures on a dark background.

This involves defining both a **low threshold** and a **high threshold.**
The low threshold operates like any [global threshold](chap_thresholding) to identify regions.
However, a region is discarded from the binary image if it does not also contain at least one pixel that exceeds the high threshold.

This is achieved using morphological reconstruction by defining the *marker* as all pixels exceeding the high threshold, and the *mask* as all pixels exceeding the low threshold.
The markers will expand to fill the mask regions that contain them.
But any mask regions that don't contain marker pixels are simply ignored.

![Applying a hysteresis threshold to an image. The size and area of the objects detected by this method are determined by the low threshold, but at least one of the pixel values within the object must exceed the high threshold. This slightly mitigates the problem of a single global threshold having [a huge impact on analysis results](chap_thresholding), by the same threshold simultaneously influencing both what is detected and its size.](assets/2.5/gen_fig-hysteresis-threshold-spots.png)

*Figure —* Applying a hysteresis threshold to an image. The size and area of the objects detected by this method are determined by the low threshold, but at least one of the pixel values within the object must exceed the high threshold. This slightly mitigates the problem of a single global threshold having [a huge impact on analysis results](chap_thresholding), by the same threshold simultaneously influencing both what is detected and its size.

### H-Maxima & H-Minima

We [saw previously](fig-morph_simple_maxima) that we could (kind of) identify local maxima in a very simple way using an image dilation, but the results are often too inaccurate to be useful.

**H-Maxima** and **H-Minima** can help us overcome this.
These operations both require only one intuitive parameter: they enable us to identify maxima or minima using a local intensity threshold *H*.

This is achieved using morphological reconstruction.
For H-maxima, the process is:
* Set the original grayscale image as the *mask*
* Subtract *H* from the mask to create the *markers*
* Apply morphological reconstruction using the markers and mask
* Subtract the reconstruction result from the *mask*
* Threshold the subtracted image with a global threshold of *H*

The main steps are illustrated in the figure.
We can apply the same process to an inverted image to find *H-minima*.

![Calculating H-maxima using morphological reconstruction. Here, *H* is set (arbitrarily) to be the image standard deviation.](assets/2.5/gen_fig-morph-h-maxima.png)

*Figure —* Calculating H-maxima using morphological reconstruction. Here, *H* is set (arbitrarily) to be the image standard deviation.

### Opening & closing by reconstruction

H-maxima and H-minima use morphological reconstruction to effectively generate a background image that can be subtracted from the original.
We do this by subtracting a constant *H*, which acts as a local intensity threshold.

We can also use morphological reconstruction to generate a background image based upon spatial information, rather than an intensity threshold *H*, by using **opening by reconstruction**.
This effectively introduces a size component into our local threshold.
**Closing by reconstruction** is an analogous operation that can be defined using morphological closing.

The starting point for opening by reconstruction is a *morphological opening* [as defined above](sec_morph_opening_closing), i.e. an erosion followed by a dilation.
This defines the marker image.
The original image is used as the mask.

![Using opening by reconstruction to obtain a background estimate. The estimate can be subtracted from an image before applying a global threshold.](assets/2.5/gen_fig-morph-reconstruct-opening.png)

*Figure —* Using opening by reconstruction to obtain a background estimate. The estimate can be subtracted from an image before applying a global threshold.

As before, opening alone removes structures that are smaller than the structuring element, while slightly affecting the shapes of everything else.
Opening by reconstruction essentially adds some further (constrained) dilations so that the structures that were *not* removed are more similar to how they were originally.
This can make opening by reconstruction more attractive for generating background images that will be used for subtraction.

Opening by reconstruction can also be applied to binary images as an alternative to *opening* and *area opening*.
Like area opening, opening by reconstruction is able to remove some objects while retaining the shapes of larger objects exactly.

![Using opening by reconstruction to remove small (and thin) objects from a binary image, while retaining the original shape of everything that remains.](assets/2.5/gen_fig-morph-reconstruct-opening-binary.png)

*Figure —* Using opening by reconstruction to remove small (and thin) objects from a binary image, while retaining the original shape of everything that remains.
