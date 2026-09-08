# Coloc 2 Groovy API Guide

### Execution Command
`IJ.run("Coloc 2", "parameter_string")`

> ⚠️ **The macro keys are derived from the dialog's checkbox/field labels — NOT numbered
> `statistic_N` keys.** A wrong/unknown key is *silently ignored* by ImageJ's macro parser,
> and the statistic then falls back to whatever was last saved in `Prefs` (`Coloc_2.useSpearmanRank`
> etc.), which is usually `false`. That is why `statistic_5=true` "never turns Spearman on".
> Verified against `Colocalisation_Analysis-3.1.0.jar` (decompiled dialog) and a live Coloc 2 run.

### Two different syntaxes — this is the part everyone gets wrong
| Field kind | Syntax | Example |
|:---|:---|:---|
| **Choice** (dropdown) | `key=value` | `channel_1=[My Image]`, `threshold_regression=Costes` |
| **Numeric** field | `key=value` | `psf=3`, `costes_randomisations=100` |
| **Checkbox** (every statistic, every display toggle) | **bare key, NO `=true`** | `spearman's_rank_correlation` |

For a checkbox ImageJ matches the bare token delimited by spaces. Writing
`spearman's_rank_correlation=true` does **not** work — the `=true` defeats the match and the
box stays unchecked. Include the bare key to turn it ON; **omit it entirely** to leave it OFF.

### Verified Choice / Numeric parameters (`key=value`)
| Argument | Type | Description |
|:---|:---|:---|
| `channel_1` | String | Title of the first image (use brackets `[]` if the name has spaces). |
| `channel_2` | String | Title of the second image. |
| `roi_or_mask` | String | Title of an ROI/mask image. **Omit the whole argument when none is used.** |
| `threshold_regression` | String | `Costes` (default), `Bisection`, or `None`. (Note: **`Bisection`**, singular.) |
| `psf` | Float | PSF size in pixels for the Costes test. Usually `3`. (This is **`psf`**, not `psf_width`.) |
| `costes_randomisations` | Integer | Iterations for the Costes test, e.g. `100`. (This is **`costes_randomisations`**, not `number_of_iterations`.) |

### Verified Checkbox parameters (include bare key = ON, omit = OFF)
| Bare key | Statistic / toggle |
|:---|:---|
| *(none — always computed)* | **Pearson's R** (PCC). There is no checkbox; it always runs. |
| `manders'_correlation` | Manders' M1/M2 (tM1/tM2). |
| `costes'_significance_test` | Costes' P-value significance test (needs `psf` + `costes_randomisations`). |
| `li_icq` | Li's ICQ. |
| `li_histogram_channel_1` | Li histogram, channel 1. |
| `li_histogram_channel_2` | Li histogram, channel 2. |
| `spearman's_rank_correlation` | **Spearman's rank correlation** (rho + t-statistic + d.f.). |
| `kendall's_tau_rank_correlation` | Kendall's Tau rank correlation. |
| `2d_intensity_histogram` | 2D intensity histogram. |
| `display_images_in_result` | Render the result image panels (scatterplot etc.). **Omit when headless** (was wrongly `display_images`). |
| `display_shuffled_images` | Display shuffled Costes images. |
| `show_save_pdf_dialog` | Pop the "save PDF" dialog — **never include in headless/batch** (it blocks). |

> There is **no** `display_results` checkbox — that key does not exist. Coloc 2 always writes its
> numeric results to a results/log window; capture them from `IJ.getLog()`, the `ResultsTable`,
> or the Coloc 2 `TextWindow`.

### Minimal working example (Spearman + Manders + Costes, headless)
```groovy
String args = [
    'channel_1=[' + ch1.getTitle() + ']',
    'channel_2=[' + ch2.getTitle() + ']',
    'threshold_regression=Costes',
    "spearman's_rank_correlation",      // bare key — turns Spearman ON
    "manders'_correlation",             // bare key
    "costes'_significance_test",        // bare key
    'psf=3',
    'costes_randomisations=100'
    // display_images_in_result / show_save_pdf_dialog intentionally omitted (headless-safe)
].join(' ')
IJ.run('Coloc 2', args)
```
Live output proof: `Spearman's rank correlation value, 0.98384632` + `Spearman's correlation t-statistic, ...`.

### Crucial Syntax Rules
1. **Checkboxes are bare keys** — `spearman's_rank_correlation`, *not* `spearman's_rank_correlation=true`, *not* `statistic_5=true`.
2. **No Spaces around `=`** for choices/numerics: `channel_1=C1` is correct; `channel_1 = C1` fails.
3. **Brackets** around image names with spaces: `channel_1=[Result of C1]`.
4. **Headless Mode:** omit `display_images_in_result` and `show_save_pdf_dialog` on a server / in a loop to prevent UI hangs (a PDF-save dialog will block waiting for a human).
5. **Batch loops leak memory.** Omitting `display_images_in_result` does *not* stop Coloc 2 from
   building its result window — that flag only controls what the window shows. On a non-headless
   JVM the window is created on every run and is only freed when a human clicks its close box, so
   each iteration pins both source images plus all derived images forever. Dispose it yourself
   after each run — see [BATCH_MEMORY.md](./BATCH_MEMORY.md).
