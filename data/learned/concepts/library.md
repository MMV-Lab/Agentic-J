# Concept library (approved, recall-searchable)

Strategic **WHEN/DO/WHY/AVOID** heuristics for planning image-analysis workflows —
a third, language-agnostic tier of learned knowledge alongside `pitfalls/` and
`recipes/`. Distilled from the sources in `README.md` and vetted in human review.

This library is **FIXED** (not auto-curated by the Librarian) and is **NOT auto-injected**.
It is retrieved on demand via the `recall_concepts` tool — the same way documentation
is pulled through the RAG retriever. New candidates are still drafted into `_pending.md`
and only land here after review. `CORE.md` is intentionally left empty (no always-inject
floor for concepts at this time).

Promoted from review on 2026-07-22: 99 entries.
Added 2026-08-03: 2 entries (`lj-verify-per-subgroup`, `lj-nuclei-within-cell-mask`) — 101 total.

---

<!--c:bib-float-before-math status:approved src:bioimagebook chap:2-processing/2-point_operations modality:general task:preprocessing kw:float,32-bit,clipping,rounding,arithmetic,convert,pixel math,convert to 32-bit,image arithmetic,divide images,ratio of images,subtract images-->
- **WHEN** any step does pixel arithmetic — background subtraction, filtering, ratios, averaging
  **DO**   convert the image to 32-bit floating point first
  **WHY**  integer images clip values outside their range and round fractions, and the loss is irreversible (200+100→255, then −100→155, not 200)
  **AVOID** doing math in place on 8/16-bit integer images
  SRC: bioimagebook · Point operations › "Convert integer images to floating point before manipulating pixels"

<!--c:bib-keep-raw status:approved src:bioimagebook chap:2-processing/2-point_operations modality:general task:preprocessing kw:raw,original,duplicate,provenance,integrity,keep original,work on a copy,don't overwrite,preserve raw data,backup image-->
- **WHEN** starting any processing pipeline
  **DO**   keep the original file untouched and work on a duplicate
  **WHY**  the raw pixel values are the actual data; processing must be justifiable and reversible back to the source
  **AVOID** overwriting the acquired image with processed output
  SRC: bioimagebook · Point operations › "Isn't modifying pixels bad?"

<!--c:bib-check-histogram status:approved src:bioimagebook chap:1-concepts/2-measurements modality:general task:qc kw:histogram,statistics,diagnose,inspect,bimodal,check the histogram,look at the histogram,inspect image,image statistics,diagnose image-->
- **WHEN** opening a new/unfamiliar image, or before choosing a threshold
  **DO**   look at the histogram and summary stats (min/max/mean/SD/percentiles) first
  **WHY**  the histogram reveals background level, bimodality, clipping and dynamic range — appearance alone (LUT) can hide all of it
  **AVOID** picking processing steps from how the image *looks* on screen
  SRC: bioimagebook · Measurements & histograms › "Make histograms a habit!"

<!--c:bib-avoid-clipping status:approved src:bioimagebook chap:1-concepts/3-bit_depths modality:general task:qc kw:clipping,saturation,0,255,65535,dynamic-range,saturated pixels,overexposed,clipped image,check saturation,blown out highlights-->
- **WHEN** assessing acquisition quality or before automated thresholding
  **DO**   check whether pixels sit at the extreme values (0 or the bit-depth max); treat their presence as possible clipping
  **WHY**  clipped data has lost information irretrievably and violates the statistical assumptions behind automated thresholds
  **AVOID** assuming 8-bit data spanning exactly 0–255 is fine — safe range is ~1–254
  SRC: bioimagebook · Types & bit-depths › "Data clipping" / "Clipping confounds automated thresholds"

<!--c:bib-nonlinear-display-only status:approved src:bioimagebook chap:2-processing/2-point_operations modality:general task:display kw:gamma,log,contrast,nonlinear,figure,publication,gamma correction,brighten dim signal,enhance contrast for figure,show dim and bright,display adjustment-->
- **WHEN** an image has high dynamic range and dim + bright structures must both be visible
  **DO**   use a log or gamma transform for *display only*, and declare it in the figure legend
  **WHY**  nonlinear contrast changes relative brightness and can mislead; it is fine for visualization but not for quantification
  **AVOID** measuring on gamma/log-adjusted pixels, or applying it silently to publication figures
  SRC: bioimagebook · Point operations › "Nonlinear contrast enhancement" / "Avoid image manipulation!"

<!--c:bib-flatten-uneven-bg status:approved src:bioimagebook chap:2-processing/3-thresholding modality:general task:thresholding kw:uneven,background,illumination,local-threshold,subtract,flatten,patchy illumination,uneven brightness,gradient background,vignetting,shading-->
- **WHEN** objects sit on a background that itself varies in brightness across the field
  **DO**   flatten the background first (subtract an estimated background image / large-radius opening / rolling-ball), then apply a global threshold — or use a local/adaptive threshold
  **WHY**  a global threshold is a point operation assuming one background level everywhere; if the background varies, no single value is right across the whole image
  **AVOID** just nudging the global threshold up or down — it trades missed dim objects for merged bright ones
  SRC: bioimagebook · Thresholding › "Thresholding difficult data" / "Local thresholding"

<!--c:bib-smooth-before-threshold status:approved src:bioimagebook chap:2-processing/3-thresholding modality:general task:thresholding kw:noise,gaussian,smooth,presmooth,denoise,smooth before thresholding,reduce noise before threshold,noisy hard to threshold-->
- **WHEN** a noisy image resists thresholding (foreground/background peaks overlap in the histogram)
  **DO**   apply a Gaussian filter (2D/3D) to smooth first, or another feature-enhancing filter, then threshold
  **WHY**  smoothing reduces random noise so the two pixel classes separate again in the histogram and an automated threshold succeeds
  **AVOID** thresholding the raw noisy image and hand-tuning to compensate
  SRC: bioimagebook · Thresholding › "Thresholding noisy data"

<!--c:bib-threshold-method-by-histogram status:approved src:bioimagebook chap:2-processing/3-thresholding modality:general task:thresholding kw:otsu,triangle,minimum,mean,mad,auto-threshold,histogram-shape,which threshold method,auto threshold,otsu vs triangle,choose threshold algorithm,thresholding method-->
- **WHEN** choosing an automated threshold method
  **DO**   match the method to the histogram shape: Otsu or Minimum for a clean bimodal histogram; Triangle for one dominant background peak with a foreground tail; Mean+k·SD or Median+k·MAD for a mostly-noise unimodal image
  **WHY**  each method encodes assumptions about the histogram; when the assumption holds it works well, when it doesn't it can fail badly
  **AVOID** defaulting to Otsu on non-bimodal microscopy histograms
  SRC: bioimagebook · Thresholding › "Automated thresholds"

<!--c:bib-mad-threshold-noisy-fluor status:approved src:bioimagebook chap:2-processing/3-thresholding modality:fluorescence task:thresholding kw:median,mad,robust,noisy,spots,fluorescence,robust threshold,threshold noisy fluorescence,dim spots threshold-->
- **WHEN** thresholding very noisy fluorescence where most of the frame is background
  **DO**   use median + k·MAD·1.482 (MAD scaled to resemble a robust SD)
  **WHY**  median/MAD is robust to outliers and won't fail catastrophically on a near-noise image the way bimodal methods do
  **AVOID** it when the background is perfectly flat (MAD→0) or the image is huge (exact median is slow)
  SRC: bioimagebook · Thresholding › "Median & Median Absolute Deviation"

<!--c:bib-threshold-bias-metric status:approved src:bioimagebook chap:2-processing/3-thresholding modality:general task:measurement kw:threshold,bias,count,size,median,merge,split,threshold affects counts,threshold sensitivity,object size bias-->
- **WHEN** the threshold choice is ambiguous and you must report object counts or sizes
  **DO**   remember a low threshold merges/enlarges objects and a high one splits/shrinks them; prefer output metrics robust to this (e.g. median object size over mean)
  **WHY**  the threshold biases both counts and areas simultaneously, and merged artifacts distort the mean far more than the median
  **AVOID** reporting a single threshold-sensitive number without considering the error it introduces
  SRC: bioimagebook · Thresholding › "The importance of the threshold choice"

<!--c:bib-auto-not-unbiased status:approved src:bioimagebook chap:2-processing/3-thresholding modality:general task:thresholding kw:automated,bias,validate,systematic,is auto threshold unbiased,automated threshold bias,validate threshold-->
- **WHEN** justifying an automated threshold as "objective"
  **DO**   validate that the method actually works on *this* dataset before trusting it
  **WHY**  a bad automated threshold applies a *systematic* bias across every image — often worse than a per-image manual choice
  **AVOID** treating "automated" as synonymous with "unbiased"
  SRC: bioimagebook · Thresholding › "Are automated thresholds less biased?"

<!--c:bib-visualize-detections status:approved src:bioimagebook chap:2-processing/3-thresholding modality:general task:qc kw:overlay,visualize,batch,qc,summary,sanity-check,check segmentation,overlay outlines,verify results,quality control,sanity check batch-->
- **WHEN** running any segmentation, especially batch-processing many images
  **DO**   overlay what was detected on the original image and actually look at it (an RGB outline copy per image); make visualization as much a part of the workflow as analysis
  **WHY**  it is disturbingly easy to generate plausible-looking summary numbers from wrong segmentations; only overlays reveal merges/misses
  **AVOID** trusting a summary spreadsheet for 10,000 images after checking a handful
  SRC: bioimagebook · Thresholding › "Beware summary plots!"

