# Sholl Analysis UI Workflow

## Workflow A - Direct Image Analysis

1. Open a segmented or thresholdable single-neuron image in Fiji.
2. If needed, threshold the image with `Image > Adjust > Threshold...` and verify that the arbor is foreground.
3. Mark the analysis center with one of the supported startup ROIs:
   - straight line for center plus ending radius
   - point for center only
   - multipoint for center plus primary-branch counts
4. Launch `Analysis > Sholl > Sholl Analysis...`.
5. Set the sampling range, shell type, polynomial fit, normalization, and output options.
6. Run the analysis and inspect the detailed table, summary table, and plots.

## Workflow B - Tracing Analysis

1. Open the Neuroanatomy Shortcut Window from `Plugins > Neuroanatomy > Neuroanatomy Shortcut Window`.
2. Choose `Sholl Analysis (Tracings)...`.
3. Select the tracing file and choose any path filtering that applies.
4. Pick the center definition, such as root nodes or soma-tagged nodes.
5. Configure profile type, sampling range, fitting, normalization, and outputs.
6. Run the analysis and review the exported tables or displayed plots.

## Workflow C - Grouped Profiles

1. Collect multiple saved profile tables with consistent radius and count column names.
2. Open the Neuroanatomy Shortcut Window and choose `Combine Sholl Profiles...`.
3. Point the dialog to the directory containing the profile files.
4. Set the column headers, integration settings, and optional fitting of the averaged profile.
5. Run the merge to obtain aggregated tables and the mean-plus-standard-deviation profile plot.
