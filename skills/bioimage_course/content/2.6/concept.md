# Image transforms

> **📌 Chapter outline**
>
> * The **watershed transform** can be used to split structures using intensity values
> * The **distance transform** calculates the distance between foreground and background pixels in a binary image
> * The **distance & watershed transforms** can be combined to separate round structures

## Introduction

An **image transform** converts an image into some other form, in which the pixel values can have a (sometimes very) different interpretation.

There are lots of ways to transform an image.
We will focus on two that are especially useful for bioimage segmentation and analysis: the distance transform and the watershed transform.
We will briefly introduce both, before then showing how they can be used in combination.

## The distance transform

The **distance transform** (sometimes called the **Euclidean distance transform**) replaces each pixel of a binary image with the distance to the closest background pixel.
If the pixel itself is already part of the background then this is zero.
The result is an image called a **distance map**.

![A binary image and its corresponding distance map, including pixel values as an overlay.](assets/2.6/gen_fig-morph-distance-detail.png)

*Figure —* A binary image and its corresponding distance map, including pixel values as an overlay.

A natural question when considering the distance transform is: *why*?

Although its importance may not be initially obvious, we will see that creative uses of the distance transform can help solve some other problems rather elegantly.

For example, eroding or dilating binary images by a large amount can be very slow, because we have to use large maximum or minimum filters.
However, erosion and dilation can be computed from a distance map very efficiently simply by applying a global threshold.
This can be much faster in practice.

![Implementing erosion (C) and dilation (F) of binary images by thresholding distance maps.](assets/2.6/gen_fig-morph-distance.png)

*Figure —* Implementing erosion (C) and dilation (F) of binary images by thresholding distance maps.

But the distance map contains useful information that we can use in other ways.

For example, we can also use distance maps to estimate the **local thickness** of a structure.
An application of this would be to assess blood vessel diameters.
If we have a binary image representing a vessel, we can generate both a distance map and a thinned binary image.
The distance map values corresponding to foreground pixels in the thinned image provide a local estimate of the vessel radius at that pixel, because the distance map gives the distance to the nearest background pixel -- and thinned pixels occur at the vessel center.

However, the distance transform can become even more useful if we combine it with other transforms.

## The watershed transform

The **watershed transform** is an example of a **region growing** method: beginning from some **seed regions**, the seeds are progressively expanded into larger regions until all the pixels of the image have been processed.
This provides an alternative to straightforward thresholding, which can be *extremely* useful when need to partition an image into many different objects.

To understand how the watershed transform works, picture the image as an uneven landscape in which the value of each pixel corresponds to a height.

![Visualizing an image as a landscape, using surface plots. Higher pixel values are generally viewed as peaks, although can easily switched to become valleys by inverting the image before plotting. This may be useful when providing input to the watershed transform.](assets/2.6/gen_fig-transform-surface.png)

*Figure —* Visualizing an image as a landscape, using surface plots. Higher pixel values are generally viewed as peaks, although can easily switched to become valleys by inverting the image before plotting. This may be useful when providing input to the watershed transform.

Now imagine water falling evenly upon this surface and slowly flooding it.
The water gathers first in the deepest parts; that is, in the places where pixels have values lower than all their neighbors.
These define the **seeds** of the watershed transform; we can think of them as separate water basins.

As the water level rises across the image, occasionally it will reach a ridge between two basins -- and, in reality, water could spill from one basin into the other.
However, in the watershed transform this is not permitted; rather a dam is constructed at such ridges.
The water then continues to rise, with dams being built as needed, until in the end every pixel is either part of a basin or a ridge, and there are exactly the same number of basins afterwards as there were at first.

The operation of the watershed transform is illustrated in the video below and example output shown in the figure.

> 🎬 *(video demonstration in the online book)*

![Applying the watershed transform to an image. Here, we passed the inverted image to the watershed transform because we want to identify bright spots rather than dark ones. The full watershed transform will expand the seeds to create a labeled image including all pixels, but we can optionally mask the expansion to prevent it filling the background. Here, we defined the mask by applying a global threshold using the triangle method. Note that the masked watershed segmentation is able to split some spots that were merged using the global threshold alone.](assets/2.6/gen_fig-transform-surface-watershed.png)

*Figure —* Applying the watershed transform to an image. Here, we passed the inverted image to the watershed transform because we want to identify bright spots rather than dark ones. The full watershed transform will expand the seeds to create a labeled image including all pixels, but we can optionally mask the expansion to prevent it filling the background. Here, we defined the mask by applying a global threshold using the triangle method. Note that the masked watershed segmentation is able to split some spots that were merged using the global threshold alone.

Crucially, as the seeds are expanded during the watershed transform, regions are not allowed to overlap.
Furthermore, once a pixel has been assigned to a region then it cannot be moved to become part of any other region.

Using the 'rain falling on a surface' analogy, the seeds would be **regional minima** in an image, i.e. pixels with values that are lower than all neighboring pixels.
This is where the water would gather first.