<!--c:davide-stain-deconvolution status:approved src:davide modality:brightfield task:segmentation kw:color-deconvolution,stain-vectors,histology,pathology,rgb,he,dab,ihc,transmitted-light,unmix stains,separate stains,stain separation-->
- **WHEN** segmenting RGB data of stained transmitted-light images (histology / pathology)
  **DO**   apply colour deconvolution and/or estimate the stain vectors, then work on the separated stain channels
  **WHY**  different structures of interest are marked by different stains/dyes, so separating their contributions gives higher segmentation/detection quality
  **AVOID** direct thresholding on raw RGB data
  SRC: Davide (internal domain expert) — see also [[sc-color-deconvolution]]

<!--c:bib-gaussian-default status:approved src:bioimagebook chap:2-processing/4-filters modality:general task:filtering kw:gaussian,mean,smooth,denoise,default,denoising,smoothing,noise reduction-->
- **WHEN** smoothing / reducing Gaussian or Poisson noise
  **DO**   use a Gaussian filter as the default
  **WHY**  it has well-behaved properties and avoids the artificial maxima and blocky patterns a plain mean (boxcar) filter can introduce
  **AVOID** a mean filter where a smooth, artifact-free result matters
  SRC: bioimagebook · Filters › "Comparing a mean and Gaussian filter"

<!--c:bib-smallest-filter status:approved src:bioimagebook chap:2-processing/4-filters modality:general task:filtering kw:filter-size,radius,blur,detail,noise-tradeoff,filter size,how much to blur,blur radius,smoothing amount,kernel size-->
- **WHEN** picking a smoothing filter size
  **DO**   use the smallest filter that gives acceptable noise reduction
  **WHY**  larger filters reduce noise more but also blur away real detail
  **AVOID** oversizing the filter "to be safe"
  SRC: bioimagebook · Filters › mean filter size / blurring

<!--c:bib-median-outliers status:approved src:bioimagebook chap:2-processing/4-filters modality:general task:filtering kw:median,salt-pepper,outliers,hot-pixels,remove-outliers,denoise,hot pixels,speckle,despeckle,salt and pepper-->
- **WHEN** the image has isolated extreme pixels (salt-and-pepper / hot pixels)
  **DO**   use a median filter, or ImageJ *Process › Noise › Remove Outliers* (replaces only truly extreme pixels)
  **WHY**  a small median removes outliers cleanly with minimal effect elsewhere; a mean filter just smears their influence around
  **AVOID** using a mean/Gaussian filter to "average out" single hot pixels
  SRC: bioimagebook · Filters › rank filters / Noise › "Remove Outliers"

<!--c:bib-dog-log-spots status:approved src:bioimagebook chap:2-processing/4-filters modality:fluorescence task:spot-detection kw:dog,log,difference-of-gaussians,spots,blob,edges,gradient,spot detection,blob detection,puncta,foci enhance-->
- **WHEN** enhancing spot-like structures (puncta, foci) or edges before detection
  **DO**   use Difference-of-Gaussians (DoG) or Laplacian-of-Gaussian (LoG) for spots; use gradient-magnitude for edges
  **WHY**  these band-pass filters suppress smooth background and boost structures at the chosen scale, making spots far easier to threshold
  **AVOID** thresholding raw intensity for small spots on structured background
  SRC: bioimagebook · Filters › "Difference of Gaussian filtering" / gradient magnitude

<!--c:davide-edge-ridge-filters status:approved src:davide modality:general task:filtering kw:edge-detection,canny,sobel,frangi,vesselness,dot-filter,filament,ridge,boundary,neurites,vessels,ridge detection,edge enhancement-->
- **WHEN** dealing with filamentous structures or hard-to-find edges/boundaries
  **DO**   apply edge-detection filters (e.g. Canny/Sobel) or signal-enhancing filters (e.g. Frangi/vesselness, dot filters) before segmenting
  **WHY**  filamentous structures and faint cell boundaries are hard to threshold directly; these filters enhance exactly that signal
  **AVOID** blind thresholding on the unprocessed image
  SRC: Davide (internal domain expert) — see also [[bib-dog-log-spots]]

<!--c:bib-circular-kernel status:approved src:bioimagebook chap:2-processing/4-filters modality:general task:filtering kw:circular,square,kernel,radius,shape,kernel shape,circular vs square filter,filter neighborhood-->
- **WHEN** choosing a filter neighborhood shape
  **DO**   prefer a circular (radius-defined) kernel over a square one
  **WHY**  a square lets far-away diagonal pixels — more likely part of another structure — influence the result and blur across structures
  **AVOID** a square kernel when structures are close together
  SRC: bioimagebook · Filters › circular vs square mean filter

<!--c:bib-sigma-to-scale status:approved src:bioimagebook chap:2-processing/4-filters modality:fluorescence task:filtering kw:sigma,scale,psf,feature-size,edge-scale,gaussian sigma,what sigma to use,blur scale,sigma for feature size-->
- **WHEN** setting a Gaussian σ (for smoothing, edge detection, or matching blur)
  **DO**   choose σ relative to the feature/PSF scale of interest; for edge detection the pre-smoothing σ sets the scale of edges enhanced
  **WHY**  filtering is scale-selective — σ decides which structures survive and which wash out
  **AVOID** a one-size σ regardless of object size or pixel calibration
  SRC: bioimagebook · Filters › Gaussian scale / edge sigma; Blur & the PSF

<!--c:bib-opening-closing status:approved src:bioimagebook chap:2-processing/5-morph modality:general task:morphology kw:opening,closing,erode,dilate,specks,gaps,merge-split,remove small specks,fill small gaps,clean up mask,morphological opening closing,rejoin split objects-->
- **WHEN** a binary segmentation has spurious specks or spurious gaps/splits
  **DO**   use opening (erode→dilate) to remove small specks while keeping survivors' size; use closing (dilate→erode) to fill small gaps and rejoin wrongly-split objects
  **WHY**  combining the two operations cleans shape without the net size change that erosion or dilation alone would cause
  **AVOID** a bare erosion or dilation when you don't want to change object sizes
  SRC: bioimagebook · Morphological operations › "Opening & closing"

<!--c:bib-area-opening status:approved src:bioimagebook chap:2-processing/5-morph modality:general task:morphology kw:area-opening,size-filter,connected-components,fill-holes,remove small objects,size filter,fill holes,filter by area,despeckle mask-->
- **WHEN** removing objects below a size, or filling only holes below a size
  **DO**   use area opening (drop connected components under an area threshold) instead of plain opening; fill small holes via invert → area-open → invert
  **WHY**  area opening removes small components with *no* effect on the shape of larger ones, unlike structuring-element opening
  **AVOID** plain opening when you need larger objects' shapes preserved exactly
  SRC: bioimagebook · Morphological operations › "Area opening" / "Filling holes"

<!--c:bib-cytoplasm-ring status:approved src:bioimagebook chap:2-processing/5-morph modality:fluorescence task:measurement kw:cytoplasm,ring,nucleus,dilate,boundary,subtract,measure cytoplasm,cytoplasmic intensity,ring around nucleus,perinuclear measurement-->
- **WHEN** you need a cytoplasmic measurement but the cell/membrane isn't clearly segmentable
  **DO**   segment the nucleus, dilate it, and subtract the nucleus to get a ring just outside it
  **WHY**  the ring reliably samples cytoplasm without the hard problem of full-cell segmentation
  **AVOID** abandoning the measurement because whole cells can't be segmented
  SRC: bioimagebook · Morphological operations › "Boundaries & outlines"

<!--c:bib-hysteresis-threshold status:approved src:bioimagebook chap:2-processing/5-morph modality:fluorescence task:thresholding kw:hysteresis,double-threshold,reconstruction,seed,noise,double threshold,two thresholds,bright core dim edges-->
- **WHEN** a single threshold either admits noise (too low) or fragments real objects (too high)
  **DO**   use hysteresis (double) thresholding: keep low-threshold regions only if they contain at least one high-threshold pixel (morphological reconstruction)
  **WHY**  it captures the full extent of real objects while rejecting noise blobs that never cross the high threshold
  **AVOID** compromising on one global threshold when objects have bright cores and dim edges
  SRC: bioimagebook · Morphological operations › "Hysteresis thresholding"

<!--c:bib-hmaxima-seeds status:approved src:bioimagebook chap:2-processing/5-morph modality:general task:detection kw:h-maxima,h-minima,seeds,local-maxima,reconstruction,seed points,find local maxima,watershed seeds,too many maxima-->
- **WHEN** you need robust seed points / local maxima (e.g. to seed a watershed)
  **DO**   use H-maxima / H-minima (one intuitive intensity parameter H) rather than a naive local-maximum filter
  **WHY**  naive dilation-based maxima over-detect on noise and plateaus; H-maxima suppress insignificant peaks below height H
  **AVOID** feeding raw local maxima as seeds — you'll get far too many
  SRC: bioimagebook · Morphological operations › "H-Maxima & H-Minima"

<!--c:bib-distance-watershed-split status:approved src:bioimagebook chap:2-processing/6-transforms modality:general task:segmentation kw:watershed,distance-transform,touching,clumped,nuclei,split,round,clumped nuclei,touching cells,stuck together,cells merged,declump,separate touching objects-->
- **WHEN** roundish objects (nuclei, cells) touch and are merged in the binary mask
  **DO**   compute the distance transform, invert it, and run a (seeded) watershed on it
  **WHY**  each round object gives a distance-map peak even when connected to neighbours, so the watershed splits them along the valleys between peaks
  **AVOID** raising the threshold to separate touching objects — it just erodes them
  SRC: bioimagebook · Image transforms › "Splitting round objects"

