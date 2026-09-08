# Plotting — Figure Recipes & Verified Behaviour

Verified against **matplotlib 3.11.0** and **seaborn 0.13.2**, main env. Every claim
below was produced by rendering a figure and inspecting it.

---

## 1. The colorblind palette, verified

`sns.color_palette('colorblind').as_hex()` returns, in order:

```
#0173b2  #de8f05  #029e73  #d55e00  #cc78bc
#ca9161  #fbafe4  #949494  #ece133  #56b4e9
```

So the two-group standard — blue `#0173B2`, orange `#DE8F05` — is exactly the first two
entries. You get them for free from the palette; no need to hardcode.

For heatmaps use `'viridis'`, `'plasma'` or `'cividis'`. Never a red/green pair.

---

## 2. `palette=` without `hue=` is DEPRECATED in seaborn 0.13

The obvious call warns and stops working in seaborn 0.14:

```python
sns.boxplot(data=d, x="g", y="v", palette="colorblind")
# FutureWarning: Passing `palette` without assigning `hue` is deprecated
```

Two clean alternatives, both verified warning-free (for the seaborn deprecation):

```python
# Preferred — set it once, globally
sns.set_palette("colorblind")
sns.boxplot(data=d, x="g", y="v")

# Or be explicit, and suppress the redundant legend
sns.boxplot(data=d, x="g", y="v", hue="g", legend=False, palette="colorblind")
```

(You may still see `vert: bool was deprecated in Matplotlib 3.11` from inside seaborn's
own boxplot call. That is seaborn's bug, not yours, and it is unavoidable today.)

---

## 3. `swarmplot` SILENTLY DROPS POINTS

This is the most dangerous default in the whole plotting stack. If the points do not
fit, seaborn *omits* them and merely warns:

```
UserWarning: 17.4% of the points cannot be placed; you may want to decrease
the size of the markers or use stripplot.
```

A swarmplot is supposed to be the honest "here is every raw data point" overlay. One
that quietly discarded a sixth of the data is a lie.

**Rules:**
- Watch stdout for that warning. If it fires, **fix it** — do not ship the figure.
- Fixes, in order: enlarge the figure, shrink `size=`, or switch to
  `sns.stripplot(..., jitter=0.25, alpha=0.5)`, which never drops points.
- Above a few hundred points per group, prefer `stripplot` or a violin outright.

---

## 3b. `scatter_kws` alias collision in `regplot`

matplotlib's `scatter` treats `linewidth`/`linewidths` and `edgecolor`/`edgecolors` as
aliases, and raises if it receives both:

```
TypeError: Got both 'linewidth' and 'linewidths', which are aliases of one another
```

seaborn passes some of these itself, so inside `scatter_kws` use the **plural** forms:

```python
sns.regplot(..., scatter_kws={"s": 28, "alpha": 0.6,
                              "edgecolors": "white", "linewidths": 0.5})
```

---

## 4. DPI and dual export, verified

```python
plt.savefig("figure.png", dpi=300, bbox_inches="tight")
plt.savefig("figure.svg", bbox_inches="tight")
```
Reading the PNG back reports `dpi = (299.9994, 299.9994)` — the float wobble is normal.
`bbox_inches="tight"` is what prevents clipped axis labels.

SVG carries no DPI (it is vector). Both formats, every figure: PNG to look at, SVG to
edit.

---

## 5. Significance brackets

There is no built-in. The reliable recipe, in data coordinates:

```python
def sig_bracket(ax, x1, x2, y, h, text, lw=1.5, fontsize=12):
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=lw, c="black")
    ax.text((x1 + x2) / 2, y + h, text, ha="center", va="bottom", fontsize=fontsize)

top = df["value"].max()
span = df["value"].max() - df["value"].min()
sig_bracket(ax, 0, 1, top + 0.05 * span, 0.02 * span, "***")
ax.set_ylim(top=top + 0.18 * span)      # make room, or the bracket is clipped
```

Categorical x positions are `0, 1, 2, …` in the order the categories are drawn.
Always extend `ylim` afterwards — `bbox_inches="tight"` will not rescue a bracket that
sits outside the axes.

Notation, from the p-value the STATISTICS stage already computed:

| p | symbol |
|---|---|
| < 0.001 | `***` |
| < 0.01 | `**` |
| < 0.05 | `*` |
| ≥ 0.05 | `ns` |

---

## 6. Font sizes and line widths

```python
plt.rcParams.update({
    "font.size": 12,          # tick labels
    "axes.labelsize": 14,     # axis labels
    "axes.titlesize": 16,     # title
    "legend.fontsize": 12,
    "axes.linewidth": 1.0,
    "lines.linewidth": 2.0,
})
```
Minimums: axis labels 14pt, tick labels 12pt, title 16pt, legend 12pt; plot lines 1.5pt,
axis lines 1.0pt. Setting them in `rcParams` once beats decorating every call.

---

## 7. Grayscale compatibility

Colour alone must never carry the meaning. Add a second channel:

```python
markers = ["o", "s", "^"]
linestyles = ["-", "--", ":"]
```

Check by converting: a figure whose series are distinguishable only by hue fails when
printed.

---

## 8. Plot type by question

| Question | Plot |
|---|---|
| Do two groups differ? | boxplot + `stripplot`/`swarmplot` overlay of raw points |
| …with few points (n<20)? | boxplot is misleading; show all points + mean±SD |
| Are x and y related? | `sns.regplot` (scatter + fit + CI band) |
| Distribution shape | `sns.violinplot` or `sns.histplot(kde=True)` |
| Many features × many objects | `sns.clustermap` with `cmap="viridis"` |
| Counts per category | `sns.barplot` **with** the raw points overlaid, or a dot plot |

A bar chart of means with SEM error bars hides the distribution. If you must draw one,
overlay the points.

---

## 9. Axis labels carry units

`"Cell Area (μm²)"`, never `"Area"`. If PROJECT STATE gives a pixel size, the
measurement stage already converted — use the μm column and say so. If it did not, label
the axis `(px²)` honestly rather than implying microns.

---

## 10. Verification for a plotting script

RAISE only on what is always true for a correct run:
- the PNG and the SVG exist and are non-empty
- the columns you read from `Statistics_Results.csv` exist
- the number of plotted groups equals the number of groups in the CSV

WARN, never raise:
- "no significant result" — annotate `ns` and move on
- NaN values in a column you are not plotting
- a swarmplot overlap warning is the exception: treat it as a **defect to fix**, not a
  warning to log

**Never recompute a statistic in the plotting script.** Read `p_value` and
`significance` from the CSV the statistics stage wrote.

---

## Files

| File | What it covers |
|---|---|
| `SKILL.md` | The mandatory publication standards |
| `FIGURE_RECIPES.md` | This file — verified palette hex, the seaborn 0.13 deprecation, the swarmplot point-dropping trap, bracket recipe, rcParams |
| `WORKFLOW_BOXPLOT_SIGNIFICANCE.py` | `Statistics_Results.csv` + raw data → boxplot with raw points and a significance bracket → PNG (300 dpi) + SVG |
| `WORKFLOW_CORRELATION_PLOT.py` | `Statistics_Results.csv` + raw data → regplot annotated with r and p from the CSV → PNG + SVG |
