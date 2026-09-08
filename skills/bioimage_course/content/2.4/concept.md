# Filters

> **📌 Chapter outline**
>
> * **Filtering** can make segmentation much easier by **enhancing features** and **reducing noise**
> * **Linear filters** replace each pixel by a weighted sum of surrounding pixels
> * **Nonlinear filters** replace each pixel with the result of another computation using surrounding pixels
> * **Gaussian filters** are linear filters with particularly useful properties, making them a good choice for many applications

## Introduction

Filters are phenomenally useful.
Almost all interesting image analysis involves filtering in some way at some stage.
In fact, the analysis of a difficult image can sometimes become (almost) trivial once a suitable filter has been applied to it.
It's therefore no surprise that much of the image processing literature is devoted to the topic of designing and testing filters.

The basic idea of filtering here is that each pixel in an image is assigned a new value depending upon the values of other pixels within some defined region (the pixel's **neighborhood**).
Different filters work by applying different calculations to the neighborhood to get their output.
Although the plethora of available filters can be intimidating at first, knowing only a few of the most useful filters is already a huge advantage.

This chapter begins by introducing several extremely common **linear** and **nonlinear filters** for image processing.
It ends by considering in detail some techniques based on one particularly important linear filter.

## Linear filters

Linear filters replace each pixel with a **linear combination** ('sum of products') of other pixels.
Therefore the only mathematical background they require is the ability to add and multiply.

A linear filter is defined using a **filter kernel**, which is like a tiny image in which the pixels are called **filter coefficients**.
To filter an image, we center the kernel over each pixel of the input image.
We then multiply each filter coefficient by the input image pixel that it overlaps, summing the result to give our filtered pixel value.
Some examples should make this clearer.

### Mean filters

Arguably the simplest linear filter is the **mean filter**.
Each pixel value is simply replaced by the average (mean) of itself and its neighbors within a defined area.

A simple **3×3 mean filter** averages each pixel with its 8 immediate neighbors (above, below, left, right and diagonals).
The filter kernel contains 9 values, arranged as a 3×3 square.
Each coefficient is 1/9, meaning that together all coefficients sum to 1.

The process of filtering with a 3×3 mean filter kernel is demonstrated below:

> 🎬 *(video demonstration in the online book)*

One of the main uses of a 3×3 mean filter is to reduce some common types of image noise, including Gaussian noise and Poisson noise.

We'll discuss the subject of noise in much more detail in a later chapter, chap_formation_noise, and demonstrate *why* a mean filter works to reduce it.
At this point, all we need to know about noise is that it acts like a random (positive or negative) error added to each pixel value, which obscures detail, messes with the histogram, and makes the image look grainy.

the figure provides an illustration of how effectively the 3×3 filter can reduce Gaussian noise in an image.

![Filters can be used to reduce noise. Applying a 3×3 mean filter makes the image smoother, as is particularly evident in the fluorescence plot made through the image center. Computing the difference between images shows what the filter removed, which was mostly random noise (with a little bit of image detail as well).](assets/2.4/gen_fig-filt-reduce-noise.png)

*Figure —* Filters can be used to reduce noise. Applying a 3×3 mean filter makes the image smoother, as is particularly evident in the fluorescence plot made through the image center. Computing the difference between images shows what the filter removed, which was mostly random noise (with a little bit of image detail as well).

Our simple 3×3 mean filter could be easily modified in at least two ways:

1.  Its size could be increased. For example, instead of using just the pixels immediately adjacent to the one we are interested in, a 5×5 mean filter replaces each pixel by the average of a square containing 25 pixels, still centered on the main pixel of interest.
2.  The average of the pixels in some other shape of region could be computed, not just an _n×n_ square.

Both of these adjustments can be achieved by changing the size of the filter kernel and its coefficients.

One common change is to make a 'circular' mean filter.
We can do this by defining the kernel in such a way that coefficients we want to ignore are set to 0, and the non-zero pixels approximate a circle.
The size of the filter is then defined in terms of a radius value (the figure).

![The kernels used with several mean filters. Note that there's no clearly 'right' way to approximate a circle within a pixel grid, and as a result different software can create circular filters that are slightly different. Here, \(B) and (C) match the 'circular' filters used by ImageJ's **Process → Filters → Mean...** command.](assets/2.4/gen_fig-filter-shapes.png)

*Figure —* The kernels used with several mean filters. Note that there's no clearly 'right' way to approximate a circle within a pixel grid, and as a result different software can create circular filters that are slightly different. Here, \(B) and (C) match the 'circular' filters used by ImageJ's **Process → Filters → Mean...** command.

> **📌 Different names for (almost) the same thing**
>
> The world of filtering is full of concepts with multiple names, all meaning pretty much the same thing. For example:
>
> * **linear filtering** may be called **convolution** (very common) or **correlation**[^fn_conv] (less common)
> * a **filter kernel** might be called a **filter mask**
> * **mean filters** are sometimes referred to as **arithmetic mean filters**, **averaging filters** or **boxcar filters**
>
> Take your pick.
> It's worth knowing the equivalence to avoid being confused by the literature.
> In particular, 'convolve' is used often enough as a synonym for 'filter' (with a linear filter) that it's important to remember.

[^fn_conv]: I feel obliged to admit that there *is* a subtle difference between convolution and correlation: the kernel is rotated 180° for convolution.
    This is something we almost never need to care about for two reasons:
    1. Convolution and correlation end up the same if the filter is symmetric -- and most filters we care about are symmetric
    2. The distinction is often ignored in practice anyway. For example, ImageJ has a **Process → Filters → Convolve...** command that (last time I checked) actually implements correlation.

Increasing the size of a mean filter increases its impact.
This is not only in terms of reducing noise, but also in terms of reducing detail, i.e. making the image more blurry (the figure).
If noise reduction is the primary goal, it's therefore best to avoid unnecessary blurring by using the smallest filter that gives acceptable results.

![Smoothing an image using circular mean filters with different radii.](assets/2.4/gen_fig-mean-filter-sizes.png)

*Figure —* Smoothing an image using circular mean filters with different radii.

> **❓ Question**
> In ImageJ, creating a mean filter with *Radius = 6* results in a circular filter that replaces each pixel with the mean of 121 pixels.
> Using a square
> 11×11 filter would also replace each pixel with the mean of 121 pixels.
>
> Can you think of any advantages in using the circular filter rather than the square filter?

<details>
<summary>Show solution</summary>

Circles are more 'compact'.
Every point on the perimeter of a circle is the same distance from the center.
Therefore using a circular filter involves calculating the mean of all pixels a distance of $\leq$ *Radius* pixels away from the center.

For a square filter, pixels that are further away in diagonal directions than horizontal or vertical directions are allowed to influence the results.
If a pixel is further away, it's more likely to have a very different value because it is part of some other structure.
Averaging across structures can blur them into one another, so is best avoided.

</details>

### Gradient filters

Linear filters can do much more than simply compute local averages.
We only need to define a new filter kernel with different coefficients.

Often, we want to detect structures in an image that are distinguishable from the background because of their edges.
Being able to detect the edges could therefore be useful.
Because an edge is usually characterized by a relatively sharp transition in pixel values -- i.e. by a steep increase or decrease in the profile across the image -- **gradient filters** can be used to help.

A very simple gradient filter has the coefficients *-1, 0, 1*.
Applied to an image, this replaces every pixel with the difference between the pixel to the right and the pixel to the left.
The output is positive whenever the pixel values are increasing horizontally, negative when the pixel values are decreasing, and zero if the values are constant -- _no matter what the original constant value was_, so that flat areas are zero in the gradient image irrespective of their original brightness.
We can also rotate the filter by 90 and get a vertical gradient image (the figure).

![Using gradient filters and the gradient magnitude for edge enhancement.](assets/2.4/gen_fig-processing-filters-gradient.png)

*Figure —* Using gradient filters and the gradient magnitude for edge enhancement.

Having two gradient images with positive and negative values can be somewhat hard to work with.
We can combine filtering with [point operations](chap_point_operations) to generate a single image representing the __gradient magnitude__ [^fn_3].
The gradient magnitude has high values around edges (regardless of their orientation), and low values everywhere else.

[^fn_3]: The equation then looks like Pythagoras' theorem: $G_{mag} = \sqrt{G_x^2 + G_y^2}$

The process of calculating the gradient magnitude is:
* Apply linear filters to produce the horizontal and vertical gradient images
* *Square* all the pixel values in both gradient images
* Add the squared images together
* Take the square root of the result

> **❓ Question**
> Suppose the mean pixel value of an image is 100.
> What will the mean value be after applying a horizontal gradient filter?

<details>
<summary>Show solution</summary>

After applying a gradient filter, the image mean will be 0: every pixel is added once and subtracted once when calculating the result.

(Note that the mean value of a *gradient magnitude* image will be ≥ 0, because all pixels have either positive values or are equal to zero.)

</details>

> **🗒️ Aside**
>
> ![](assets/2.4/filter_corner.png)

### Filtering at image boundaries

If a filter consists of more than one coefficient, the neighborhood will extend beyond the image boundaries when filtering some pixels nearby.
We need to handle this somehow.
There are several common approaches.

The boundary pixels could simply be ignored and left with their original values, but for large neighborhoods this would result in much of the image being unfiltered.
Alternative options include treating every pixel beyond the boundary as zero, replicating the closest valid pixel, treating the image as if it is part of a periodic tiling, or mirroring the internal values (the figure).

![Methods for determining suitable values for pixels beyond image boundaries when filtering.](assets/2.4/gen_fig-filter-boundaries.png)

*Figure —* Methods for determining suitable values for pixels beyond image boundaries when filtering.

Different software can handle boundaries in different ways.
Often, if you are using an image processing library to code your own filtering operation you will be able to specify the boundary operation.

## Nonlinear filters

Linear filters involve taking neighborhoods of pixels, scaling them by the filter coefficients, and adding the results to get new pixel values.
**Nonlinear filters** also make use of neighborhoods of pixels, but can use any other type of calculation to obtain the output.
Here we'll consider one especially important family of nonlinear filters.

### Rank filters

**Rank filters** effectively sort the values of all the neighboring pixels in ascending order, and then choose the output based upon this ordered list.

Perhaps the most common example is the **median filter**, in which the pixel value at the center of the list is used for the filtered output.

![Results of different 3×3 rank filters when processing a single neighborhood in an image. The output of a 3×3 mean filter in this case would also be 15.](assets/2.4/rank_results.png)

*Figure —* Results of different 3×3 rank filters when processing a single neighborhood in an image. The output of a 3×3 mean filter in this case would also be 15.

The result of applying a median filter is often similar to that of applying a mean filter, but has the major advantage of removing isolated extreme values completely, _without allowing them to have an impact upon surrounding pixels_.
This is in contrast to a mean filter, which cannot ignore extreme pixels but rather will smooth them out into occupying larger regions (the figure).

However, a disadvantage of a median filter is that it can seem to introduce patterns or textures that were not present in the original image, at least whenever the size of the filter increases (see the figureD below).
Another disadvantage is that large median filters tend to be slow.

![Applying 3×3 mean and median filters to an image containing isolated extreme values (known as _salt and pepper noise_). A mean filter reduces the intensity of the extreme values but spreads out their influence. A small median filter is capable of removing the outliers completely, with a minimal effect upon the rest of the image.](assets/2.4/gen_fig-processing-filters-speckled.png)

*Figure —* Applying 3×3 mean and median filters to an image containing isolated extreme values (known as _salt and pepper noise_). A mean filter reduces the intensity of the extreme values but spreads out their influence. A small median filter is capable of removing the outliers completely, with a minimal effect upon the rest of the image.

Other rank filters include the **minimum** and **maximum filters**, which replace each pixel value with the minimum or maximum value in the surrounding neighborhood respectively (the figure).
They will become more important when we discuss [morphological operations](chap_morph).

![The result of applying 3×3 rank filters. The original noise-free image is shown below in the figureA.](assets/2.4/gen_fig-processing-filters-rank.png)

*Figure —* The result of applying 3×3 rank filters. The original noise-free image is shown below in the figureA.

> **❓ Question**
> What would happen if you subtract a minimum filtered image (e.g.
> the figureC) from a maximum filtered image (Figure the figureB)?

<details>
<summary>Show solution</summary>

Subtracting a minimum from a maximum filtered image would be another way to accent the edges:

![](assets/2.4/gen_2.4_10.png)

</details>

## Gaussian filters

### Filters from Gaussian functions

We conclude this chapter with one fantastically important linear filter, and some variants based upon it.

A **Gaussian filter** is a linear filter that also smooths an image and reduces noise.
However, unlike a mean filter -- for which even the furthest away pixels in the neighborhood influence the result by the same amount as the closest pixels -- the smoothing of a Gaussian filter is weighted so that the influence of a pixel decreases with its distance from the filter center.
This tends to give a better result in many cases (the figure).

![Comparing a mean and Gaussian filter. The mean filter can introduce patterns and maxima where previously there were none. For example, the brightest region in (B) is one such maximum – _but the values of all pixels in the same region in (A) were zero!_ By contrast, the Gaussian filter produces a smoother, more visually pleasing result, somewhat less prone to this effect \(C).](assets/2.4/gen_fig-filt-smoothing.png)

*Figure —* Comparing a mean and Gaussian filter. The mean filter can introduce patterns and maxima where previously there were none. For example, the brightest region in (B) is one such maximum – _but the values of all pixels in the same region in (A) were zero!_ By contrast, the Gaussian filter produces a smoother, more visually pleasing result, somewhat less prone to this effect \(C).

The coefficients of a Gaussian filter are determined from a Gaussian function (the figure)

$$
g(x, y) = Ae^{-(\frac{x^2 + y^2}{2\sigma^2})}
$$

The scaling factor $A$ is used to make the entire volume under the surface equal to 1.
In terms of filtering, this means that the coefficients add to 1 and the image will not be unexpectedly scaled.
The size of the function is controlled by $\sigma$, rather than a filter radius.
$\sigma$ is equivalent to the standard deviation of a normal (i.e. Gaussian) distribution.

![Surface plot of a 2D Gaussian function.](assets/2.4/gen_fig-gaussian-2d.png)

*Figure —* Surface plot of a 2D Gaussian function.

A comparison of several filters is shown in the figure.

![The effects of various filters upon a noisy image of a fixed cell.](assets/2.4/gen_fig-processing-filters.png)

*Figure —* The effects of various filters upon a noisy image of a fixed cell.

### Filters of varying sizes

Gaussian filters have useful properties that make them generally preferable to mean filters, some of which will be mentioned in chap_formation_spatial (others require a trip into Fourier space, beyond the scope of this book).
Therefore if you're not sure which filter to use for smoothing, Gaussian is likely to be a safer choice than mean -- particularly if the filter is large.
Nevertheless, your decisions are not at an end since the precise size of the filter still needs to be chosen.

A small filter will mostly suppress noise, because noise masquerades as tiny random fluctuations at individual pixels.
As the filter size increases, Gaussian filtering starts to suppress larger structures occupying multiple pixels -- reducing their intensities and increasing their sizes, until eventually they would be smoothed into surrounding regions (the figure).
By varying the filter size, we can then decide the **scale** at which the processing and analysis should happen.

![The effect of Gaussian filtering on the size and intensity of structures.](assets/2.4/gen_fig-gaussian-effects.png)

*Figure —* The effect of Gaussian filtering on the size and intensity of structures.

the figure shows an example of when this is useful.
Here, gradient magnitude images are computed, similar to what was shown in the figure, but because the original image is now noisy the initial result is not very useful -- with even strong edges being buried amid noise (B).
Applying a small Gaussian filter prior to computing the gradient magnitude gives much better results \(C).
If we only want the very strongest edges, then apply a larger filter would be better (D).

![Applying Gaussian filters before computing the gradient magnitude changes the scale at which edges are enhanced.](assets/2.4/gen_fig-edge-sigma.png)

*Figure —* Applying Gaussian filters before computing the gradient magnitude changes the scale at which edges are enhanced.

### Difference of Gaussians filtering

So Gaussian filters can be chosen to suppress small structures.
But what if we also wish to suppress large structures -- so that we can concentrate on detecting or measuring structures with sizes inside a particular range?

We already have the pieces necessary to construct one solution.

Suppose we apply one Gaussian filter to reduce small structures.
Then we apply a *second* Gaussian filter, bigger than the first, to a duplicate of the original image.
This will remove even more structures, while still preserving the largest features in the image.

The trick is that, if we subtract this second filtered image from the first, we are left with an image that contains the information that 'falls between' the two smoothing scales we used.

This process is called **difference of Gaussians (DoG) filtering**, and it is a technique that I use *all the time*.
It is especially useful for detecting small structures, or as an alternative to the gradient magnitude for enhancing edges (the figure).

![Difference of Gaussian filtering of the same image at various scales.](assets/2.4/gen_fig-dog-red-hela.png)

*Figure —* Difference of Gaussian filtering of the same image at various scales.

> **📌 DoG filters**
>
> In fact, to get the result of DoG filtering it's not necessary to filter the image twice and subtract the results.
> We could equally well subtract the coefficients of the larger filter from the smaller first (after making sure both filters are the same size by adding zeros to the edges as required), then apply the resulting filter to the image only once (the figure).
>
>
> ![Surface plots of two Gaussian filters with small and large $\sigma$, and the result of subtracting the latter from the former. The sum of the coefficients for (A) and (B) is one in each case, while the coefficients of (C) add to zero.](assets/2.4/gen_fig-dog-plots.png)

*Figure —* Surface plots of two Gaussian filters with small and large $\sigma$, and the result of subtracting the latter from the former. The sum of the coefficients for (A) and (B) is one in each case, while the coefficients of (C) add to zero.

### Laplacian of Gaussian filtering

One minor complication with DoG filtering is the need to select two different values of $\sigma$.
A similar operation, which requires only a single $\sigma$ and a single filter, is **Laplacian of Gaussian (LoG) filtering**.

The appearance of a LoG filter is like an upside-down DoG filter (the figure), but if the resulting image is [inverted](sec_points_inversion) then the results are comparable [^fn_4].

[^fn_4]: A LoG filter is also often referred to as a _mexican-hat filter_, although clearly the filter (or the hat-wearer) should be inverted for the name to make more sense

![Surface plot of a LoG filter. This closely resembles the figure, but inverted so that the negative values are found in the filter center.](assets/2.4/gen_fig-log-plots.png)

*Figure —* Surface plot of a LoG filter. This closely resembles the figure, but inverted so that the negative values are found in the filter center.

![Application of DoG and LoG filtering to an image. Both methods enhance the appearance of spot-like structures, and (to a lesser extent) edges, and result in an image containing both positive and negative values with an overall mean of zero. In the case of LoG filtering, inversion is involved: darker points become bright after filtering.](assets/2.4/gen_fig-dog-on-log.png)

*Figure —* Application of DoG and LoG filtering to an image. Both methods enhance the appearance of spot-like structures, and (to a lesser extent) edges, and result in an image containing both positive and negative values with an overall mean of zero. In the case of LoG filtering, inversion is involved: darker points become bright after filtering.

### Unsharp masking

Finally, a related technique widely-used to enhance the visibility of details in images -- although certainly _not_ advisable for quantitative analysis -- is **unsharp masking**.

This uses a Gaussian filter first to blur the edges of an image, and then subtracts it from the original.
But rather than stop there, the subtracted image is multiplied by some weighting factor and _added back_ to the original.
This gives an image that looks much the same as the original, but with edges sharpened by an amount dependent upon the chosen weight.

![The application of unsharp masking to a blurred image. First a Gaussian-smoothed version of the image ($\sigma = 1$) is subtracted from the original, scaled ($weight = 0.7$) and added back to the original.](assets/2.4/gen_fig-unsharp-masking.png)

*Figure —* The application of unsharp masking to a blurred image. First a Gaussian-smoothed version of the image ($\sigma = 1$) is subtracted from the original, scaled ($weight = 0.7$) and added back to the original.

Unsharp masking can improve the visual appearance of an image, but it's important to remember that it modifies the image content in a way that might well be considered suspicious in scientific circles.
Therefore, if you apply unsharp masking to any image you intend to share with the world you should have a good justification and certainly admit what you have done.
The technique is included here not as a recommendation that you use it, but rather to show how Gaussian filters can be combined with point operations in creative ways.

If you want a more theoretically justified method to improve image sharpness in microscopy, it may be worth looking into *'(maximum likelihood) deconvolution'* algorithms.