<!--c:bib-distance-transform-uses status:approved src:bioimagebook chap:2-processing/6-transforms modality:general task:morphology kw:distance-transform,erosion,dilation,thickness,vessel-radius,skeleton,distance transform,distance map,local thickness,vessel diameter,fast erosion-->
- **WHEN** you need a large erosion/dilation, or a local-thickness measure
  **DO**   use the distance transform — threshold the distance map for fast large erosion/dilation; read distance values along a skeleton for local thickness (e.g. vessel radius)
  **WHY**  thresholding a distance map is far faster than large min/max filters, and the map directly encodes distance-to-background
  **AVOID** huge structuring-element erosions/dilations when a distance map would do
  SRC: bioimagebook · Image transforms › "The distance transform"

<!--c:bib-voronoi-expand-nuclei status:approved src:bioimagebook chap:2-processing/6-transforms modality:fluorescence task:segmentation kw:voronoi,seeded-watershed,expand,cell-boundary,nuclei,no-overlap,cell boundaries from nuclei,expand nuclei,cell territories,grow nuclei to cells-->
- **WHEN** approximating cell territories from detected nuclei
  **DO**   seed a watershed on the distance transform of the inverted nuclei (Voronoi), optionally capping expansion at a fixed distance
  **WHY**  it expands each nucleus into a non-overlapping territory; a plain dilation of a labelled image lets the higher label win and merge
  **AVOID** dilating labelled nuclei with a max filter to make cells
  SRC: bioimagebook · Image transforms › "Partitioning images with Voronoi" / "Expanding without overlaps"

<!--c:bib-skeletonize-filaments status:approved src:bioimagebook chap:2-processing/5-morph modality:general task:morphology kw:skeleton,thinning,filament,axon,vessel,centerline,neurites,axons,blood vessels,tracing,filament length-->
- **WHEN** analysing filamentous/tubular structures (axons, vessels, neurites)
  **DO**   skeletonize/thin to the centerline (try both if the software offers them — results differ)
  **WHY**  centerlines give length, branching and connectivity that a thick binary mask can't
  **AVOID** measuring filament length off the raw thresholded mask
  SRC: bioimagebook · Morphological operations › "Thinning & skeletonization"

<!--c:bib-anisotropy-aware status:approved src:bioimagebook chap:2-processing/7-multidimensional_processing modality:general task:3d kw:anisotropy,z-spacing,sigma,per-axis,distance-transform,isotropic,z-stack,voxel size,anisotropic,z spacing,3d segmentation,3d filtering,anisotropic voxels,non-isotropic-->
- **WHEN** processing a z-stack whose z-spacing differs from xy pixel size (anisotropic)
  **DO**   set filter σ per-axis by pixel size (e.g. σz smaller when z-steps are larger), and use an anisotropy-aware distance transform (or resample to isotropic)
  **WHY**  ignoring anisotropy makes filters and distances wrong in physical units — "nearest" pixel is computed in voxels, not µm
  **AVOID** applying one isotropic σ or a voxel-only distance transform to anisotropic stacks
  SRC: bioimagebook · Multidimensional processing › "Isotropy and anisotropy" / distance transform in 3D

<!--c:bib-separable-and-split-channels status:approved src:bioimagebook chap:2-processing/7-multidimensional_processing modality:general task:3d kw:separable,performance,channels,time,split,combine,gpu,slow 3d processing,speed up filtering,separable filter,process channels separately,gpu acceleration,clij-->
- **WHEN** an nD workflow is slow, or spans channels/time
  **DO**   prefer separable filters (e.g. Gaussian: three 1D passes, not one dense nD kernel), process each channel/timepoint separately then combine ROIs/measurements, and consider GPU (CLIJ/clEsperanto) for the heavy steps
  **WHY**  the algorithm dominates cost — a separable 11³ filter is ~147 ops vs 1331; we rarely filter *across* channels/time anyway
  **AVOID** buying a bigger machine before making the algorithm efficient
  SRC: bioimagebook · Multidimensional processing › "Accelerating analysis" / "The most important performance consideration is the algorithm!"

<!--c:bib-3d-threshold-slice-count status:approved src:bioimagebook chap:2-processing/7-multidimensional_processing modality:general task:thresholding kw:3d,z-stack,out-of-focus,slice-count,histogram-bias,comparability,3d thresholding,z-stack threshold,different number of slices,out of focus planes-->
- **WHEN** auto-thresholding 3D stacks acquired with different numbers of slices / out-of-focus planes
  **DO**   extract a fixed number of slices centered on the volume of interest before computing the threshold
  **WHY**  extra out-of-focus planes shift the histogram and statistics, so the same structure gets thresholded differently across images
  **AVOID** thresholding whole stacks of varying depth and comparing the results directly
  SRC: bioimagebook · Multidimensional processing › "Thresholding" in 3D

<!--c:davide-zproject-simplify status:approved src:davide modality:general task:3d kw:z-projection,sum,average,dimensionality-reduction,2d,noisy,dense-stack,simplify,z projection,max projection,sum projection,flatten z-stack,project to 2d,simplify 3d-->
- **WHEN** 3D data is collected but the pipeline doesn't need full 3D reconstruction, or the data is low-quality and filtering hasn't solved it
  **DO**   as a last resort, Z-project / combine some slices or the whole volume (e.g. sum or average projection) and analyse in 2D
  **WHY**  very noisy or very dense z-stacks can over-complicate processing; 2D analysis is considerably easier and often sufficient
  **AVOID** forcing full 3D analysis when a projection answers the question
  SRC: Davide (internal domain expert)

<!--c:bib-verify-calibration status:approved src:bioimagebook chap:1-concepts/5-pixel_size modality:general task:measurement kw:calibration,pixel-size,units,µm,area,sanity-check,pixel size,scale bar,microns,physical units,spatial calibration-->
- **WHEN** reporting any measurement in physical units (length, area, volume)
  **DO**   verify the pixel size / calibration is present and correct, and sanity-check derived sizes for plausibility (area scales by pixel-width × pixel-height)
  **WHY**  calibration metadata is often missing or wrong after acquisition/format conversion, silently corrupting every physical measurement
  **AVOID** trusting the software's calibration without checking
  SRC: bioimagebook · Pixel size & dimensions › "Pixel sizes and measurements"

<!--c:bib-diffraction-limit-size status:approved src:bioimagebook chap:3-fluorescence/2-formation_spatial modality:fluorescence task:measurement kw:diffraction-limit,psf,size,sub-resolution,resolution,diffraction limit,measure small structures,size below resolution-->
- **WHEN** measuring sizes of very small structures (near/below a few hundred nm)
  **DO**   don't report sizes below the diffraction limit as real; sub-PSF objects all appear ~PSF-sized, and brightness (not apparent size) tracks their true size
  **WHY**  nothing images smaller than the Airy disk, so 2 nm, 20 nm and 200 nm objects can look identical in size
  **AVOID** quoting sizes of sub-resolution puncta from conventional fluorescence
  SRC: bioimagebook · Blur & the PSF › spatial resolution practical

<!--c:bib-detect-more-photons status:approved src:bioimagebook chap:3-fluorescence/3-formation_noise modality:fluorescence task:acquisition kw:noise,photons,snr,exposure,averaging,binning,low snr,noisy images,weak signal,improve signal-->
- **WHEN** images are too noisy to analyse reliably
  **DO**   the root fix is to detect more photons (longer/averaged exposures, frame averaging, binning); treat filters as damage control afterwards
  **WHY**  photon-noise SNR = √(signal), so more photons directly raise SNR; filtering only trades noise for lost detail
  **AVOID** relying on aggressive smoothing to rescue chronically photon-starved data
  SRC: bioimagebook · Noise › "If you want to reduce noise, you need to detect more photons"

