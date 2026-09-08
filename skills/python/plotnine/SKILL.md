---
name: plotnine
description: >-
  Grammar-of-graphics publication plotting with plotnine 0.15.7 (ggplot2 for Python) — a
  STAGE 2 alternative to the seaborn 'plotting' skill, building figures from layered
  aes()/geom_*/scale_*/facet_*/theme(). Same publication standards: 300 DPI dual PNG+SVG,
  colorblind hex (#0173b2 blue, #de8f05 orange; never red/green; viridis via scale_*_cmap),
  >=14pt axis labels with units, and ***/**/*/ns significance read FROM Statistics_Results.csv
  (never recomputed). CRITICAL plotnine gotchas: save with verbose=False or a "Saving W x H
  image" PlotnineWarning hits stderr; discrete axis positions are 1-BASED (first category is
  x=1, not 0) which matters for significance brackets; geom_smooth(method="lowess") draws no
  CI band (use "lm" or "loess"); geom_jitter/geom_sina never silently drop points (unlike
  seaborn swarmplot). Use when a task wants ggplot-style or faceted small-multiple figures.
---

# Grammar-of-Graphics Plotting with plotnine (STAGE 2)

plotnine is **ggplot2 for Python**: a figure is a *sum of layers* over a tidy DataFrame.
This skill is an **alternative** to the seaborn `plotting` skill, not a replacement — reach
for it when a task asks for ggplot-style figures, or when the figure is naturally built by
**faceting** (small multiples) or by **stacking layers** (points + fit + CI + annotations).
For a quick single boxplot or regplot, the seaborn `plotting` skill is just as good; the two
skills share the *same publication standards* below.

Verified against **plotnine 0.15.7, matplotlib 3.11.0, pandas 3.0.3** in the main env. Every
behavioural claim in `PLOTNINE_RECIPES.md` was produced by rendering a figure and inspecting it.

> **STAGE SEPARATION.** Plotting is STAGE 2. NEVER combine statistics and plotting in one
> script. Read the values STAGE 1 already wrote to `Statistics_Results.csv`. Do NOT compute a
> new p-value, correlation, or fit statistic here — if the figure recomputes it, the figure and
> the text can silently disagree. (A `geom_smooth` *visual* trend line is fine; the *reported*
> r and p must come from the CSV.)

## The grammar in one screen

A plot is `ggplot(data, aes(...))` plus layers joined with `+`:

```python
from plotnine import *
p = (ggplot(df, aes(x="condition", y="area_um2"))   # DATA + AESTHETIC MAPPING
     + geom_boxplot(aes(fill="condition"))            # GEOM  (what marks to draw)
     + geom_jitter(width=0.2, alpha=0.5)              # another layer, drawn on top
     + scale_fill_manual(values=["#0173b2", "#de8f05"])  # SCALE (map data->pixels/colour)
     + facet_wrap("plate")                            # FACET (small multiples), optional
     + labs(x="Condition", y="Cell Area (μm²)", title="…")
     + theme_matplotlib() + theme(figure_size=(6, 6)))  # THEME (non-data ink)
p.save("figures/fig.png", dpi=300, verbose=False)
```

Read `PLOTNINE_CHEATSHEET.md` for the seaborn→plotnine translation table and the layer catalogue.

## The four plotnine traps (read these before you write code)

**1. `save()` is verbose by default — pass `verbose=False`.** `p.save("f.png", dpi=300)`
emits `PlotnineWarning: Saving 6 x 6 in image.` and a `Filename:` line to **stderr**. It is
harmless but noisy and looks like an error in logs. ALWAYS `p.save(..., verbose=False)`.

**2. Discrete axis positions are 1-BASED.** The first category sits at `x=1`, the second at
`x=2` — NOT 0-based like matplotlib/seaborn. A significance bracket between the two groups of a
two-group test spans `x=1..2`. Fix category order (and therefore positions) with an ordered
`pd.Categorical` or `scale_x_discrete(limits=[...])`, then place the bracket at the 1-based
index of each compared group.

**3. `geom_smooth(method="lowess")` draws NO confidence band** and warns
`Confidence intervals are not yet implemented for lowess smoothings`. If you want a shaded CI,
use `method="lm"` (linear, statsmodels) or `method="loess"` (curved, scikit-misc). Use `lowess`
only when you deliberately want a trend line without a band.

**4. Use `geom_jitter` / `geom_sina` for raw points, never expect a swarm.** plotnine's
`geom_jitter` (stripplot-equivalent) and `geom_sina` (beeswarm-equivalent) **never silently
drop points** — this is a genuine advantage over `seaborn.swarmplot`, which omits points that
do not fit and only warns. Overlay raw points freely.

## Publication standards (identical to the seaborn plotting skill)

1. **Resolution & formats.** Save at **300 DPI** and in **both** PNG (raster, viewing) and SVG
   (vector, editing). Verified: `p.save("f.png", dpi=300)` yields a PNG reporting
   `dpi=(299.9994, 299.9994)` — the float wobble is normal.
   ```python
   p.save("figures/fig.png", dpi=300, width=6, height=6, verbose=False)
   p.save("figures/fig.svg",          width=6, height=6, verbose=False)
   ```
