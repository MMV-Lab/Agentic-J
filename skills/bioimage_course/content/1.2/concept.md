# Measurements & histograms

> **📌 Chapter outline**
>
> * **Measurements** can be made in images by calculating statistics from the pixel values
> * **Histograms** show the distribution of pixel values in an image, and are extremely useful to compare images & diagnose problems

## Introduction

chap_pixels demonstrated how looks can be deceiving: the visual appearance of an image isn't enough to determine what data it contains.

Because scientific image analysis depends upon having the right pixel values in the first place, this leads to the important admonition:

> **📌 Keep your original pixel values safe!**
>
> The pixel values in your original image are your raw data: it's essential to protect these from unwanted changes.

This is really important because there are lots of ways to accidentally compromise the raw data of an image -- such as by using the wrong software to adjust the brightness and contrast, or saving the files [in the wrong format](chap_files).
This can cause the results of analysis to be wrong.

What makes this especially tricky is that trustworthy and untrustworthy images can *look* identical. 
Therefore, we need a way to see beyond LUTs to compare the content of images easily and efficiently.

## Comparing histograms & statistics

In principle, if we want to compare two images we could check that every corresponding pixel value is identical in both images.
We will use this approach later, but isn't always necessary.

There are two other things we can do, which are often much faster and easier:

1. Calculate some **summary statistics** from the pixel values, such as the average (mean) pixel value, standard deviation, minimum and maximum values.
2. Check out the image **histogram**. This graphically depicts the distribution of pixel values in the image.

Putting these into action, we can recreate the figure but this time add
1. the LUT (shown as a colored bar below the image)
2. a histogram
3. summary statistics

![Recreation of the figure showing images that *look* the same, but contain *different* pixels values -- this time with measurements and histograms included.](assets/1.2/gen_fig-images-look-same-histograms.png)

*Figure —* Recreation of the figure showing images that *look* the same, but contain *different* pixels values -- this time with measurements and histograms included.

With the additional information at our disposal, we can immediately see that the images really **do** contain different underlying values -- and therefore potentially quite different information -- despite their initial similar appearance.
We can also see that the LUTs are different; they show the same colors (shades of gray), but in each case these map to different values.

By contrast, when we apply the same steps to the figure we see that the histograms and statistics are identical -- only the LUT has been changed in each case.
This suggests that any analysis we perform on each of these images should give the same results, since the pixel values remain intact.

![Recreation of the figure showing images that *look* different, but contain *the same* pixel values -- this time with measurements and histograms included.](assets/1.2/gen_fig-images-look-different-histograms.png)

*Figure —* Recreation of the figure showing images that *look* different, but contain *the same* pixel values -- this time with measurements and histograms included.

> **❓ Question**
> If two images have identical histograms and summary statistics (mean, min, max, standard deviation), does this **prove** that the images are identical?

<details>
<summary>Show solution</summary>

No! For example, we might have the same pixel values in a different arrangement.
If I randomly shuffle the pixels in the image then the basic statistics and histogram remain unchanged -- but the image itself is very different.

![](assets/1.2/gen_1.2_3.png)

This means that, technically, we can only really use histograms and summary measurements to prove that images are definitely *not* the same.

However, in practice this is usually enough.
If two images have identical histograms and summary statistics *and* look similar, it is *very likely* that they are the same.

Conceivably, someone might try to deceive us by making some very subtle change to an image that preserves the statistics, such as as swapping two pixels amongst millions so that we don't notice the difference.
Later, we'll see how to overcome even that by checking every single pixel -- but such elaborate trickery probably isn't a very real risk for most of us.

Most of the time, when things go wrong with scientific images the histogram and statistics will be compromised in an obvious way -- we just need to remember to check for these changes.

</details>

The ability to quickly generate and interpret histograms is an essential skill for any image analyst.
We will use histograms a lot throughout this text, both to help diagnose problems with the data and to figure out which techniques we should use.

> **📌 Make histograms a habit!**
>
> When working with new images, it's a good habit to *always* check histograms.
> This can give a deeper understanding of the data, and help flag up potential problems.