<!--c:bib-average-frames status:approved src:bioimagebook chap:3-fluorescence/3-formation_noise modality:fluorescence task:preprocessing kw:averaging,frames,snr,registration,histogram-separation,frame averaging,reduce noise,improve snr-->
- **WHEN** you have (or can acquire) multiple frames of a static scene
  **DO**   average them (after registration if there's drift)
  **WHY**  averaging N independent frames lowers noise SD and improves peak separation in the histogram, making thresholding easier
  **AVOID** averaging frames with motion between them without aligning first
  SRC: bioimagebook · Noise › "Adding & averaging noisy images"

<!--c:bib-isolated-pixels-noise status:approved src:bioimagebook chap:3-fluorescence/3-formation_noise modality:fluorescence task:qc kw:isolated-pixels,hot-pixels,noise,psf,outliers,hot pixels,isolated bright pixels,single bright pixels,dead pixels-->
- **WHEN** a low-light image has isolated bright/dark single pixels
  **DO**   treat them as noise and remove outliers — a real structure must span at least a PSF, so a single pixel can't be one (unless the pixel size is larger than the PSF)
  **WHY**  in dark images, noise alone produces many extreme single pixels; they carry almost no real signal
  **AVOID** interpreting single-pixel spikes as structures, or removing them when pixel size ≫ PSF
  SRC: bioimagebook · Noise › "Other noise sources" practical

<!--c:bib-signal-dependent-noise status:approved src:bioimagebook chap:3-fluorescence/3-formation_noise modality:fluorescence task:measurement kw:poisson,signal-dependent,background,detectability,comparability,poisson noise,bright vs dark comparison,noise depends on intensity,shot noise-->
- **WHEN** comparing detections/intensities between bright and dark regions or images
  **DO**   account for photon noise being signal-dependent — detectability of a fixed increment depends on the local background
  **WHY**  Poisson noise SD grows as √signal, so counts/measurements from bright vs dark regions aren't directly comparable
  **AVOID** pooling detection results across very different background levels as if equally reliable
  SRC: bioimagebook · Noise › "Poisson noise & detection"

<!--c:bib-blur-is-gaussian-psf status:approved src:bioimagebook chap:3-fluorescence/2-formation_spatial modality:fluorescence task:concept kw:psf,blur,convolution,gaussian,wavelength,na,point spread function,why blurry,microscope blur,resolution and na-->
- **WHEN** reasoning about apparent size/intensity of fluorescent structures
  **DO**   model microscope blur as convolution with the PSF (≈ a Gaussian in the focal plane); its size falls with lower wavelength and higher NA (~hundreds of nm)
  **WHY**  blur alters apparent size, intensity and sometimes count of every structure, so measurements must be interpreted in its light
  **AVOID** treating measured sizes/intensities as blur-free ground truth
  SRC: bioimagebook · Blur & the PSF › "Blur & convolution" / "The size of the PSF"

<!--c:bib-z-resolution-worse status:approved src:bioimagebook chap:3-fluorescence/2-formation_spatial modality:fluorescence task:3d kw:z-resolution,axial,anisotropy,rayleigh,separation,axial resolution,z resolution,resolution in z,depth resolution-->
- **WHEN** resolving or separating structures along z
  **DO**   expect axial (z) resolution to be several times worse than lateral (xy) — structures separable in xy may merge in z
  **WHY**  the PSF is elongated along z (z-min > 3× r-airy even at high NA)
  **AVOID** assuming xy-separable objects are also separable in depth
  SRC: bioimagebook · Blur & the PSF › axial vs lateral resolution

<!--c:bib-gaussian-fit-localization status:approved src:bioimagebook chap:3-fluorescence/2-formation_spatial modality:fluorescence task:spot-detection kw:localization,gaussian-fit,subpixel,smlm,storm,palm,sub-pixel localization,gaussian fitting,single molecule localization,find spot center-->
- **WHEN** you need sub-pixel localization of well-separated point sources
  **DO**   fit a 2D Gaussian to each spot; its center localizes below pixel precision (basis of SMLM/STORM/PALM) and its σ equals the equivalent Gaussian-filter blur
  **WHY**  the Airy disk is well approximated by a Gaussian, so fitting recovers position more precisely than the pixel grid
  **AVOID** it when PSFs overlap — interference ruins the fit
  SRC: bioimagebook · Blur & the PSF › "Measuring PSFs & small structures"

<!--c:davide-deconvolution status:approved src:davide modality:fluorescence task:preprocessing kw:deconvolution,psf,deconvolutionlab,wavelength,na,refractive-index,colocalization,smlm,localization,deblur,remove blur,restore resolution-->
- **WHEN** ALL imaging parameters are known (laser wavelength, objective magnification, NA, refractive index)
  **DO**   approximate the PSF and run deconvolution (e.g. DeconvolutionLab, EPFL)
  **WHY**  deconvolution reassigns blurred signal to the correct voxel, which is a big help for colocalization and localization (e.g. SMLM)
  **AVOID** running deconvolution when the parameters aren't known — instead ask the user for the missing acquisition details when the task needs it
  SRC: Davide (internal domain expert) — see also [[bib-blur-is-gaussian-psf]]

<!--c:senft-reverse-workflow status:approved src:senft2023 modality:general task:planning kw:reverse-workflow,end-in-mind,design-backward,endpoint,pipeline-planning,plan the analysis,design pipeline,where to start,experimental design,plan backwards-->
- **WHEN** designing a new analysis pipeline or advising on an experiment
  **DO**   work backwards from the desired measurement/endpoint — let the final metric dictate the segmentation, the imaging, and the controls ("begin with the end in mind")
  **WHY**  bioimaging steps are tightly coupled; a decision at acquisition can make the needed measurement impossible, so the endpoint must drive the earlier steps
  **AVOID** treating the workflow as a linear pipeline built forward from whatever images exist
  SRC: senft2023 · Introduction ("reverse workflow")

<!--c:senft-pilot-first status:approved src:senft2023 modality:general task:planning kw:pilot,test-workflow,candidate-metric,scale-up,dry-run,pilot experiment,test on a few images,before batch,dry run-->
- **WHEN** committing to a full run over many images
  **DO**   pilot the entire workflow (and the candidate metrics) on a few images first, then scale up
  **WHY**  a cheap end-to-end pilot exposes a broken metric or acquisition choice before thousands of images are processed
  **AVOID** batch-processing the whole dataset before the pipeline has been validated on a subset
  SRC: senft2023 · Introduction / Quantitative data

<!--c:senft-parallel-controls status:approved src:senft2023 modality:general task:experiment-design kw:controls,parallel-processing,batch-effect,technical-variability,comparability,batch effect,technical variability,compare conditions fairly-->
- **WHEN** images from different conditions will be quantitatively compared
  **DO**   process the samples in parallel with the same reagents and identical acquisition settings, and include positive and negative controls
  **WHY**  differences in handling, reagents, or settings become confounders (batch effects) indistinguishable from the biology of interest
  **AVOID** comparing measurements across samples acquired or stained under different conditions
  SRC: senft2023 · Sample preparation / Quantitative data

<!--c:senft-validate-antibody status:approved src:senft2023 modality:fluorescence task:sample-prep kw:antibody,validation,specificity,secondary-only,isotype,knockout,controls,antibody specificity,immunofluorescence controls,is my antibody specific,staining controls-->
- **WHEN** an immunofluorescence result is being interpreted
  **DO**   validate antibody specificity — do not assume it; use secondary-only, isotype, and (ideally) knockdown/knockout controls, and optimize blocking
  **WHY**  antibodies frequently bind non-specifically; unvalidated signal can be an artifact, and nonoptimal blocking raises background
  **AVOID** treating a stained structure as the target without specificity controls
  SRC: senft2023 · Fixed samples

<!--c:senft-phototoxicity status:approved src:senft2023 modality:fluorescence task:acquisition kw:phototoxicity,photobleaching,live-cell,fluorophore,gentle-illumination,monomeric,live cell imaging,reduce light damage,fluorophore choice-->
- **WHEN** imaging live samples or anything prone to bleaching
  **DO**   choose bright, photostable, monomeric fluorophores and longer excitation wavelengths; use the gentlest illumination that works; watch the sample in brightfield for stress (blebs, rounding, stalled division)
  **WHY**  phototoxicity and photobleaching are cumulative and directly harm reproducibility in live-cell imaging; oligomerizing FPs cause localization artifacts
  **AVOID** maximizing excitation power for a brighter picture at the cost of sample health
  SRC: senft2023 · Live samples / Microscope settings

<!--c:senft-autofluorescence status:approved src:senft2023 modality:fluorescence task:sample-prep kw:autofluorescence,background,plastic,phenol-red,media,dim-signal,high background,background fluorescence,plastic autofluorescence-->
- **WHEN** dim signal must be measured against background
  **DO**   avoid autofluorescent substrates and media components (standard culture plastic, phenol red, serum, riboflavins); use glass or optical-polymer dishes and balance media for health vs background
  **WHY**  bright autofluorescence can swamp dim true signal, making it hard or impossible to quantify
  **AVOID** blaming faint results on the detector when the background is autofluorescent
  SRC: senft2023 · Live samples / Box 2 (autofluorescence)

<!--c:senft-modality-by-thickness status:approved src:senft2023 modality:fluorescence task:acquisition kw:modality,thickness,widefield,confocal,multiphoton,deconvolution,light-sheet,clearing,which microscope,confocal or widefield,thick sample,optical sectioning-->
- **WHEN** choosing a microscope modality for a sample
  **DO**   pick by optical thickness: <10 µm → widefield (or some super-res); 10–20 µm → widefield+deconvolution or confocal; 20–150 µm → confocal/multiphoton for optical sectioning; thick/whole tissue → clearing + light sheet
  **WHY**  thicker samples scatter light and add out-of-focus haze; optical sectioning or deconvolution is what restores contrast and resolution
  **AVOID** widefield alone on thick, scattering samples and then fighting the haze in analysis
  SRC: senft2023 · Optical properties of the sample

<!--c:senft-na-over-mag status:approved src:senft2023 modality:fluorescence task:acquisition kw:numerical-aperture,na,magnification,resolution,working-distance,objective,which objective,numerical aperture,magnification vs resolution,choose lens-->
- **WHEN** selecting or recommending an objective
  **DO**   prioritize numerical aperture (NA) over magnification for resolution and light collection, and check the working distance actually reaches the sample (through coverslip + mounting medium)
  **WHY**  NA sets resolving power and emission-collection efficiency; magnification alone does not resolve finer detail; too-short WD makes the scope "run out" of focus
  **AVOID** choosing a lens on magnification alone
  SRC: senft2023 · Microscope settings

<!--c:senft-no-saturation status:approved src:senft2023 modality:fluorescence task:acquisition kw:saturation,overexposure,exposure,intensity,quantification,averaging,don't saturate,exposure for quantification,camera exposure-->
- **WHEN** images will be used for intensity quantification
  **DO**   avoid saturation/overexposure (it destroys intensity information); prefer lower excitation power with longer camera exposure to limit bleaching; on PMT/scanning systems use line/frame averaging for SNR
  **WHY**  saturated pixels have lost their true value, so any intensity measurement on them is invalid — the same clipping problem as at the bit-depth level
  **AVOID** pushing exposure/gain until the brightest structures saturate
  SRC: senft2023 · Microscope settings

<!--c:senft-record-settings status:approved src:senft2023 modality:general task:reproducibility kw:acquisition-settings,metadata,reproducibility,consistency,report,record acquisition settings,reproducible imaging,imaging metadata,keep settings consistent-->
- **WHEN** running or reporting a multi-image experiment
  **DO**   record the acquisition parameters and keep them consistent, and report them with the results
  **WHY**  measurements are only comparable and reproducible if imaging conditions are documented and held fixed across the experiment
  **AVOID** changing acquisition settings midway through a comparative dataset
  SRC: senft2023 · Image acquisition (conclusion) / Best practices reporting

<!--c:senft-measure-on-original status:approved src:senft2023 modality:general task:measurement kw:intensity,original,corrected,segmentation-image,processed,measure,measure intensity,raw image,corrected image,quantify intensity-->
- **WHEN** extracting intensity measurements from segmented objects
  **DO**   measure on the original image (or the illumination/background-corrected image), using the segmentation only as a mask
  **WHY**  images enhanced/filtered for segmentation have altered pixel values; measuring intensity on them corrupts the quantification
  **AVOID** measuring intensity on the same processed image you thresholded
  SRC: senft2023 · Image analysis (measurement)

<!--c:senft-pipeline-order status:approved src:senft2023 modality:general task:pipeline kw:pipeline,order,denoise,illumination-correction,enhance,segment,measure,pipeline order,preprocessing order,analysis steps order-->
- **WHEN** assembling a segmentation-and-measurement pipeline
  **DO**   follow the canonical order: denoise → illumination/background correction → enhance for detection → segment → measure on the corrected image
  **WHY**  each stage prepares the next; correction before enhancement, and enhancement before segmentation, is what makes a simple threshold work
  **AVOID** thresholding raw images or enhancing before correcting illumination
  SRC: senft2023 · Image analysis (pipeline) / Common methods

<!--c:senft-illumination-correction status:approved src:senft2023 modality:fluorescence task:preprocessing kw:illumination-correction,shading,vignetting,spherical-aberration,background-correction,autofluorescence,patchy illumination,shading correction,uneven brightness-->
- **WHEN** the field has a brighter center or an autofluorescent background
  **DO**   apply illumination/shading correction and background correction as an early pipeline step (some scopes can also do it at acquisition)
  **WHY**  objective/optical vignetting and light-path autofluorescence add a spatially varying offset that biases both segmentation and intensity
  **AVOID** ignoring shading and letting it distort per-object measurements across the field
  SRC: senft2023 · Common image analysis methods

<!--c:senft-specific-question status:approved src:senft2023 modality:general task:statistics kw:metric-selection,question,specific,total-intensity,mean,nucleus,which measurement,which metric,what to measure-->
- **WHEN** deciding which measurement/metric answers a biological question
  **DO**   make the question as specific as possible first ("did total marker X increase within the nucleus?" not "did expression change?")
  **WHY**  a specific question narrows a host of plausible metrics to the right one; a vague question has many defensible-but-different answers
  **AVOID** picking a metric before the question is sharp
  SRC: senft2023 · Quantitative data (metric selection)

<!--c:senft-normality status:approved src:senft2023 modality:general task:statistics kw:normality,gaussian,multimodal,shapiro-wilk,kolmogorov-smirnov,parametric-test,which statistical test,significance test,compare groups,t-test,p-value-->
- **WHEN** choosing a statistical test for image-derived measurements
  **DO**   check normality (e.g. Shapiro–Wilk or Kolmogorov–Smirnov) before using tests that assume it; expect biological / pixel-derived data to be non-normal and often multimodal
  **WHY**  microscopy measurements frequently violate the Gaussian assumption (mixed populations, foreground/background), so parametric tests can mislead
  **AVOID** defaulting to a t-test/ANOVA without verifying the distribution
  SRC: senft2023 · Quantitative data (statistics)

<!--c:senft-define-n status:approved src:senft2023 modality:general task:statistics kw:sample-size,n,biological-replicate,technical-replicate,pseudoreplication,power-analysis,sample size,what is n,biological vs technical replicate,how many images,power analysis-->
- **WHEN** counting samples or planning how many images to acquire
  **DO**   define what "n" is (biological replicate vs technical replicate vs individual cell), be explicit about it in summaries, and use pilot data + power analysis to size the experiment
  **WHY**  treating cells from one animal as independent replicates (pseudoreplication) inflates significance; the right n depends on the model and effect size
  **AVOID** pooling cells across one sample and reporting them as independent n
  SRC: senft2023 · Quantitative data (sample number)

<!--c:senft-superplots status:approved src:senft2023 modality:general task:plotting kw:superplots,individual-points,distribution,summary-statistics,replicate,plot with points,show data points,bar chart alternative,show distribution-->
- **WHEN** plotting quantitative comparisons
  **DO**   show the distribution — individual data points alongside the summary statistic — and encode replicate structure (e.g. SuperPlots)
  **WHY**  a bare bar/mean hides the distribution shape and the replicate level, which is exactly what the reader needs to judge the result
  **AVOID** bar charts of means with no individual points
  SRC: senft2023 · Quantitative data / schmied2024 · figures

<!--c:reinke-match-problem-category status:approved src:reinke2024 modality:general task:validation kw:metric,problem-category,detection,semantic-segmentation,instance-segmentation,dice,which metric,validation metric,evaluate segmentation,dice score-->
- **WHEN** picking a metric to validate a segmentation/detection result
  **DO**   first phrase the task correctly — detection vs semantic segmentation vs instance segmentation — and choose a metric built for it
  **WHY**  a pixel-overlap metric (Dice/IoU) on a detection problem can score a prediction that finds *every* object *lower* than one that finds only one, because it never checks that all objects are found
  **AVOID** reporting Dice for a counting/detection task, or Pearson correlation for a segmentation-shaped task
  SRC: reinke2024 · P1 (inadequate problem category) / Fig. 1, Fig. 3

<!--c:reinke-instance-for-touching status:approved src:reinke2024 modality:general task:validation kw:instance-segmentation,touching,overlapping,clumped,dice,semantic,touching objects,overlapping cells,clumped objects,stuck together-->
- **WHEN** validating segmentation of touching or overlapping objects (clumped nuclei/cells)
  **DO**   use instance-segmentation metrics, not semantic-segmentation overlap (Dice)
  **WHY**  semantic metrics can't tell instances apart, so merged/split objects and overlapping instances go unmeasured
  **AVOID** judging a clumped-object segmentation by whole-foreground Dice
  SRC: reinke2024 · P2.4 / Extended Data Fig. 2a

<!--c:reinke-boundary-and-small status:approved src:reinke2024 modality:general task:validation kw:dice,iou,boundary,small-structures,hausdorff,hd95,overlap-metric,dice ignores boundary,small object metric,boundary metric,evaluate thin structures-->
- **WHEN** boundaries matter, or objects are small
  **DO**   know that overlap metrics (Dice/IoU) ignore boundary correctness and are dominated by size — a single-pixel error swings small-object Dice hugely; add a boundary metric, and prefer HD95 over raw Hausdorff (robust to outliers)
  **WHY**  overlap and boundary quality are different properties; small structures and thin/branchy shapes need boundary- or centerline-aware metrics (e.g. clDice)
  **AVOID** reporting only Dice for thin, small, or boundary-critical structures
  SRC: reinke2024 · P2.1/P2.2 / Fig. 4a, Extended Data Fig. 1

<!--c:reinke-complementary-metrics status:approved src:reinke2024 modality:general task:validation kw:metric-redundancy,dice,iou,complementary,ranking,synonyms,which metrics to report,dice and iou,redundant metrics-->
- **WHEN** reporting more than one validation metric
  **DO**   choose metrics that measure complementary properties, and watch for synonyms/mathematical relatives
  **WHY**  Dice and IoU are monotonically related — reporting both adds nothing; unknowingly using two names for the same metric distorts rankings
  **AVOID** padding a report with Dice + IoU as if they were independent evidence
  SRC: reinke2024 · P3.3 (metric relationships)

<!--c:reinke-class-imbalance status:approved src:reinke2024 modality:general task:validation kw:class-imbalance,accuracy,balanced-accuracy,mcc,rare-class,false-positive,class imbalance,rare class,accuracy misleading-->
- **WHEN** classes are imbalanced (rare positives)
  **DO**   avoid accuracy / balanced accuracy as the headline metric; use one that accounts for predictive value (e.g. MCC)
  **WHY**  under imbalance a model with many false positives can still post a high accuracy/BA, hiding its failure on the rare class
  **AVOID** reporting accuracy on a heavily imbalanced problem
  SRC: reinke2024 · P2.3 / Fig. 5a

<!--c:reinke-aggregation status:approved src:reinke2024 modality:general task:validation kw:aggregation,hierarchical,per-image,per-patient,global-average,pooling,how to average metric,aggregate scores,per image vs global-->
- **WHEN** aggregating a metric over many images/objects
  **DO**   respect the hierarchy — aggregate per image (and per patient/experiment) rather than pooling every pixel/object into one global average
  **WHY**  a global average lets many correct large structures mask errors on small ones, and over-represents whichever image contributed the most objects
  **AVOID** a single dataset-wide mean that ignores image/subject structure
  SRC: reinke2024 · P3.2 / Fig. 6b

<!--c:reinke-report-distributions status:approved src:reinke2024 modality:general task:validation kw:reporting,box-plot,distribution,jittered-dots,variability,best-run,report results,box plot,show variability,validation reporting-->
- **WHEN** reporting validation results
  **DO**   show the raw distribution (dots on top of the box), report variability across runs (not just the best run), and give SD/confidence intervals
  **WHY**  a bare box plot hides clusters and images where the algorithm failed; neural nets are non-deterministic, so a single best run overstates performance
  **AVOID** reporting only a box plot or only the best of several runs
  SRC: reinke2024 · P3.4 / Fig. 6c

<!--c:schmied-rotate-interpolation status:approved src:schmied2024 modality:general task:publishing kw:rotation,interpolation,90-degrees,vector,small-image,quantify-first,rotate image,crop image,resize figure,quantify before rotating-->
- **WHEN** rotating/cropping/resizing an image for a figure
  **DO**   do all quantification *before* these operations; rotate by multiples of 90° or in vector software to avoid interpolation (non-90° rotation resamples and changes pixel values, badly in images under ~100×100 px)
  **WHY**  interpolation alters the underlying intensity data; measurements taken afterward are on modified pixels
  **AVOID** measuring on a rotated/resized figure image
  SRC: schmied2024 · Image formatting

<!--c:schmied-contrast-consistency status:approved src:schmied2024 modality:general task:publishing kw:brightness,contrast,same-adjustment,faded,clipped,histogram,compare,same brightness contrast,adjust contrast fairly,identical adjustment-->
- **WHEN** displaying images that will be visually compared
  **DO**   apply identical brightness/contrast (and processing) to all of them, and set the range with the histogram — too wide fades detail, too narrow clips data
  **WHY**  different display adjustments make equal signals look different (or vice versa), misleading the reader
  **AVOID** auto-contrasting each panel independently in a comparison figure
  SRC: schmied2024 · Image colors and channels

<!--c:schmied-color-accessibility status:approved src:schmied2024 modality:general task:publishing kw:grayscale,colorblind,magenta-green,red-green,lut,calibration-bar,pseudocolor,figure colors,colormap,display colors-->
- **WHEN** choosing display colors for microscopy figures
  **DO**   prefer grayscale for single channels, or another uniform-perception, colorblind-safe LUT; for multicolor use colorblind-safe pairs (magenta/green, not red/green) and provide per-channel grayscale; add a calibration bar for pseudocolor/nonlinear LUTs
  **WHY**  grayscale conveys intensity most faithfully and accessibly; red/green excludes colorblind readers; pseudocolor without a scale is uninterpretable
  **AVOID** red/green merges and unlabeled pseudocolor
  SRC: schmied2024 · Image colors and channels / Fig. 4

<!--c:schmied-scalebar status:approved src:schmied2024 modality:general task:publishing kw:scale-bar,magnification,pixel-size,physical-size,annotation,scale bar,add scale bar,physical size in figure,annotate figure-->
- **WHEN** publishing any microscopy image
  **DO**   include a scale bar (or state the physical image size); explain every annotation; avoid magnification statements
  **WHY**  physical size isn't recoverable from the image alone, and magnification doesn't fix pixel size (binning/sampling do) — scale info is missing in ~half of publications
  **AVOID** relying on "×63" instead of a scale bar
  SRC: schmied2024 · Image annotation / Fig. 5

<!--c:schmied-formats status:approved src:schmied2024 modality:general task:data-management kw:png,jpeg,ome-tiff,lossless,compression,metadata,raw,save format,tiff vs jpeg,which file format,don't use jpeg-->
- **WHEN** saving/sharing images from an analysis
  **DO**   keep the original untouched; use lossless formats — OME-TIFF to preserve metadata, PNG over JPEG when a compressed copy is needed
  **WHY**  JPEG is lossy and discards data; OME-TIFF retains calibration/channel metadata needed to reanalyze
  **AVOID** overwriting the raw file or saving analysis inputs as JPEG
  SRC: schmied2024 · Image availability

<!--c:schmied-report-workflow status:approved src:schmied2024 modality:general task:reproducibility kw:workflow,reporting,versions,settings,code,example-data,reproducible,report methods,reproducible workflow,cite software versions,share pipeline,methods section-->
- **WHEN** publishing or documenting an analysis workflow
  **DO**   cite the tools and their exact versions, describe the step sequence, report key (non-default) settings, and share the code/pipeline plus example input+output
  **WHY**  image processing changes the data, so a result is only reproducible if the exact transform chain is recoverable
  **AVOID** "analyzed in Fiji" with no versions, settings, or shared pipeline
  SRC: schmied2024 · Checklists for analysis workflows / Fig. 3

<!--c:schmied-ml-training-bias status:approved src:schmied2024 modality:general task:machine-learning kw:deep-learning,training-data,bias,validation-set,disjoint,model,generalization,cellpose,stardist,deep learning,pretrained model-->
- **WHEN** applying or reporting a deep-learning model (Cellpose, StarDist, U-Net, etc.)
  **DO**   report the training/testing data and model access; keep validation data disjoint from training data; check and state how the model performs and fails on *your* data
  **WHY**  a model inherits the biases and label errors of its training set, and evaluating on training data hides its true generalization
  **AVOID** trusting a pretrained model on new data without validating on held-out examples
  SRC: schmied2024 · Machine learning workflows / reinke2024 · reference quality

<!--c:sc-bioformats-virtual-stack status:approved src:image.sc modality:general task:io kw:bio-formats,virtual-stack,large-file,out-of-memory,czi,nd2,series,open large image,out of memory,big file,virtual stack,load huge image-->
- **WHEN** opening a very large image (multi-GB CZI/ND2/OME-TIFF) or hitting OutOfMemory
  **DO**   open it with Bio-Formats as a *virtual stack* (planes loaded on demand), and pick the correct series for multi-series files
  **WHY**  a virtual stack avoids loading the whole volume into RAM; grabbing the wrong series silently analyses the wrong resolution level or scene
  **AVOID** loading a huge file fully into memory, or assuming series 0 is the one you want
  SRC: image.sc · "How to open large (100GB) CZI files" (t/10523) / "Virtual Stack BioFormats Macro" (t/23134)

<!--c:sc-stardist-global-normalization status:approved src:image.sc modality:fluorescence task:segmentation kw:stardist,normalization,percentile,per-tile,tiling,background,spurious,stardist normalization,spurious detections,stardist background,tile normalization-->
- **WHEN** running StarDist, especially on a large image that must be tiled
  **DO**   normalize with percentiles computed *globally* over the whole image; for big images use a whole-image/consistent normalization path (e.g. predict_instances_big) rather than default per-tile normalization
  **WHY**  each tile normalized independently rescales background-only tiles up to full range, producing spurious detections in empty regions
  **AVOID** relying on per-tile normalization when some tiles contain only background
  SRC: image.sc · "Normalization in Stardist" (t/41696) / "predict_instances_big()" (t/88871)

<!--c:sc-trackmate-blob-diameter status:approved src:image.sc modality:fluorescence task:spot-detection kw:trackmate,log,dog,estimated-blob-diameter,radius,calibrated-units,detection,tracking,cell tracking,time lapse,particle tracking,track cells,single particle tracking,trajectory,motion-->
- **WHEN** detecting spots/cells in TrackMate (LoG/DoG detector)
  **DO**   set "estimated blob diameter" to the *actual* diameter of the objects in calibrated units (µm), matching the Gaussian scale to object size
  **WHY**  the LoG detector is scale-selective — a diameter far from the true size misses real spots or fragments/merges them; it's the single most decisive detection parameter
  **AVOID** leaving the default diameter, or entering a value in the wrong units
  SRC: image.sc · "TrackMate — how detector uses estimated blob diameter and threshold" (t/11067)

<!--c:sc-cellpose-diameter status:approved src:image.sc modality:general task:segmentation kw:cellpose,diameter,rescale,over-segmentation,flow-threshold,cellprob-threshold,background,cellpose diameter,cellpose over-segmentation,cellpose too many cells,cell size cellpose-->
- **WHEN** segmenting with Cellpose and getting too many/too few or noisy objects
  **DO**   set the diameter to the true mean object size (Cellpose internally rescales to its trained ~30 px); then tune cellprob_threshold up and flow_threshold to suppress background/noise detections
  **WHY**  a wrong diameter mis-scales the image and drives over- or under-segmentation; thresholds control how much faint background is accepted as an object
  **AVOID** fixing bad output by only nudging thresholds while the diameter is wrong
  SRC: image.sc · "Cellpose size parameter bias" (t/72892) / "Cellpose cell diameter does not scale linearly" (t/64791)

<!--c:sc-recheck-calibration status:approved src:image.sc modality:general task:measurement kw:set-scale,calibration,global-scale,reset,conflict,pixels,microns,processing,pixel size,scale bar,set scale,calibration lost-->
- **WHEN** measuring in physical units in ImageJ/Fiji, especially after processing or format conversion
  **DO**   re-check the image scale (Set Scale) right before measuring — calibration is per-image and easily lost or overridden by a "global scale", and some plugins reset it to a default (e.g. 96 pixels/inch)
  **WHY**  a silently reset or conflicting calibration makes every physical measurement wrong while the numbers still look plausible
  **AVOID** trusting that calibration survived a duplicate, conversion, or plugin step
  SRC: image.sc · "Set scale — Pixels to µm" (t/37910) / "Global Scale Automatically Resetting Itself" (t/256)

<!--c:sc-analyze-particles-order status:approved src:image.sc modality:general task:measurement kw:analyze-particles,watershed,exclude-on-edges,size-filter,circularity,touching,count,analyze particles,count particles,exclude on edges,size filter,circularity filter-->
- **WHEN** counting/measuring objects with Analyze Particles on a binary mask
  **DO**   separate touching objects first (watershed on the distance map), then run Analyze Particles with Exclude-on-Edges plus size and circularity filters
  **WHY**  unseparated clumps count as one object; edge-clipped objects give biased partial areas; size/circularity removes debris — order and filters together decide the counts
  **AVOID** counting a raw threshold mask without splitting clumps or excluding edge-truncated objects
  SRC: image.sc · "Watershed and counting — irregular particles" (t/8927) / "Exclude on Edges" (t/81131)

<!--c:sc-threshold-per-channel status:approved src:image.sc modality:fluorescence task:thresholding kw:threshold,per-channel,multichannel,independent,stain,distribution,per channel threshold,multiple stains-->
- **WHEN** segmenting a multichannel image where each channel is a different stain/marker
  **DO**   determine the threshold independently per channel (each stain has its own intensity distribution)
  **WHY**  one shared threshold assumes the channels share an intensity distribution; they don't, so a value tuned on one channel mis-segments the others
  **AVOID** applying a single global threshold across all channels
  SRC: image.sc · "Fluorescence intensity thresholding and integrated density" (t/118275)

<!--c:sc-coloc-pearson-vs-manders status:approved src:image.sc modality:fluorescence task:colocalization kw:colocalization,pearson,manders,threshold,occupancy,jacop,costes,coloc,two channel overlap-->
- **WHEN** quantifying colocalization of two channels
  **DO**   know that Pearson's coefficient is a global, threshold-independent metric; prefer (thresholded) Manders' coefficients when the two channels have very different signal occupancy, and set the coloc thresholds deliberately (e.g. Costes)
  **WHY**  Pearson ignores thresholds entirely and is biased when one channel is much sparser; Manders reflects the fraction of one signal overlapping the other and is threshold-sensitive
  **AVOID** reporting Pearson alone and expecting it to respond to thresholds, or using it when occupancy differs greatly
  SRC: image.sc · "JACoP BIOP Version, Pearson's Coefficient" (t/62687)

<!--c:sc-no-rgb-for-quant status:approved src:image.sc modality:general task:measurement kw:rgb,8-bit,16-bit,intensity,truncate,integrated-density,ctcf,quantification,measure intensity,fluorescence intensity,quantify brightness,mean gray value-->
- **WHEN** quantifying fluorescence intensity
  **DO**   measure on the original 16-bit image; do NOT convert to RGB (it silently drops to 8-bit and truncates the intensity range); subtract background first, and remember Integrated Density = Area × Mean Gray Value (CTCF ≈ IntDen − background_mean × area)
  **WHY**  RGB conversion looks identical on screen but rescales/clips the data, corrupting every intensity measurement — visible only in the histogram
  **AVOID** running quantification on an RGB or auto-converted 8-bit copy
  SRC: image.sc · "Pipeline for intensity measurement" (t/74859) / "Intensity quantification by CTCF" (t/64913)

<!--c:sc-flatfield-reference status:approved src:image.sc modality:fluorescence task:preprocessing kw:flat-field,illumination-correction,reference,blank,sample-free,shading,uneven,flat field image,vignetting,uneven illumination-->
- **WHEN** correcting uneven illumination / shading
  **DO**   acquire a real flat-field reference during the imaging session (a sample-free region / blank), and correct with it — the closer the estimate is to the true flat field, the better; for a whole set, estimate from many images
  **WHY**  a measured flat field beats a guessed one; correction quality is limited by how well the estimate matches the actual illumination profile
  **AVOID** relying on a synthetic background estimate when a blank could have been imaged
  SRC: image.sc · "I need help with setting an appropriate threshold" (t/35360)

<!--c:sc-ratiometric-mask status:approved src:image.sc modality:fluorescence task:measurement kw:ratiometric,ratio,mask,background,divide,threshold,over-processing,ratio image,mask before ratio,fret ratio,divide channels-->
- **WHEN** computing a ratio of two channels (e.g. ratiometric imaging)
  **DO**   mask out the background (threshold to the signal) before dividing, and don't over-process — if the raw ratio on signal pixels is already correct, keep it
  **WHY**  dividing background by background produces huge, meaningless ratios that dominate the image; you only care about the ratio where there is signal
  **AVOID** computing the ratio over the whole frame including background, or stacking corrections that don't improve the answer
  SRC: image.sc · "Shading Correction and Background Subtraction for Ratiometric Analysis" (t/115421)

<!--c:sc-reslice-to-fit-tool status:approved src:image.sc modality:general task:preprocessing kw:reslice,axis-order,line-scan,xt,time-series,bleach-correction,dimension,reorder dimensions,wrong dimension order,axis order,reshape stack-->
- **WHEN** a tool expects a specific dimension order your data doesn't have (e.g. bleach correction wants XYT but you have an XT line scan)
  **DO**   reslice/reorder the axes so the data matches the tool's expected shape (XT → a 1×a×b time series), then run the tool
  **WHY**  many tools are hard-coded to one dimension layout; reshaping is often all that's needed rather than a different tool
  **AVOID** concluding a capability is missing when a reslice would present the data in the expected order
  SRC: image.sc · "Photobleaching for line scan images" (t/5553)

<!--c:sc-batchmode-reality status:approved src:image.sc modality:general task:performance kw:setbatchmode,headless,speed,display,plugin,subprocess,startup,batch,batch mode,speed up macro,faster processing-->
- **WHEN** trying to speed up batch processing in ImageJ/Fiji
  **DO**   use setBatchMode to remove display/redraw overhead (big wins for light, GUI-bound operations); but for heavy plugin/model runs (ilastik, deep learning) the cost is compute + startup, so batch the external tool over many images per invocation (e.g. ilastik headless via subprocess) to amortize startup
  **WHY**  setBatchMode only hides the GUI; it doesn't accelerate the actual computation, and some plugins can't return ROIs while in batch mode
  **AVOID** expecting setBatchMode to speed up a compute-bound plugin, or restarting a heavy tool per image
  SRC: image.sc · "Batch mode issue when using ilastik Fiji plugin" (t/55975)

<!--c:sc-model-for-crowded-nuclei status:approved src:image.sc modality:fluorescence task:segmentation kw:stardist,cellpose,overlapping,crowded,nuclei,threshold,watershed,instance-model,crowded cells,dense nuclei,clumped nuclei,stuck together,cells touching-->
- **WHEN** threshold+watershed keeps merging crowded/overlapping nuclei
  **DO**   try a trained instance-segmentation model (StarDist for roundish nuclei, Cellpose for varied cells) before hand-tuning classical steps further
  **WHY**  learned models separate touching convex objects that defeat intensity-based watershed; users repeatedly report success switching to StarDist 2D on DAPI
  **AVOID** endlessly tuning threshold/watershed on densely packed nuclei when a trained model is available
  SRC: image.sc · "3D segmentation in tissue: counting nuclei" (t/43286)

<!--c:sc-pipeline-size-mismatch status:approved src:image.sc modality:general task:debugging kw:size-mismatch,resize,pipeline,cellprofiler,dimension,upstream,size mismatch error,dimensions don't match,cellprofiler error,resize module-->
- **WHEN** a pipeline step errors about image/size mismatch
  **DO**   trace the inputs upstream — a mismatch usually means some inputs passed through a resize/crop module and others didn't; make all inputs to the step share dimensions
  **WHY**  operations that combine images (masking, relate, watershed-from-markers) require identical dimensions; a stray resize upstream is the common culprit
  **AVOID** debugging the failing module itself before checking whether its inputs were resized inconsistently
  SRC: image.sc · "Error messages from watershed segmentation in 3D z-stack" (t/76209)

<!--c:sc-spot-detector-for-puncta status:approved src:image.sc modality:fluorescence task:spot-detection kw:puncta,spots,comdet,trackmate,log,threshold,analyze-particles,count,count spots,foci,fluorescent dots,count objects-->
- **WHEN** counting sub-diffraction puncta (single molecules, antibody dots, foci) that bleed together
  **DO**   use a dedicated spot detector (ComDet, or TrackMate's LoG) with a small particle size, not threshold + Analyze Particles; and accept ~5–10% error vs manual ground truth as the cost of automation
  **WHY**  thresholding merges touching diffraction-limited spots and picks up autofluorescence; a LoG-based detector is built to localize point sources
  **AVOID** thresholding + particle analysis for spots at/below the resolution limit, or expecting exact agreement with hand counts
  SRC: image.sc · "Plugin for counting antibodies" (t/72189)

<!--c:sc-weka-save-data-not-classifier status:approved src:image.sc modality:general task:machine-learning kw:weka,trainable,classifier,training-data,traces,accumulate,retrain,random-forest,weka training,trainable weka,train on multiple images,accumulate training-->
- **WHEN** training a Trainable Weka (or similar) classifier across several images
  **DO**   save the training *data* (labels/traces), not just the classifier, and reload it to keep accumulating — retraining rebuilds the model from scratch and loses earlier traces (FastRandomForest is not updateable)
  **WHY**  each "train" call on the default classifier starts over, so adding a second image's traces silently discards the first unless the data is persisted
  **AVOID** expecting successive trainings to accumulate by saving/reloading only the classifier
  SRC: image.sc · "Train Weka segmentation classifier on many images" (t/3613)

<!--c:sc-classifier-features-and-normalize status:approved src:image.sc modality:general task:machine-learning kw:pixel-classifier,weka,ilastik,features,memory,normalize,bit-depth,generalize,weka features,pixel classification,classifier generalize,too many features-->
- **WHEN** building a pixel classifier (Weka/ilastik) meant to work on new images
  **DO**   keep the feature set small and informative (each feature is a 32-bit copy held in RAM), and normalize both training and test images the same way
  **WHY**  a classifier is tied to the intensity range/bit-depth it was trained on — one trained on RGB or 16-bit won't work on 8-bit unless intensities are matched; too many features exhaust memory on large images
  **AVOID** enabling every feature, or applying a model to a different image type/bit-depth without normalizing
  SRC: image.sc · "Sensitivity of Weka Segmentation Scripts / Input images" (t/5267)

<!--c:sc-binary-black-background status:approved src:image.sc modality:general task:morphology kw:binary,black-background,foreground,invert,process-binary-options,analyzed-region,black background,inverted mask,wrong region measured,binary options-->
- **WHEN** a binary/morphology/measurement step seems to operate on the wrong region (e.g. measuring background as the object, inverted mask)
  **DO**   check Process › Binary › Options… "Black background" — it defines which value (0 vs 255) is foreground, and most plugins analyze whatever is foreground
  **WHY**  a mismatched Black-background setting silently inverts foreground/background, so thresholds and particle analysis act on the complement of what you intended
  **AVOID** debugging the plugin before confirming the binary foreground convention
  SRC: image.sc · "Switch bone and background segment setting — BoneJ threshold" (t/64647)

<!--c:sc-findmaxima-prominence status:approved src:image.sc modality:general task:detection kw:find-maxima,prominence,noise-tolerance,gaussian-blur,segmented-particles,blob,count,count blobs,find maxima,local maxima,count objects-->
- **WHEN** counting/segmenting blob-like objects and threshold+watershed is fiddly
  **DO**   pre-smooth (a generous Gaussian blur), then Find Maxima with "Prominence" set near the noise floor and output "Segmented Particles", then Analyze Particles with a size filter
  **WHY**  Prominence is an intuitive single noise-tolerance knob (how far a peak must stand above its surroundings), and pre-smoothing stops noise from spawning spurious maxima
  **AVOID** running Find Maxima on a noisy raw image, or hand-tuning a watershed when prominence-based maxima suffice
  SRC: image.sc · "Area measurements on histo image" (t/33241)

<!--c:sc-dl-channel-consistency status:approved src:image.sc modality:general task:machine-learning kw:cellpose,stardist,channel,training,prediction,epochs,masks,retrain,deep learning segmentation,retrain model-->
- **WHEN** retraining or applying a deep-learning segmenter (Cellpose/StarDist) and results are poor
  **DO**   make the channel-to-segment (and all preprocessing) identical between training and prediction; and note that more epochs/augmentation help only when you have very few masks — with hundreds, they barely matter
  **WHY**  a train/predict channel mismatch means the model learned one channel and is scored on another; and once you have plenty of masks, added epochs mostly overfit rather than improve
  **AVOID** cranking epochs to fix bad output while the train/predict channel or normalization silently differ
  SRC: image.sc · "Challenging Segmentation with cellpose" (t/103618)

<!--c:sc-color-deconvolution status:approved src:image.sc modality:brightfield task:preprocessing kw:color-deconvolution,unmix,stain,h&e,dab,ihc,histology,separate,unmix stains,separate stains,stain separation,alizarin red-->
- **WHEN** quantifying stains in brightfield histology (H&E, DAB/IHC, Alizarin red)
  **DO**   separate the stains with colour deconvolution / UnmixColors into per-stain grayscale images (sampling the actual stain colors from your image), then threshold each
  **WHY**  RGB channels mix the stains; color deconvolution recovers the amount of each dye, which is what you actually want to measure
  **AVOID** thresholding raw R/G/B channels to isolate a stain
  SRC: image.sc · "Image of calcification" (t/92169)

<!--c:sc-stardist-large-image-tiling status:approved src:image.sc modality:fluorescence task:segmentation kw:stardist,large-image,tiling,gpu,nms,post-processing,memory,multi-core,stardist large image,stardist tiling,stardist memory,stardist gpu-->
- **WHEN** running StarDist on an image/stack too big to process at once
  **DO**   enable internal tiling (overlapping tiles); know the pipeline is NN prediction (GPU-accelerable, needs a normalized input) followed by non-max-suppression post-processing (CPU, multi-core)
  **WHY**  tiling bounds memory; understanding the two-stage GPU/CPU split tells you where the time goes and why a strong multi-core CPU still matters even with a GPU
  **AVOID** trying to predict a huge image in one pass, or expecting the GPU to accelerate the NMS step
  SRC: image.sc · "[NEUBIAS] StarDist webinar Q&A" (t/38274)

<!--c:sc-one-marker-per-object status:approved src:image.sc modality:general task:detection kw:local-maxima,h-maxima,morphological-domes,ultimate-points,one-per-object,centroid,one seed per object,single centroid,ultimate points,marker per cell-->
- **WHEN** you need exactly one marker/seed per object (centroid, seed for watershed)
  **DO**   use local maxima or h-maxima (morphological domes / h-convex transform), not ultimate erosion points
  **WHY**  ultimate erosion points can return several maxima per object; h-maxima with a height threshold collapses each object to one robust marker
  **AVOID** ultimate points when a single seed per object is required
  SRC: image.sc · "Multiple ultimate points per ROI — only want one per ROI" (t/64920)

<!--c:sc-labels-to-rois-bridge status:approved src:image.sc modality:general task:pipeline kw:labels,rois,cellpose,stardist,imagej,compartment,integration,measure,label image to rois,cellpose to imagej,convert masks to rois,measure model output-->
- **WHEN** you have a label image from a model (Cellpose/StarDist) but need per-object measurements in ImageJ
  **DO**   convert the labels image to ROIs (Fiji "Label image to ROIs"), and combine a learned mask for one compartment (e.g. cytoplasm/cell) with classical thresholding for another (e.g. nucleus) within it
  **WHY**  the labels image is the portable bridge between a Python/deep-learning segmenter and ImageJ's measurement tools; mixing learned + classical steps handles compartments no single tool segments well
  **AVOID** treating the model output as a dead end because it isn't already ImageJ ROIs
  SRC: image.sc · "Cell detection with unstained nucleus" (t/115496)

<!--c:lj-verify-per-subgroup status:approved src:lukas modality:general task:validation kw:subgroup,subgroups,stratified,per condition,per group,per folder,per subfolder,condition,conditions,treatment,control,genotype,timepoint,replicate,batch,slide,well,plate,acquisition session,directory structure,folder structure,subfolders,filename pattern,file naming,name prefix,naming convention,state ledger,ask the user,spot check,sanity check,representative sample,sample of images,test on a few images,check a few images,validate the pipeline,verify the pipeline,before the full run,whole dataset,pooled sample,random sample-->
- **WHEN** validating a pipeline on a subset before running it over a dataset that contains distinct subgroups (conditions, treatments, genotypes, timepoints, slides/wells/plates, acquisition sessions)
  **DO**   work out what the subgroups are, then draw the verification sample **per subgroup** and check each one separately. The grouping is usually recoverable without asking: from the **directory structure** (one folder per condition/timepoint/slide), from a **shared pattern in the filenames** (`ctrl_*` vs `treated_*`, a well ID like `A01`, a date or run prefix), or from what the **state ledger** already records about the dataset. Ask the user only when those disagree or reveal nothing — and confirm the grouping before relying on it
  **WHY**  one subgroup can differ from the rest in intensity, morphology, density or artifacts and silently break a pipeline tuned on the others, while a pooled sample still looks fine — the failure then propagates through the whole analysis unseen
  **AVOID** validating on a single pooled random sample over all images and declaring the pipeline good; equally, assuming a flat folder means a single group — the grouping is often in the filenames
  SRC: Lukas (internal domain expert) — see also [[reinke-aggregation]]

<!--c:lj-nuclei-within-cell-mask status:approved src:lukas modality:general task:segmentation kw:nuclei,nucleus,nuclear,nuclei mask,nuclear mask,cell mask,cytoplasm,cytoplasmic,whole-cell,compartment,compartments,two channels,ch2,nuclear channel,segment nuclei and cells,nuclei inside cells,nuclei within cells,assign nuclei to cells,one nucleus per cell,orphan nuclei,parent child,relate objects,match nuclei to cells,cellpose channels,derive nuclei from cells,constrain segmentation-->
- **WHEN** nuclei must be segmented in data where a cell / cytoplasm mask already exists (an earlier Cellpose or StarDist run, or a whole-cell channel)
  **DO**   reuse that mask to constrain the nuclei step — segment nuclei *inside* each existing cell label, or hand the nucleus channel to Cellpose as the second channel (`ch2`) so one model call returns both — instead of segmenting nuclei independently over the whole field
  **WHY**  each nucleus is then assigned to exactly one cell by construction; orphan nuclei outside any cell, double assignments and background false positives disappear, and the per-cell table needs no matching step
  **AVOID** segmenting nuclei globally and matching them to cells afterwards by overlap or centroid distance
  SRC: Lukas (internal domain expert) — see also [[sc-labels-to-rois-bridge]]