In practice, we often need to have more control over the seeds rather than accepting all regional minima (to see why too many local minima could be a problem, observe that the figure contains more regions that we probably would want).
This variation is called the **seeded watershed transform**: the idea is the same, but we simply provide the seeds explicitly in the form of a labeled image, and the regions grow from these.
We can generate seeds using other processing steps, such as by identifying [H-minima](sec_h_extrema).

## Combining transforms

The watershed transform can be applied to any image, but it has some particularly interesting applications when it is applied to an image that is a distance map.

### Splitting round objects

A distance map has regional maxima whenever a foreground pixel is further from the background than any of its neighbors.

This tends to occur towards the center of objects: particularly round objects that don't contain any holes.
Importantly, regional maxima can still be present even if the 'round objects' are connected to one another in the binary image used to generate the distance map originally.

This means that by applying a watershed transform to a distance map, we are able to split 'roundish' structures in binary images.
The process is as follows:

* Compute the distance map of the image
* Invert the distance map (e.g. multiply by -1), so that peaks become valleys
* Apply the watershed transform, starting from the regional minima of the inverted distance map

![Splitting round objects using the distance and watershed transforms.](assets/2.6/gen_fig-morph-distance-split-small.png)

*Figure —* Splitting round objects using the distance and watershed transforms.

The objects to be split do not have to be perfectly round.
The only requirement is that there are clearly distinct regional maxima in the distance transform -- or, alternatively, we can define suitable seeds using other processing steps.

![Splitting merged blobs based on 'roundness' using the distance and watershed transforms. Because there are many small regional maxima in the distance transform, here we define seeds using H-maxima followed by a 3×3 dilation to avoid excessive splitting.](assets/2.6/gen_fig-morph-distance-split.png)

*Figure —* Splitting merged blobs based on 'roundness' using the distance and watershed transforms. Because there are many small regional maxima in the distance transform, here we define seeds using H-maxima followed by a 3×3 dilation to avoid excessive splitting.

> **📌 Watershed lines**
>
> When applying a watershed transform, it is often possible to specify whether the separations between regions are assigned one of the region labels, or are left as background pixels.
>
> Here, we have shown the separations as background pixels.
> This is consistent with how ImageJ's default watershed command works, and also makes the splits clearer in the figures shown here.
> In Python code using scikit-image, that means we are using the `watershed_lines=True` option.

### Partitioning images with Voronoi

Calculating the distance transform of an *inverted* binary image gives a distance map in which each pixel gives the distance to the closest foreground object.

If we apply a watershed transform to this distance map, using the objects in the binary image as seeds, we effectively partition the image into different regions according to the closest object in the binary image.

This is sometimes called the **Voronoi transform** of the image.

![Expanding blobs to compute the Voronoi transform of a labeled image, partitioning it into different regions according to the closest seed object.](assets/2.6/gen_fig-morph-voronoi-expand.png)

*Figure —* Expanding blobs to compute the Voronoi transform of a labeled image, partitioning it into different regions according to the closest seed object.

### Expanding without overlaps

Building upon the Vononoi idea in the last section, we can expand the objects themselves in such a way that they don't overlap.

![QuPath's cell detection, based upon nucleus detection + watershed expansion.](assets/2.6/qupath_cells.png)

*Figure —* QuPath's cell detection, based upon nucleus detection + watershed expansion.

Our goal is to dilate each object in the image by 10 pixels, but without merging.
If seed objects are closer than 20 pixels apart, they each expand the same amount -- until they meet in the middle.
This technique may be used to approximate a cell boundary based upon detected nuclei by expansion using a fixed distance.

Firstly, we look at what *won't* work.
We can't simply dilate a labeled image with a maximum filter, because there's nothing to prevent regions merging into one another.
When seeds are close together, the higher label will 'win' the expansion race in every case, dominating the output.

![Expanding blobs using a maximum filter only. This approach is too simple; it results in overlapping labels and a lot of confusion.](assets/2.6/gen_fig-morph-bad-expand.png)

*Figure —* Expanding blobs using a maximum filter only. This approach is too simple; it results in overlapping labels and a lot of confusion.

Instead, we need to build upon the Voronoi approach shown in the figure.
The only difference we need to incorporate is that we prevent the watershed expansion from growing beyond 10 pixels.

Fortunately, this criterion is easy to set: our distance map already gives us the distance to every seed object.
We can threshold that to define a binary mask that indicates where regions should no longer expand.
If we update our watershed output to have background pixels at the same locations where our binary mask has background pixels, we have achieved a constrained expansion of 10 pixels without overlap.

![Using distance and watershed transforms to expand regions by a fixed distance, without overlap. The final output (F) is obtained using information from all images (A) - (E).](assets/2.6/gen_fig-morph-distance-expand.png)

*Figure —* Using distance and watershed transforms to expand regions by a fixed distance, without overlap. The final output (F) is obtained using information from all images (A) - (E).