2. **Colourblind-safe colour.** plotnine has **no built-in `colorblind` palette**. Use
   `scale_color_manual`/`scale_fill_manual` with the verified hex — blue `#0173b2`, orange
   `#de8f05`, green `#029e73`, vermilion `#d55e00`, purple `#cc78bc`. **Never red/green.** For
   continuous fills (heatmaps) use `scale_fill_cmap(cmap_name="viridis")` (or `plasma`/`cividis`).
3. **Grayscale safety.** Colour alone must not carry meaning — add `shape=`/`linetype=`
   aesthetics (`scale_shape_manual`, `scale_linetype_manual`).
4. **Typography.** axis titles ≥14pt, tick text ≥12pt, plot title ≥16pt, legend ≥12pt:
   ```python
   + theme(axis_title=element_text(size=14), axis_text=element_text(size=12),
           plot_title=element_text(size=16), legend_title=element_text(size=12),
           legend_text=element_text(size=12))
   ```
5. **Line widths.** geom lines `size=1.0`+ (plotnine line "size" is in mm; ~1.0 ≈ a heavy line).
6. **Axis labels carry units** — `labs(y="Cell Area (μm²)")`, never `"Area"`. If STAGE 0 never
   calibrated, label it `(px²)` honestly.
7. **Significance notation** — `***` p<0.001, `**` p<0.01, `*` p<0.05, `ns` p≥0.05, with a
   bracket connecting the compared groups. Take the p-value **from the CSV**. There is no
   built-in bracket; build it from `annotate("segment", …)` × 3 + `annotate("text", …)` and
   `expand_limits(y=…)` so it is not clipped (see `WORKFLOW_BOXPLOT_SIGNIFICANCE.py`).
8. **Save into `figures/`** under the project directory.

## Plot type by question (plotnine geom)

| Question | plotnine |
|---|---|
| Do two/several groups differ? | `geom_boxplot` + `geom_jitter` (or `geom_violin` + `geom_sina`) |
| …few points (n<20)? | `geom_point` + `stat_summary(fun_data="mean_cl_boot", geom="pointrange")` |
| Are x and y related? | `geom_point` + `geom_smooth(method="lm")` (CI band from the fit) |
| Distribution shape | `geom_histogram` / `geom_density` (often `+ facet_wrap`) |
| Same plot across a factor | any geom **`+ facet_wrap("col")`** or `facet_grid("row ~ col")` |
| Many features × samples | `geom_tile(aes(fill=…))` + `scale_fill_cmap(cmap_name="viridis")` |
| Counts per category | `geom_bar` (counts) / `geom_col` (pre-summed) — overlay points if means |

A bar of means hides the distribution — prefer boxplot+jitter, or overlay the points.

## Coding rules for a plotnine STAGE-2 script

- `from plotnine import *` (or import the specific names). Assign the plot to a variable and
  build it with `+`; `p.save(..., dpi=300, verbose=False)` for **both** PNG and SVG.
- The main-env preamble pre-imports `pd/np/plt/sns`; plotnine is independent of them — just
  `import` it. Set the matplotlib **Agg** backend (headless container) before importing pyplot
  if you run the file directly.
- ALWAYS raw strings for Windows paths: `r"C:\Users\..."`.
- Read the scientific goal / calibration / group labels from any "PROJECT STATE" block in your
  input (plot titles, μm² vs px², group names).
- Read `p_value` and `significance` from `Statistics_Results.csv`; never recompute them.

## Verification — fail loudly, not silently

RAISE `ValueError("VERIFICATION FAILED: <what>")` ONLY on conditions always true for a correct
run: the PNG and SVG exist and are non-empty; the columns you read exist; the number of plotted
groups equals the number in the CSV; any p-value read is in [0,1].

`print("WARNING: …")` and continue for data-dependent facts: small n, a non-significant result
(annotate `ns` — it is publishable), NaNs in a column you are not drawing. Never recompute a
statistic in the plotting script.

## Documentation requirement

Your script `description` MUST state: the test + result you read from the CSV, the plotnine
geoms/scales used, the palette + DPI + formats, and the output paths. Example: *"plotnine
boxplot + geom_jitter, significance bracket from Mann-Whitney p=0.023 (**) read from
Statistics_Results.csv, colorblind manual fill, PNG 300 dpi + SVG to figures/."*

## Files

| File | What it covers |
|---|---|
| `PLOTNINE_CHEATSHEET.md` | The grammar (aes/geom/scale/facet/theme), a seaborn→plotnine translation table, the layer catalogue, saving/theming/palette recipes |
| `PLOTNINE_RECIPES.md` | Verified 0.15.7 behaviour & gotchas: verbose-save, 1-based positions, lowess-no-CI, colourblind hex, viridis, the significance-bracket recipe, `stat_summary`, faceting |
| `WORKFLOW_BOXPLOT_SIGNIFICANCE.py` | `Statistics_Results.csv` + raw data → boxplot + `geom_jitter` + significance bracket at 1-based positions → PNG (300 dpi) + SVG |
| `WORKFLOW_CORRELATION_PLOT.py` | `Statistics_Results.csv` + raw data → scatter + `geom_smooth` (lm, or loess when Pearson/Spearman disagree) annotated with r,p read from the CSV → PNG + SVG |
| `WORKFLOW_FACETED_DISTRIBUTIONS.py` | raw measurements → faceted small-multiple distributions (`facet_wrap`) with colourblind fill → PNG + SVG (grammar-of-graphics showcase) |

All three workflows run untouched on synthetic data.
