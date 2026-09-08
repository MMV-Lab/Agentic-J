# Image processing & analysis 

> **📌 Chapter outline**
>
> * **Image processing** involves changing images, usually in ways that will help interpretation later
> * **Image analysis** involves converting images into measurements
> * When image analysis is our goal, we almost always need image processing to get there

## Introduction

Successfully extracting useful information from microscopy images usually requires triumphing in two main battles.

The first is to overcome limitations in image quality and make the really interesting image content more clearly visible.
This involves **image processing**, the output of which is another image.
The second is to compute meaningful measurements, which could be presented in tables and summary plots.
This is **image analysis**.

Our main goal here is analysis -- but processing is almost always indispensable to get us there. 

## An image analysis workflow

So how do we figure out how to analyze our images?

Ultimately, we need some kind of workflow comprising multiple steps that eventually take us from image to results.
Each individual step might be small and straightforward, but the combination is powerful.

I tend to view the challenge of constructing any scientific image analysis workflow as akin to solving a puzzle.
In the end, we hope to extract some kind of quantitative measurements that are justified by the nature of the experiment and the facts of image formation.
One of the interesting features of the puzzle is that there is no single, fixed solution.

Although this might initially seem inconvenient, it can be liberating: it suggests there is room for lateral thinking and sparks of creativity.
The same images could be analyzed in quite different ways.
Sometimes giving quite different results, or answering quite different scientific questions.

Admittedly, if no solution comes to mind after pondering for a while then such an optimistic outlook quickly subsides, and the 'puzzle' may very well turn into an unbearably infuriating 'problem' -- but the point here is that _in principle_ image analysis _can_ be enjoyable.
What it takes is: 
* a modicum of enthusiasm (please bring your own)
* properly-acquired data, including all the necessary metadata (the subject of Part I)
* actually *having the tools at your disposal* to solve the puzzle (the subject Part II)

If you're a reluctant puzzler then it also helps to have the good luck not to be working on something horrendously difficult, but that is difficult to control.

### Combining processing tools

Image processing provides a whole host of tools that can be applied to puzzle-solving.
When piecing together processing steps to form a workflow, we usually have two main stages:

1. **Preprocessing**: the stuff you do to clean up the image, e.g. subtract the background, use a filter to reduce noise 
2. **Segmentation** the stuff you do to identify the things in the image you care about, e.g. apply a threshold to locate interesting features

Having successfully navigated these stages, there are usually some additional tasks remaining (e.g. making measurements of shape, intensity or dynamics).
However, these depend upon the specifics of the application and are *usually* not the hard part.
If you can identify what you want to quantify, you're a long way towards solving the puzzle.

the figure shows an example of how these ideas can fit together.

![A simple image analysis workflow for detecting and measuring spots in an image.](assets/2.1/gen_fig-workflow.png)

*Figure —* A simple image analysis workflow for detecting and measuring spots in an image.

It won't be possible to cover *all* image processing tools in a book like this.
Rather, we will focus on the essential ones needed to get started: thresholds, filters, morphological operations and transforms.

These are already enough to solve many image analysis puzzles, and provide the framework to which more can be added later.
