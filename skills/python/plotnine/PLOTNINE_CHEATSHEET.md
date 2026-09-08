# plotnine Cheatsheet — the grammar, and the seaborn→plotnine map

plotnine 0.15.7. A figure is a **sum of layers** over one tidy (long-format) DataFrame:

```
ggplot(data, aes(...))  +  geom_*(...)  +  scale_*(...)  +  facet_*(...)  +  coord_*(...)  +  theme_*() + theme(...)
   └ data + mapping        └ marks        └ data→pixel    └ small mult.    └ coord space   └ non-data ink
```

You **add layers with `+`**. Parenthesise the whole expression so you can break lines:

```python
from plotnine import *
p = (ggplot(df, aes(x="dose", y="response", color="genotype"))
     + geom_point()
     + geom_smooth(method="lm"))
p.save("figures/f.png", dpi=300, verbose=False)
```

---

## 1. `aes()` — the aesthetic mapping (data → visual channel)

`aes()` maps **column names (strings)** to channels: `x`, `y`, `color` (lines/points/text),
`fill` (areas/bars/boxes/tiles), `shape`, `linetype`, `size`, `alpha`, `group`.

- Put a mapping in `aes()` → it is **driven by data** and gets a legend.
- Put a constant **outside** `aes()`, as a plain kwarg → it is a **fixed** setting, no legend.

```python
geom_point(aes(color="genotype"), size=2)   # colour VARIES by genotype; size FIXED at 2
geom_point(color="#0173b2")                  # colour FIXED; no legend
```

This inside/outside distinction is the single most common plotnine mistake — `color="blue"`
inside `aes()` does *not* make points blue, it creates a one-level legend labelled "blue".

Mappings set in `ggplot(aes(...))` are inherited by every layer; a layer's own `aes()` overrides.

---

## 2. seaborn → plotnine translation

| seaborn | plotnine |
|---|---|
| `sns.scatterplot(data=d, x="a", y="b", hue="g")` | `ggplot(d, aes("a","b",color="g")) + geom_point()` |
| `sns.lineplot(...)` | `+ geom_line()` (or `geom_path()` for unsorted x) |
| `sns.regplot(x,y)` | `+ geom_point() + geom_smooth(method="lm")` |
| `sns.boxplot(x="g", y="v")` | `ggplot(d, aes("g","v")) + geom_boxplot()` |
| `sns.violinplot(...)` | `+ geom_violin()` |
| `sns.stripplot(...)` | `+ geom_jitter(width=0.2)` |
| `sns.swarmplot(...)` | `+ geom_sina()` (beeswarm; **never drops points**) |
| `sns.barplot(estimator=mean)` | `+ stat_summary(fun_y="mean", geom="col")` (or precompute + `geom_col`) |
| `sns.histplot(x)` | `+ geom_histogram(bins=30)` |
| `sns.kdeplot(x)` | `+ geom_density()` |
| `sns.heatmap(matrix)` | long-form df `+ geom_tile(aes(fill="z")) + scale_fill_cmap(cmap_name="viridis")` |
| `sns.FacetGrid(...).map(...)` | `+ facet_wrap("col")` or `facet_grid("row ~ col")` |
| `sns.set_palette("colorblind")` | `+ scale_color_manual(values=CB)` / `scale_fill_manual(values=CB)` |
| `plt.xlabel/ylabel/title` | `+ labs(x=…, y=…, title=…)` |
| `ax.set_ylim(...)` | `+ coord_cartesian(ylim=(lo,hi))` or `+ expand_limits(y=…)` |
| `plt.savefig("f.png", dpi=300)` | `p.save("f.png", dpi=300, verbose=False)` |

**Key mental shift:** seaborn wants **wide** data and does the aggregation for you; plotnine wants
**long/tidy** data (`df.melt(...)`) and you say which column maps to which channel.

---

## 3. Geom catalogue (the ones you will actually use)

