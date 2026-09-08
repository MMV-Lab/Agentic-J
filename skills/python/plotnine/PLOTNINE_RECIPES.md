# plotnine — Recipes & Verified Behaviour

Verified against **plotnine 0.15.7, matplotlib 3.11.0, pandas 3.0.3**, main env. Every claim
below was produced by rendering a figure and inspecting the output.

---

## 1. `save()` is verbose by DEFAULT — it warns to stderr

```python
p.save("f.png", dpi=300, width=6, height=6)                # verbose=True (default)
# -> stderr: PlotnineWarning: Saving 6 x 6 in image.
# -> stderr: PlotnineWarning: Filename: f.png
p.save("f.png", dpi=300, width=6, height=6, verbose=False) # silent  <-- ALWAYS DO THIS
```

Verified: with `verbose=True` both lines land on **stderr** (as `PlotnineWarning`); with
`verbose=False` stdout and stderr are empty. The message is harmless but reads like an error in
logs. **Every `save()` in a workflow uses `verbose=False`.**

---

## 2. DPI and dual export, verified

```python
p.save("figures/fig.png", dpi=300, width=6, height=6, verbose=False)
p.save("figures/fig.svg",          width=6, height=6, verbose=False)
```

Reading the PNG back reports `dpi = (299.9994, 299.9994)` — the float wobble is identical to
matplotlib and normal. SVG is vector and carries no DPI (~19 KB for a simple boxplot). Save
**both** every figure: PNG to look at, SVG to edit. Final pixel size = `width×dpi` by `height×dpi`.

---

## 3. `geom_smooth`: which `method` gives a confidence band

| `method` | curve | CI band | backend | note |
|---|---|---|---|---|
| `"lm"` | straight line | **yes** | statsmodels | the honest default for a linear trend |
| `"loess"` | smooth curve | **yes** | scikit-misc | non-linear; needs `scikit-misc` installed |
| `"lowess"` | smooth curve | **NO** | statsmodels | warns: *"Confidence intervals are not yet implemented for lowess smoothings"* |

```python
+ geom_smooth(method="lm", se=True, color="#0173b2", fill="#0173b2", alpha=0.2)   # line + band
+ geom_smooth(method="loess", se=True)                                            # curve + band
+ geom_smooth(method="lowess")                                                    # curve, NO band (+warning)
```

If you want a shaded CI, use `lm` or `loess`. Reach for `lowess` only when a band is not wanted;
if you keep it, pass `se=False` to silence the warning.

---

## 4. Discrete axis positions are 1-BASED

The first category sits at `x=1`, the second at `x=2`, … — **not** 0-based like matplotlib.
Verified by annotating `annotate("text", x=1, …)` / `x=2` and seeing the marks land on the first
and second boxes. Consequences:

- A significance bracket for a two-group test spans `x=1..2`.
- Control category order (hence positions) with an **ordered** `pd.Categorical` or
  `scale_x_discrete(limits=[...])`:
  ```python
  df["condition"] = pd.Categorical(df["condition"], categories=["control","treated"], ordered=True)
  pos = {g: i + 1 for i, g in enumerate(["control", "treated"])}   # 1-based lookup
  ```

---

## 5. Significance bracket (there is no built-in)

Build it from three `annotate("segment", …)` plus one `annotate("text", …)`, at 1-based x
positions, and make headroom with `expand_limits` so it is not clipped:

```python
def sig_bracket(x1, x2, y, h, text, size=12):
    """Return plotnine layers for a bracket from x1..x2 at height y (bar height h) labelled text."""
    return [
        annotate("segment", x=x1, xend=x1, y=y - h, yend=y),   # left tick down
        annotate("segment", x=x1, xend=x2, y=y,     yend=y),   # top bar
        annotate("segment", x=x2, xend=x2, y=y,     yend=y - h),# right tick down
        annotate("text",    x=(x1 + x2) / 2, y=y + h, label=text, size=size, va="bottom"),
    ]

top  = df["v"].max(); span = df["v"].max() - df["v"].min()
p = ggplot(df, aes("g", "v")) + geom_boxplot()
for layer in sig_bracket(1, 2, top + 0.05 * span, 0.03 * span, "***"):
    p = p + layer
p = p + expand_limits(y=top + 0.20 * span)   # or coord_cartesian(ylim=…) — without it the bracket clips
```

