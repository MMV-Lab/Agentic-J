# ImageJ: Image transforms

## Introduction

ImageJ has excellent 2D distance and watershed transforms... although not necessarily everything about them is quite what you might expect.

## Distance transform

> **🗒️ Aside**
>
> ![](assets/2.6/imagej-binary-options.png)

A 2D distance transform can be calculated in ImageJ using the **Process → Binary → Distance Map** command.

A non-obvious feature of this is that the type of output given is determined by the **EDM output** option tucked away under **Process → Binary → Options...** (where EDM stands for 'Euclidean Distance Map').
This makes a difference, because the distance between two diagonal pixels is considered $\sqrt{2} \approx 1.414$ (by Pythagoras' theorem) -- which means that a 32-bit output can give more exact straight-line distances without rounding.

![Outputs from several distance transform-related commands in ImageJ.](assets/2.6/gen_fig-distance-commands-imagej.png)

*Figure —* Outputs from several distance transform-related commands in ImageJ.

### Ultimate points

**Process → Binary → Ultimate Points** is a related command.
It uses the distance transform to identify the last points that would be removed if the objects would be eroded until they disappear.
In other words, it identifies centers.
But these are not simply single center points for each object; rather, they are maximum points in the distance map, and therefore the pixels furthest away from the boundary.

This means that if a structure has several 'bulges', then an ultimate point exists _at the center of each of them_.
If segmentation has resulted in structures being merged together, then each distinct bulge could actually correspond to something interesting -- and the number of bulges actually means more than the number of separated objects in the binary image.

> **⚠️ Caution**
>
> Although conceptually straightforward, and easy to use in ImageJ, implementing 'Ultimate points' in other software can be tricky.
> Here, I've tried to replicate it in Python.
> The results aren't necessarily identical to ImageJ's implementation, but should be pretty close.
>
> Select to **Show code cell contents** above to see how it works.
>
>
> ![Computing the ultimate points from a binary image can be an effective step towards counting the objects in the image -- even if these have been merged. It works best when the true objects are round in shape.](assets/2.6/gen_fig-distance-transform-python.png)

*Figure —* Computing the ultimate points from a binary image can be an effective step towards counting the objects in the image -- even if these have been merged. It works best when the true objects are round in shape.

### Watershed (after distance transform)

As the name suggests, ImageJ's **Process → Binary → Watershed** command applies a watershed transform.

However, as the name conceals, the watershed transform is always applied to a distance map -- which is calculated automatically in the background.

The clue to this is only that it appears in a **Process → Binary** submenu, and therefore requires a binary image as input; a 'regular' watershed transform isn't normally applied to a binary image.

Effectively, the seeds of the watershed transform are the 'ultimate points' described above.
The effect of the command is therefore to split 'roundish' objects.

> **🗒️ Aside**
>
> ![](assets/2.6/imagej-binary-blobs-stack.png)

> **📌 Watching the distance transform**
>
> If you click the **Dev** toolbar button and select **Debug Mode** from the drop-down menu, then running **Process → Binary → Watershed** will generate an image stack that visualizes how the seeds expanded during the watershed processing.

### Voronoi

**Process → Binary → Voronoi** is another distance-and-watershed-based command for binary images.

It will partition the image into different regions so that the separation lines have an equal distance to the nearest foreground objects.

> **🗒️ Aside**
>
> ![](assets/2.6/imagej-blobs-surroundings.png)

> **❓ Question**
> Imagine you have created a binary image containing detected cells, but you are only interested in the region inside the cell that is close to the membrane, i.e. within 5 pixels of the edge of each detected object.
> Any pixels outside the objects or closer to their centers do not matter.
>
> How would you go about finding these regions using ImageJ and the distance transform?
>
> **Note:** There other ways to do this using techniques we've discussed, although these don't necessarily give identical results.

<details>
<summary>Show solution</summary>

This is the approach I was thinking of:
1. Run **Edit → Invert**
2. Run **Process → Binary → Distance Map**
3. Run **Image → Adjust → Threshold...**
4. Choose **Set** and enter *Lower Threshold Level: 1* and *Higher Threshold Level: 5*.

There are more possible ways, such as applying a maximum filter and subtracting the original binary image -- but I think the distance transform is more elegant.
The distance transform is also likely to be much faster for large distances, and more precise (assuming you use a 32-bit output).

</details>

## Watershed transform

> **🗒️ Aside**
>
> ![](assets/2.6/imagej-find-maxima.png)

So if ImageJ has a watershed transform, but it's not the command called **Watershed**, then where is it?

The answer is that it's hidden in the phenomenally useful **Process → Find maxima** command.

I say 'hidden', because you specifically have to choose the output **Segmented Particles** to use it.
And you'll need to flip your expectations: unlike most watershed transforms, it will start at the *intensity peaks* of the image (i.e. the maxima) and expand outwards, rather than starting at minima.

But don't let those things discourage you: I highly recommend exploring the various options of **Process → Find maxima** to see what all it can do.
Depending upon which options are selected, this includes finding structures using a global threshold, a local threshold, generating point ROIs and generating binary regions.

> **📌 Check out MorphoLibJ**
>
> Echoing my recommendation at the end of the last chapter, you should check out **MorphoLibJ** if you would like more transform options -- particularly when it comes to watersheds of various kinds.
>
> See https://imagej.net/plugins/morpholibj for more details.