| geom | draws | notes |
|---|---|---|
| `geom_point` | scatter | `aes(shape=, size=, color=)` |
| `geom_jitter` | scattered points | stripplot; `width=`, `height=0` to jitter x only |
| `geom_sina` | beeswarm | swarm without dropping points |
| `geom_line` / `geom_path` | connected lines | `line` sorts by x; `path` keeps row order |
| `geom_boxplot` | box + whiskers | `outlier_alpha=0` to hide fliers when overlaying points |
| `geom_violin` | violin | pair with `geom_sina` |
| `geom_bar` / `geom_col` | bars | `bar`=counts (stat_count); `col`=use y as-is |
| `geom_histogram` | histogram | set `bins=` (default 30, warns if unset in some geoms) |
| `geom_density` | KDE | |
| `geom_smooth` | fit + CI band | `method="lm"|"loess"|"lowess"` (see recipe 3) |
| `geom_tile` / `geom_raster` | heatmap cells | `aes(fill=)` + `scale_fill_cmap` |
| `geom_errorbar` / `geom_pointrange` | error bars | pair with `stat_summary` |
| `geom_hline`/`geom_vline`/`geom_abline` | reference lines | `geom_hline(yintercept=0)` |
| `geom_text` / `geom_label` | data labels | annotate uses these under the hood |

Add raw-point overlays as their own layer *after* the summary geom so they draw on top.

---

## 4. Scales — map data to pixels/colour/shape

```python
# colour / fill
+ scale_color_manual(values=["#0173b2", "#de8f05"])     # discrete, explicit hex
+ scale_fill_cmap(cmap_name="viridis")                  # continuous fill (heatmaps)
+ scale_color_cmap_d(cmap_name="viridis")               # discrete sampled from a cmap
+ scale_fill_brewer(type="qual", palette="Set2")        # a ColorBrewer qualitative set
# axes
+ scale_x_log10()   + scale_y_continuous(limits=(0, 100), expand=(0, 0))
+ scale_x_discrete(limits=["control","treated"], labels=["Control","Treated"])
# non-colour channels (grayscale safety)
+ scale_shape_manual(values=["o","s","^"])  + scale_linetype_manual(values=["-","--",":"])
```

The colourblind hex list (first five, blue/orange/green/vermilion/purple):
`["#0173b2", "#de8f05", "#029e73", "#d55e00", "#cc78bc"]`.

---

## 5. Facets — small multiples (plotnine's superpower)

```python
+ facet_wrap("plate")                      # one panel per level of `plate`, wrapped
+ facet_wrap("plate", ncol=3, scales="free_y")
+ facet_grid("genotype ~ dose")            # rows × columns grid
```

`scales="free"|"free_x"|"free_y"` lets each panel have its own range. This is how you turn one
`ggplot(...)` into a grid of comparable panels with zero extra loops.

---

## 6. Themes & sizing

```python
+ theme_matplotlib()          # or theme_bw(), theme_minimal(), theme_classic(), theme_seaborn()
+ theme(
    figure_size=(6, 6),                       # INCHES; combines with dpi at save time
    axis_title=element_text(size=14),
    axis_text=element_text(size=12),
    plot_title=element_text(size=16),
    legend_title=element_text(size=12), legend_text=element_text(size=12),
    legend_position="right",                  # "none" to drop the legend
    panel_grid_minor=element_blank(),
  )
```

`element_text`, `element_line`, `element_rect`, `element_blank` are the building blocks; set an
element to `element_blank()` to remove it. Final image pixels = `figure_size` (in) × `dpi`.

---

## 7. Saving (the one call that bites everyone)

```python
p.save("figures/fig.png", dpi=300, width=6, height=6, verbose=False)  # verbose=False is MANDATORY
p.save("figures/fig.svg",          width=6, height=6, verbose=False)  # SVG carries no dpi (vector)
```

`verbose=True` (the default) prints `PlotnineWarning: Saving 6 x 6 in image.` to **stderr**.
`width`/`height` are inches; if omitted, `theme(figure_size=…)` is used, else a default. `ggsave`
is an alias of `p.save`.

---

## 8. Annotate (fixed marks not tied to a data column)

```python
+ annotate("text", x=1.5, y=1200, label="***", size=12)
+ annotate("segment", x=1, xend=2, y=1180, yend=1180)   # one line; positions are 1-BASED on discrete x
+ annotate("rect", xmin=0.5, xmax=1.5, ymin=0, ymax=100, alpha=0.1)
```

See `PLOTNINE_RECIPES.md` §5 for the full significance-bracket helper.