Notation, from the p-value the STATISTICS stage already wrote:

| p | symbol |
|---|---|
| < 0.001 | `***` |
| < 0.01 | `**` |
| < 0.05 | `*` |
| ≥ 0.05 | `ns` |

---

## 6. Colourblind colour — no built-in palette, use manual hex or a cmap

plotnine ships **no `colorblind` palette**. Two verified routes:

```python
CB = ["#0173b2", "#de8f05", "#029e73", "#d55e00", "#cc78bc"]   # blue orange green vermilion purple
+ scale_fill_manual(values=CB)          # discrete fills (boxes/bars)
+ scale_color_manual(values=CB)         # discrete colours (points/lines)

+ scale_fill_cmap(cmap_name="viridis")  # CONTINUOUS fill (heatmaps) — verified with geom_tile
+ scale_color_brewer(type="qual", palette="Set2")   # a ColorBrewer qualitative alternative
```

Never a red/green pair. For grayscale safety add a second channel:
`scale_shape_manual(values=["o","s","^"])`, `scale_linetype_manual(values=["-","--",":"])`.

---

## 7. Raw-point overlays never drop points

`geom_jitter` (stripplot) and `geom_sina` (beeswarm) place **every** point — verified: 1000
points jittered produced **no** warning and no dropped data. This is a real advantage over
`seaborn.swarmplot`, which silently omits points that do not fit. Overlay freely:

```python
+ geom_boxplot(outlier_alpha=0, width=0.6)          # hide fliers; the jitter shows them
+ geom_jitter(width=0.2, height=0, alpha=0.5, size=1.2, color="#333333")
```

`height=0` jitters x only, so a point's y (its real value) is never moved.

---

## 8. Mean ± CI without precomputing — `stat_summary`

```python
+ stat_summary(fun_data="mean_cl_boot", geom="pointrange")   # bootstrap 95% CI, verified OK
+ stat_summary(fun_y="mean", geom="col")                     # bar of means
```

`stat_summary` computes the summary at draw time — fine for a *visual* mean; the *reported*
statistic still comes from `Statistics_Results.csv`.

---

## 9. Faceting — one plot, many panels

```python
+ facet_wrap("condition")                       # one panel per level, auto-wrapped
+ facet_wrap("feature", ncol=3, scales="free")  # each panel its own x/y range
+ facet_grid("genotype ~ dose")                 # rows × columns
```

Verified `facet_wrap` renders without warnings. Faceting replaces seaborn's `FacetGrid`/loops.

---

## 10. Themes render warning-free; sizing is inches × dpi

A full publication theme rendered with **no warnings** on this stack:

```python
+ theme_matplotlib()
+ theme(figure_size=(6, 6), axis_title=element_text(size=14),
        axis_text=element_text(size=12), plot_title=element_text(size=16),
        legend_text=element_text(size=12))
```

`figure_size` is in **inches**; the saved raster is `figure_size × dpi` pixels. Prefer setting
`figure_size` in the theme and only `dpi` at `save()`.

---

## 11. Verification for a plotnine plotting script

RAISE only on what is always true for a correct run:
- the PNG and the SVG exist and are non-empty
- the columns you read from `Statistics_Results.csv` exist
- the number of plotted groups equals the number of groups in the CSV
- any p-value you read is in [0, 1]

WARN, never raise: "no significant result" (annotate `ns` and move on); NaNs in a column you are
not drawing; small n. **Never recompute a statistic in the plotting script** — read `p_value`
and `significance` from the CSV the statistics stage wrote.

---

## Files

| File | What it covers |
|---|---|
| `SKILL.md` | The mandatory publication standards + the four plotnine traps |
| `PLOTNINE_CHEATSHEET.md` | The grammar, seaborn→plotnine translation, geom/scale/facet/theme catalogue |
| `PLOTNINE_RECIPES.md` | This file — verified 0.15.7 behaviour & gotchas |
| `WORKFLOW_BOXPLOT_SIGNIFICANCE.py` | boxplot + `geom_jitter` + significance bracket (1-based) from the CSV |
| `WORKFLOW_CORRELATION_PLOT.py` | scatter + `geom_smooth` annotated with r,p read from the CSV |
| `WORKFLOW_FACETED_DISTRIBUTIONS.py` | faceted small-multiple distributions (`facet_wrap`) |
