import numpy as np
from pathlib import Path
import warnings
from typing import Dict, Any, Optional, Tuple, Union
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import imagej

import tifffile
import pydicom
from readlif.reader import LifFile

try:
    from aicsimageio import AICSImage
except ImportError:
    AICSImage = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Numpy dtype -> bytes-per-element lookup used for size estimation.
_DTYPE_BYTES: Dict[str, int] = {
    'uint8': 1, 'int8': 1,
    'uint16': 2, 'int16': 2, 'float16': 2,
    'uint32': 4, 'int32': 4, 'float32': 4,
    'uint64': 8, 'int64': 8, 'float64': 8,
}


def _estimate_dataset_bytes(dataset) -> int:
    """
    Estimate the in-memory footprint of an ImageJ2 Dataset in bytes.
    Returns 0 if the estimate cannot be determined.
    """
    try:
        n_pixels = 1
        for i in range(dataset.numDimensions()):
            n_pixels *= int(dataset.dimension(i))

        # Try to infer bytes-per-pixel from the type label
        try:
            type_name = str(dataset.getType().getClass().getSimpleName()).lower()
        except Exception:
            type_name = ''

        bpp = 2  # default: assume 16-bit
        for key, val in _DTYPE_BYTES.items():
            if key in type_name:
                bpp = val
                break

        return n_pixels * bpp
    except Exception:
        return 0


def _tiff_estimated_bytes(file_path: str) -> int:
    """
    Return the estimated uncompressed byte size of a TIFF stack without
    reading pixel data.  Returns 0 on failure.
    """
    try:
        with tifffile.TiffFile(file_path) as tif:
            page = tif.pages[0]
            n_pages = len(tif.pages)
            h, w = page.shape[:2]
            bpp = np.dtype(page.dtype).itemsize
            samples = page.shape[2] if len(page.shape) == 3 else 1
            return h * w * samples * bpp * n_pages
    except Exception:
        return 0


class ImageMetadataAnalyzer:
    """
    Analyze metadata and intensity statistics for PyImageJ datasets.
    Compatible with images loaded in ImageJ/Fiji via PyImageJ.

    Large-dataset safety
    --------------------
    When the estimated uncompressed size of the dataset exceeds
    ``large_dataset_threshold_bytes`` (default 2 GB), full numpy array
    conversions are replaced with slice-sampled approximations so that
    ImageJ is not pushed out of memory.  The ``_is_large_dataset`` flag is
    set to ``True`` in that case and a warning is emitted.
    """

    # Datasets larger than this (bytes) trigger sampled statistics.
    LARGE_DATASET_THRESHOLD_BYTES: int = 2 * 1024 ** 3  # 2 GB

    def __init__(self, ij, dataset=None,
                 large_dataset_threshold_bytes: int = None):
        """
        Args:
            ij: PyImageJ instance
            dataset: ImageJ Dataset object (if None, uses active dataset)
            large_dataset_threshold_bytes: Override the 2 GB threshold above
                which full-array numpy conversions are avoided.
        """
        self.ij = ij
        self.dataset = dataset if dataset is not None else ij.py.active_dataset()

        if self.dataset is None:
            raise ValueError("No dataset provided and no active image in ImageJ GUI")

        if large_dataset_threshold_bytes is not None:
            self.LARGE_DATASET_THRESHOLD_BYTES = large_dataset_threshold_bytes

        self.metadata = {}
        self.calibration = {}
        self.intensity_stats = {}
        self.structure = {}
        self.dicom_metadata = {}
        self._lif_dims = None
        self._is_large_dataset: bool = False  # set during analyze()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, compute_histogram: bool = True, n_bins: int = 256,
                compute_percentiles: bool = True) -> Dict[str, Any]:
        """
        Main analysis function that extracts all metadata and statistics.

        For datasets larger than ``LARGE_DATASET_THRESHOLD_BYTES``:
        - Percentiles and histograms are approximated from a random sample
          of slices instead of the full array.
        - A ``'large_dataset'`` key is added to the returned dict.

        Args:
            compute_histogram: Whether to compute intensity histogram
            n_bins: Number of bins for histogram
            compute_percentiles: Whether to compute percentile statistics

        Returns:
            Dictionary containing all metadata and statistics
        """
        self._extract_metadata()
        self._extract_calibration()

        # ------------------------------------------------------------------
        # Size check — must happen AFTER _extract_metadata so structure is set
        # ------------------------------------------------------------------
        estimated_bytes = _estimate_dataset_bytes(self.dataset)
        if estimated_bytes > self.LARGE_DATASET_THRESHOLD_BYTES:
            self._is_large_dataset = True
            gb = estimated_bytes / 1024 ** 3
            warnings.warn(
                f"Dataset '{self.metadata.get('name')}' is estimated at "
                f"{gb:.1f} GB (>{self.LARGE_DATASET_THRESHOLD_BYTES / 1024 ** 3:.0f} GB "
                f"threshold).  Full numpy array conversion will be skipped; "
                f"statistics will be approximated from sampled slices.",
                ResourceWarning,
                stacklevel=2,
            )

        self._compute_statistics_via_ops(compute_percentiles)

        if compute_histogram:
            self._compute_histogram(n_bins)

        return self._compile_results()

    # ------------------------------------------------------------------
    # Metadata / calibration extraction  (unchanged from original)
    # ------------------------------------------------------------------

    def _extract_metadata(self):
        """Extract basic metadata from dataset."""
        self.metadata['name'] = str(self.dataset.getName())
        self.metadata['source'] = (
            str(self.dataset.getSource())
            if hasattr(self.dataset, 'getSource') else None
        )

        try:
            self.metadata['pixel_type'] = str(
                self.dataset.getType().getClass().getSimpleName()
            )
        except Exception:
            self.metadata['pixel_type'] = 'unknown'

        for i in range(self.dataset.numDimensions()):
            axis = self.dataset.axis(i)
            label = str(axis.type().getLabel())
            size = int(self.dataset.dimension(i))
            self.structure[label] = size

        self.metadata['structure'] = self.structure
        self.metadata['n_dimensions'] = self.dataset.numDimensions()
        self.metadata['is_3d'] = 'Z' in self.structure
        self.metadata['is_time_series'] = 'Time' in self.structure
        self.metadata['is_multichannel'] = 'Channel' in self.structure

    def _extract_calibration(self):
        """Extract spatial calibration using ImageJ and format-specific fallbacks."""
        scales = {}

        for i in range(self.dataset.numDimensions()):
            axis = self.dataset.axis(i)
            label = str(axis.type().getLabel())
            if label in ['X', 'Y', 'Z']:
                scale = float(axis.averageScale(0, 1))
                unit = axis.unit()
                scales[label] = {'scale': scale, 'unit': str(unit) if unit else None}

        src_path = self.metadata.get('source')
        if src_path and Path(src_path).exists():
            p = Path(src_path)
            suffix = p.suffix.lower()
            name_lower = p.name.lower()
            is_ome = '.ome.' in name_lower
            try:
                if suffix in ['.tif', '.tiff'] and not is_ome:
                    with tifffile.TiffFile(src_path) as tif:
                        tags = tif.pages[0].tags
                        x_res_tag = tags.get('XResolution')
                        y_res_tag = tags.get('YResolution')
                        res_unit_tag = tags.get('ResolutionUnit')
                        if x_res_tag and y_res_tag:
                            x_num, x_den = x_res_tag.value
                            y_num, y_den = y_res_tag.value
                            x_ppu = x_num / x_den if x_den else 0
                            y_ppu = y_num / y_den if y_den else 0
                            res_unit_value = res_unit_tag.value if res_unit_tag else 1
                            x_scale = 1.0 / x_ppu if x_ppu > 0 else 1.0
                            y_scale = 1.0 / y_ppu if y_ppu > 0 else 1.0
                            if res_unit_value == 2:
                                tiff_unit = 'inch'
                            elif res_unit_value == 3:
                                tiff_unit = 'cm'
                            else:
                                tiff_unit = 'pixel'
                            for ax, sc in [('X', x_scale), ('Y', y_scale)]:
                                scales.setdefault(ax, {'scale': 1.0, 'unit': None})
                                scales[ax]['scale'] = sc
                                if not scales[ax]['unit'] or scales[ax]['unit'] == 'pixel':
                                    scales[ax]['unit'] = tiff_unit

                elif is_ome or suffix in ['.ome.tif', '.ome.tiff']:
                    with tifffile.TiffFile(src_path) as tif:
                        ome_xml = tif.ome_metadata
                        if ome_xml:
                            root = ET.fromstring(ome_xml)
                            ns = {'ome': 'http://www.openmicroscopy.org/Schemas/OME/2016-06'}
                            pixels = root.find('.//ome:Pixels', ns)
                            if pixels is not None and 'PhysicalSizeX' in pixels.attrib:
                                px = float(pixels.attrib['PhysicalSizeX'])
                                py = float(pixels.attrib['PhysicalSizeY'])
                                pz = float(pixels.attrib.get('PhysicalSizeZ', 0))
                                unit = pixels.attrib.get('PhysicalSizeXUnit', 'µm')
                                for ax, val in [('X', px), ('Y', py), ('Z', pz)]:
                                    if val > 0:
                                        scales.setdefault(ax, {'scale': 1.0, 'unit': None})
                                        scales[ax]['scale'] = val
                                        if not scales[ax]['unit'] or scales[ax]['unit'] == 'pixel':
                                            scales[ax]['unit'] = unit

                elif suffix == '.lif':
                    try:
                        lif = LifFile(src_path)
                        img = lif.get_image(0)
                        scale_n = img.info.get("scale_n")
                        if scale_n:
                            for idx, ax in enumerate(['X', 'Y', 'Z']):
                                if idx < len(scale_n) and scale_n[idx] and scale_n[idx] > 0:
                                    scales.setdefault(ax, {'scale': 1.0, 'unit': None})
                                    scales[ax]['scale'] = 1.0 / scale_n[idx]
                                    if not scales[ax]['unit'] or scales[ax]['unit'] == 'pixel':
                                        scales[ax]['unit'] = 'µm'
                        self._lif_dims = img.info.get("dims")
                    except Exception:
                        if AICSImage is not None:
                            img = AICSImage(src_path)
                            phys = img.physical_pixel_sizes
                            for ax in ['X', 'Y', 'Z']:
                                val = getattr(phys, ax, None)
                                if val is not None:
                                    scales.setdefault(ax, {'scale': 1.0, 'unit': None})
                                    scales[ax]['scale'] = val
                                    if not scales[ax]['unit'] or scales[ax]['unit'] == 'pixel':
                                        scales[ax]['unit'] = 'µm'

                elif suffix in ['.dcm', '.dicom']:
                    ds = pydicom.dcmread(src_path)
                    if hasattr(ds, 'PixelSpacing'):
                        for ax, idx in [('X', 1), ('Y', 0)]:
                            scales.setdefault(ax, {'scale': 1.0, 'unit': None})
                            scales[ax]['scale'] = float(ds.PixelSpacing[idx])
                            if not scales[ax]['unit'] or scales[ax]['unit'] == 'pixel':
                                scales[ax]['unit'] = 'mm'
                    if hasattr(ds, 'SliceThickness'):
                        scales.setdefault('Z', {'scale': 1.0, 'unit': None})
                        scales['Z']['scale'] = float(ds.SliceThickness)
                        if not scales['Z']['unit'] or scales['Z']['unit'] == 'pixel':
                            scales['Z']['unit'] = 'mm'
                    self.dicom_metadata = self._extract_dicom_imaging_metadata(src_path)

                elif AICSImage is not None:
                    try:
                        img = AICSImage(src_path)
                        phys = img.physical_pixel_sizes
                        for ax in ['X', 'Y', 'Z']:
                            val = getattr(phys, ax, None)
                            if val is not None:
                                scales.setdefault(ax, {'scale': 1.0, 'unit': None})
                                scales[ax]['scale'] = val
                                if not scales[ax]['unit'] or scales[ax]['unit'] == 'pixel':
                                    scales[ax]['unit'] = 'µm'
                    except Exception:
                        pass

            except Exception as e:
                warnings.warn(f"Could not read physical pixel size from {src_path}: {e}")

        for ax in scales:
            if not scales[ax]['unit']:
                scales[ax]['unit'] = 'pixel'

        self.calibration = scales

    def _extract_dicom_imaging_metadata(self, src_path: str) -> Dict[str, Any]:
        """Extract comprehensive DICOM imaging metadata."""
        ds = pydicom.dcmread(src_path)
        meta: Dict[str, Any] = {}
        if hasattr(ds, 'PixelSpacing'):
            meta['PixelSpacing'] = [float(v) for v in ds.PixelSpacing]
        if hasattr(ds, 'SliceThickness'):
            meta['SliceThickness'] = float(ds.SliceThickness)
        if hasattr(ds, 'SpacingBetweenSlices'):
            meta['SpacingBetweenSlices'] = float(ds.SpacingBetweenSlices)
        if hasattr(ds, 'ImageOrientationPatient'):
            meta['ImageOrientationPatient'] = [float(v) for v in ds.ImageOrientationPatient]
        if hasattr(ds, 'ImagePositionPatient'):
            meta['ImagePositionPatient'] = [float(v) for v in ds.ImagePositionPatient]
        for attr in ['Rows', 'Columns', 'BitsAllocated', 'BitsStored',
                     'PixelRepresentation', 'SamplesPerPixel']:
            if hasattr(ds, attr):
                meta[attr] = int(getattr(ds, attr))
        if hasattr(ds, 'PhotometricInterpretation'):
            meta['PhotometricInterpretation'] = str(ds.PhotometricInterpretation)
        for attr in ['WindowCenter', 'WindowWidth', 'RescaleSlope', 'RescaleIntercept']:
            if hasattr(ds, attr):
                val = getattr(ds, attr)
                if isinstance(val, pydicom.multival.MultiValue):
                    meta[attr] = [float(v) for v in val]
                else:
                    meta[attr] = float(val)
        if hasattr(ds, 'Modality'):
            meta['Modality'] = str(ds.Modality)
        return meta

    # ------------------------------------------------------------------
    # Large-dataset safe numpy conversion
    # ------------------------------------------------------------------

    def _safe_get_numpy_sample(self, max_slices: int = 20) -> Optional[np.ndarray]:
        """
        Return a numpy array for statistics computation.

        * **Small datasets** (below threshold): full conversion via
          ``ij.py.from_java``.
        * **Large datasets**: only ``max_slices`` evenly-spaced Z/T/Channel
          slices are converted and concatenated, keeping memory use bounded.

        Returns None if conversion fails entirely.
        """
        if not self._is_large_dataset:
            try:
                img_array = self.ij.py.from_java(self.dataset)
                return np.asarray(img_array)
            except Exception as e:
                warnings.warn(f"Full dataset conversion failed: {e}")
                return None

        # ---- Large dataset: slice-sampled conversion --------------------
        # Identify a Z or Time axis to iterate over; fall back to Channel.
        slice_axis_label = None
        slice_axis_idx = None
        for priority in ('Z', 'Time', 'Channel'):
            for i in range(self.dataset.numDimensions()):
                label = str(self.dataset.axis(i).type().getLabel())
                if label == priority and int(self.dataset.dimension(i)) > 1:
                    slice_axis_label = label
                    slice_axis_idx = i
                    break
            if slice_axis_label:
                break

        if slice_axis_label is None:
            # 2-D image flagged as large — should be rare; try direct conversion
            try:
                img_array = self.ij.py.from_java(self.dataset)
                return np.asarray(img_array)
            except Exception as e:
                warnings.warn(f"2D large-dataset conversion failed: {e}")
                return None

        n_slices = int(self.dataset.dimension(slice_axis_idx))
        sample_indices = np.linspace(0, n_slices - 1, min(max_slices, n_slices),
                                     dtype=int).tolist()

        sampled_slices: list = []
        for idx in sample_indices:
            try:
                # Use ImageJ Views to get a single hyper-slice
                views = self.ij.py.jc.Views
                interval_start = [0] * self.dataset.numDimensions()
                interval_end = [int(self.dataset.dimension(i)) - 1
                                for i in range(self.dataset.numDimensions())]
                interval_start[slice_axis_idx] = idx
                interval_end[slice_axis_idx] = idx

                java_start = self.ij.py.jc.long_array(interval_start)
                java_end   = self.ij.py.jc.long_array(interval_end)
                interval   = self.ij.py.jc.FinalInterval(java_start, java_end)
                view       = views.interval(self.dataset, interval)

                slice_arr = np.asarray(self.ij.py.from_java(view))
                sampled_slices.append(slice_arr.ravel())
            except Exception as e:
                warnings.warn(
                    f"Could not sample slice {idx} along {slice_axis_label}: {e}"
                )

        if not sampled_slices:
            warnings.warn("Slice sampling failed for all indices; statistics unavailable.")
            return None

        combined = np.concatenate(sampled_slices)
        warnings.warn(
            f"Large dataset: statistics approximated from {len(sampled_slices)} "
            f"sampled {slice_axis_label}-slices (out of {n_slices}).",
            stacklevel=3,
        )
        return combined

    # ------------------------------------------------------------------
    # Statistics / histogram
    # ------------------------------------------------------------------

    def _compute_statistics_via_ops(self, compute_percentiles: bool = True):
        """
        Compute intensity statistics using ImageJ Ops for min/max/mean/std,
        then use a memory-safe numpy sample for percentiles.
        """
        try:
            ops = self.ij.op()
            self.intensity_stats['min']  = float(ops.stats().min(self.dataset).getRealDouble())
            self.intensity_stats['max']  = float(ops.stats().max(self.dataset).getRealDouble())
            self.intensity_stats['mean'] = float(ops.stats().mean(self.dataset).getRealDouble())
            self.intensity_stats['std']  = float(ops.stats().stdDev(self.dataset).getRealDouble())
            self.intensity_stats['dynamic_range'] = (
                self.intensity_stats['max'] - self.intensity_stats['min']
            )
        except Exception as e:
            raise RuntimeError(f"Error computing statistics via ImageJ Ops: {e}")

        if compute_percentiles:
            try:
                data = self._safe_get_numpy_sample()
                if data is not None:
                    flat = data.ravel().astype(np.float64)
                    self.intensity_stats['median'] = float(np.median(flat))
                    self.intensity_stats['q1']     = float(np.percentile(flat, 25))
                    self.intensity_stats['q3']     = float(np.percentile(flat, 75))
                    self.intensity_stats['q95']    = float(np.percentile(flat, 95))
                    self.intensity_stats['q99']    = float(np.percentile(flat, 99))
                    self.intensity_stats['_stats_sampled'] = self._is_large_dataset
                else:
                    self.intensity_stats['median'] = None
            except Exception as e:
                warnings.warn(f"Could not compute percentiles: {e}")
                self.intensity_stats['median'] = None

    def _compute_histogram(self, n_bins: int = 256):
        """Compute intensity histogram using a memory-safe numpy sample."""
        try:
            data = self._safe_get_numpy_sample()
            if data is None:
                warnings.warn("Histogram skipped: could not obtain pixel sample.")
                return
            flat = data.ravel().astype(np.float64)
            hist, bins = np.histogram(flat, bins=n_bins)
            self.intensity_stats['histogram']      = hist.tolist()
            self.intensity_stats['histogram_bins'] = bins.tolist()
        except Exception as e:
            warnings.warn(f"Could not compute histogram: {e}")

    # ------------------------------------------------------------------
    # Result compilation and reporting  (mostly unchanged)
    # ------------------------------------------------------------------

    def _compile_results(self) -> Dict[str, Any]:
        """Compile all results into a single dictionary."""
        result = {
            'filename':        self.metadata['name'],
            'source':          self.metadata.get('source'),
            'structure':       self.structure,
            'metadata':        self.metadata,
            'calibration':     self.calibration,
            'statistics':      self.intensity_stats,
            'is_3d':           self.metadata['is_3d'],
            'is_time_series':  self.metadata['is_time_series'],
            'is_multichannel': self.metadata['is_multichannel'],
            'large_dataset':   self._is_large_dataset,
        }
        if self.dicom_metadata:
            result['dicom_imaging_metadata'] = self.dicom_metadata
        return result

    def get_pixel_size(self, axis: str = 'X') -> Tuple[float, str]:
        info = self.calibration.get(axis, {'scale': 1.0, 'unit': 'pixel'})
        return info['scale'], info['unit']

    def get_voxel_volume(self) -> Tuple[float, str]:
        x = self.calibration.get('X')
        y = self.calibration.get('Y')
        z = self.calibration.get('Z')
        if not (x and y and z):
            return 1.0, "pixel³"
        volume = x['scale'] * y['scale'] * z['scale']
        units = {x['unit'], y['unit'], z['unit']}
        unit = units.pop() if len(units) == 1 else "mixed"
        return volume, f"{unit}³"

    def suggest_threshold_params(self) -> Dict[str, Any]:
        """Suggest parameters for thresholding based on intensity statistics."""
        if not self.intensity_stats:
            return {}
        suggestions: Dict[str, Any] = {}
        suggestions['otsu_like_estimate'] = self.intensity_stats['mean'] + self.intensity_stats['std']
        if 'q3' in self.intensity_stats and self.intensity_stats['q3'] is not None:
            suggestions['threshold_conservative'] = self.intensity_stats['q95']
            suggestions['threshold_moderate']     = self.intensity_stats['q3']
            suggestions['threshold_aggressive']   = self.intensity_stats.get(
                'median', self.intensity_stats['mean']
            )
        suggestions['normalization_range'] = (
            self.intensity_stats['min'], self.intensity_stats['max']
        )
        if 'q99' in self.intensity_stats and self.intensity_stats['q99'] is not None:
            suggestions['robust_normalization_range'] = (
                self.intensity_stats['min'], self.intensity_stats['q99']
            )
        x_info = self.calibration.get('X')
        if x_info and x_info['unit'] != 'pixel':
            x_scale = x_info['scale']
            unit    = x_info['unit']
            suggestions['pixel_size'] = f"{x_scale:.4f} {unit}/pixel"
            suggestions['gaussian_sigma_small']  = {'pixels': max(2, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}
            suggestions['gaussian_sigma_medium'] = {'pixels': max(3, int(1.0 / x_scale)), 'physical': f"~1.0 {unit}"}
            suggestions['gaussian_sigma_large']  = {'pixels': max(5, int(2.0 / x_scale)), 'physical': f"~2.0 {unit}"}
            suggestions['morphology_kernel_small']  = {'pixels': max(3, int(0.3 / x_scale)), 'physical': f"~0.3 {unit}"}
            suggestions['morphology_kernel_medium'] = {'pixels': max(5, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}
        return suggestions

    def suggest_filter_params(self) -> Dict[str, Any]:
        """Suggest filtering parameters based on noise characteristics."""
        if not self.intensity_stats:
            return {}
        suggestions: Dict[str, Any] = {}
        mean = self.intensity_stats['mean']
        std  = self.intensity_stats['std']
        snr  = mean / std if std > 0 else float('inf')
        suggestions['estimated_snr'] = snr
        if snr < 2:
            suggestions['noise_level']        = 'high'
            suggestions['recommended_filter'] = 'median or bilateral'
            suggestions['median_radius']       = 2
        elif snr < 5:
            suggestions['noise_level']        = 'moderate'
            suggestions['recommended_filter'] = 'gaussian'
            suggestions['gaussian_sigma']      = 1.5
        else:
            suggestions['noise_level']        = 'low'
            suggestions['recommended_filter'] = 'mild gaussian or none'
            suggestions['gaussian_sigma']      = 0.5
        return suggestions

    def plot_intensity_distribution(self, figsize: Tuple[int, int] = (12, 4)):
        """Plot intensity distribution and cumulative histogram."""
        if 'histogram' not in self.intensity_stats:
            print("No histogram data available. Run analyze() with compute_histogram=True")
            return
        fig, axes = plt.subplots(1, 2, figsize=figsize)
        hist = np.array(self.intensity_stats['histogram'])
        bins = np.array(self.intensity_stats['histogram_bins'])
        bin_centers = (bins[:-1] + bins[1:]) / 2
        sampled_note = " (sampled)" if self.intensity_stats.get('_stats_sampled') else ""

        axes[0].bar(bin_centers, hist, width=np.diff(bins)[0], edgecolor='black', alpha=0.7)
        axes[0].axvline(self.intensity_stats['mean'], color='r', linestyle='--',
                        label=f"Mean: {self.intensity_stats['mean']:.1f}")
        if self.intensity_stats.get('median') is not None:
            axes[0].axvline(self.intensity_stats['median'], color='g', linestyle='--',
                            label=f"Median: {self.intensity_stats['median']:.1f}")
        axes[0].set_xlabel('Intensity')
        axes[0].set_ylabel('Frequency')
        axes[0].set_title(f'Intensity Distribution — {self.metadata["name"]}{sampled_note}')
        axes[0].legend()
        axes[0].grid(alpha=0.3)

        cumsum = np.cumsum(hist) / np.sum(hist)
        axes[1].plot(bin_centers, cumsum, linewidth=2)
        if self.intensity_stats.get('q95') is not None:
            axes[1].axhline(0.95, color='r', linestyle='--', alpha=0.5, label='95th percentile')
            axes[1].axvline(self.intensity_stats['q95'], color='r', linestyle='--', alpha=0.5)
        axes[1].set_xlabel('Intensity')
        axes[1].set_ylabel('Cumulative Probability')
        axes[1].set_title(f'Cumulative Distribution{sampled_note}')
        axes[1].legend()
        axes[1].grid(alpha=0.3)

        plt.tight_layout()
        plt.show()

    def print_report(self):
        """Print a formatted analysis report."""
        print("=" * 70)
        print(f"IMAGE ANALYSIS REPORT: {self.metadata['name']}")
        if self._is_large_dataset:
            print("  *** LARGE DATASET — statistics approximated from sampled slices ***")
        print("=" * 70)

        print("\nSTRUCTURE:")
        print("-" * 70)
        for axis, size in self.structure.items():
            print(f"  {axis}: {size}")
        print(f"  Type: {self.metadata['pixel_type']}")
        print(f"  3D: {self.metadata['is_3d']}")
        print(f"  Time series: {self.metadata['is_time_series']}")
        print(f"  Multi-channel: {self.metadata['is_multichannel']}")

        print("\nCALIBRATION / PIXEL SCALE:")
        print("-" * 70)
        for axis in ['X', 'Y', 'Z']:
            if axis in self.calibration:
                info = self.calibration[axis]
                print(f"  {axis}: {info['scale']:.6f} {info['unit']}/pixel")
        if self.metadata['is_3d'] and 'Z' in self.calibration:
            volume, vol_unit = self.get_voxel_volume()
            print(f"  Voxel Volume: {volume:.6f} {vol_unit}")

        if self.intensity_stats:
            sampled_note = " (approximated from sampled slices)" if self.intensity_stats.get('_stats_sampled') else ""
            print(f"\nINTENSITY STATISTICS{sampled_note.upper()}:")
            print("-" * 70)
            print(f"  Range: [{self.intensity_stats['min']:.2f}, {self.intensity_stats['max']:.2f}]")
            print(f"  Mean: {self.intensity_stats['mean']:.2f}")
            if self.intensity_stats.get('median') is not None:
                print(f"  Median: {self.intensity_stats['median']:.2f}")
            print(f"  Std Dev: {self.intensity_stats['std']:.2f}")
            if self.intensity_stats.get('q1') is not None:
                print(f"  Q1 (25%): {self.intensity_stats['q1']:.2f}")
                print(f"  Q3 (75%): {self.intensity_stats['q3']:.2f}")
                print(f"  Q95 (95%): {self.intensity_stats['q95']:.2f}")
            print(f"  Dynamic Range: {self.intensity_stats['dynamic_range']:.2f}")

            print("\nSUGGESTED THRESHOLDING PARAMETERS:")
            print("-" * 70)
            for key, value in self.suggest_threshold_params().items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for k, v in value.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  {key}: {value}")

            print("\nSUGGESTED FILTERING PARAMETERS:")
            print("-" * 70)
            for key, value in self.suggest_filter_params().items():
                print(f"  {key}: {value}")

        print("=" * 70)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def quick_analyze(ij, dataset=None, show_plot: bool = True,
                  large_dataset_threshold_bytes: int = None):
    """
    Quick analysis with default settings.

    Args:
        ij: PyImageJ instance
        dataset: Optional dataset (uses active if None)
        show_plot: Whether to display histogram plots
        large_dataset_threshold_bytes: Override the 2 GB large-dataset threshold.

    Returns:
        ImageMetadataAnalyzer instance
    """
    analyzer = ImageMetadataAnalyzer(ij, dataset,
                                     large_dataset_threshold_bytes=large_dataset_threshold_bytes)
    analyzer.analyze(compute_histogram=True, compute_percentiles=True)
    analyzer.print_report()
    if show_plot:
        analyzer.plot_intensity_distribution()
    return analyzer


def check_tiff_size(file_path: str,
                    threshold_bytes: int = 2 * 1024 ** 3) -> Dict[str, Any]:
    """
    Inspect a TIFF file and report whether it exceeds the memory threshold
    **without loading any pixel data**.  Useful as a pre-flight check before
    opening an image in ImageJ.

    Returns a dict with keys:
        file_path, n_pages, height, width, dtype, estimated_bytes,
        estimated_gb, exceeds_threshold, threshold_bytes
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(file_path)

    with tifffile.TiffFile(file_path) as tif:
        page = tif.pages[0]
        n_pages = len(tif.pages)
        h, w = page.shape[:2]
        bpp = np.dtype(page.dtype).itemsize
        samples = page.shape[2] if len(page.shape) == 3 else 1
        estimated = h * w * samples * bpp * n_pages

    return {
        'file_path':          str(p),
        'n_pages':            n_pages,
        'height':             h,
        'width':              w,
        'dtype':              str(page.dtype),
        'estimated_bytes':    estimated,
        'estimated_gb':       round(estimated / 1024 ** 3, 2),
        'exceeds_threshold':  estimated > threshold_bytes,
        'threshold_bytes':    threshold_bytes,
    }


def _compute_standalone_stats(file_path: str, suffix: str, is_ome: bool) -> Dict[str, Any]:
    """
    Read pixel data directly (no ImageJ instance) and compute intensity
    statistics.  For large TIFFs the file is opened as a memory-map so that
    only the pages needed for sampling are actually read into RAM.
    """
    LARGE_TIFF_THRESHOLD = 2 * 1024 ** 3  # 2 GB
    try:
        data: Optional[np.ndarray] = None

        if suffix in ['.tif', '.tiff']:
            estimated = _tiff_estimated_bytes(file_path)
            if estimated > LARGE_TIFF_THRESHOLD:
                # Memory-map: open without reading all pages
                with tifffile.TiffFile(file_path) as tif:
                    n_pages = len(tif.pages)
                    sample_idx = np.linspace(0, n_pages - 1, min(20, n_pages), dtype=int)
                    slices = [tif.pages[i].asarray() for i in sample_idx]
                data = np.stack(slices)
                warnings.warn(
                    f"Large TIFF ({estimated / 1024 ** 3:.1f} GB): standalone stats "
                    f"approximated from {len(slices)} sampled pages."
                )
            else:
                data = tifffile.imread(file_path)

        elif suffix == '.lif':
            lif = LifFile(file_path)
            img = lif.get_image(0)
            frames = []
            for c in range(img.channels):
                try:
                    frame = img.get_frame(z=0, t=0, c=c)
                    frames.append(np.array(frame))
                except Exception:
                    pass
            if frames:
                data = np.stack(frames)

        elif suffix in ['.dcm', '.dicom']:
            ds = pydicom.dcmread(file_path)
            if hasattr(ds, 'pixel_array'):
                data = ds.pixel_array

        if data is None:
            return {}

        flat = data.astype(np.float64).ravel()
        return {
            'min':           float(np.min(flat)),
            'max':           float(np.max(flat)),
            'mean':          float(np.mean(flat)),
            'std':           float(np.std(flat)),
            'median':        float(np.median(flat)),
            'q1':            float(np.percentile(flat, 25)),
            'q3':            float(np.percentile(flat, 75)),
            'q95':           float(np.percentile(flat, 95)),
            'q99':           float(np.percentile(flat, 99)),
            'dynamic_range': float(np.max(flat) - np.min(flat)),
        }
    except Exception as e:
        warnings.warn(f"Could not compute standalone pixel statistics for {file_path}: {e}")
        return {}


def _suggest_threshold_from_stats(stats: Dict[str, Any],
                                   calibration: Dict[str, Any]) -> Dict[str, Any]:
    if not stats:
        return {}
    suggestions: Dict[str, Any] = {}
    suggestions['otsu_like_estimate']          = stats['mean'] + stats['std']
    suggestions['threshold_conservative']      = stats['q95']
    suggestions['threshold_moderate']          = stats['q3']
    suggestions['threshold_aggressive']        = stats['median']
    suggestions['normalization_range']         = [stats['min'], stats['max']]
    suggestions['robust_normalization_range']  = [stats['min'], stats['q99']]
    x_info = calibration.get('X')
    if x_info and x_info.get('unit') not in (None, 'pixel'):
        x_scale = x_info['scale']
        unit    = x_info['unit']
        suggestions['pixel_size'] = f"{x_scale:.4f} {unit}/pixel"
        suggestions['gaussian_sigma_small']       = {'pixels': max(2, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}
        suggestions['gaussian_sigma_medium']      = {'pixels': max(3, int(1.0 / x_scale)), 'physical': f"~1.0 {unit}"}
        suggestions['gaussian_sigma_large']       = {'pixels': max(5, int(2.0 / x_scale)), 'physical': f"~2.0 {unit}"}
        suggestions['morphology_kernel_small']    = {'pixels': max(3, int(0.3 / x_scale)), 'physical': f"~0.3 {unit}"}
        suggestions['morphology_kernel_medium']   = {'pixels': max(5, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}
    return suggestions


def _suggest_filter_from_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    if not stats:
        return {}
    suggestions: Dict[str, Any] = {}
    mean = stats['mean']
    std  = stats['std']
    snr  = mean / std if std > 0 else float('inf')
    suggestions['estimated_snr'] = snr
    if snr < 2:
        suggestions['noise_level']        = 'high'
        suggestions['recommended_filter'] = 'median or bilateral'
        suggestions['median_radius']       = 2
    elif snr < 5:
        suggestions['noise_level']        = 'moderate'
        suggestions['recommended_filter'] = 'gaussian'
        suggestions['gaussian_sigma']      = 1.5
    else:
        suggestions['noise_level']        = 'low'
        suggestions['recommended_filter'] = 'mild gaussian or none'
        suggestions['gaussian_sigma']      = 0.5
    return suggestions


def extract_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract format-specific metadata from a file without requiring an ImageJ
    instance or open dataset.  Returns a JSON-serializable dict with:
      - file_path, file_format
      - calibration (pixel scale / unit per axis)
      - dimensions (image dimensions)
      - dicom_imaging (only for DICOM files)
      - intensity_statistics, threshold_suggestions, filter_suggestions
      - large_file  (bool — True when estimated size exceeds 2 GB)
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix     = p.suffix.lower()
    name_lower = p.name.lower()
    is_ome     = '.ome.' in name_lower

    result: Dict[str, Any] = {
        'file_path':   str(p),
        'file_format': suffix.lstrip('.'),
        'calibration': {},
        'dimensions':  {},
        'large_file':  False,
    }

    scales = result['calibration']
    dims   = result['dimensions']

    # Pre-flight size check for TIFFs
    if suffix in ['.tif', '.tiff']:
        estimated = _tiff_estimated_bytes(file_path)
        if estimated > 2 * 1024 ** 3:
            result['large_file']       = True
            result['estimated_bytes']  = estimated
            result['estimated_gb']     = round(estimated / 1024 ** 3, 2)

    try:
        if suffix in ['.tif', '.tiff'] and not is_ome:
            with tifffile.TiffFile(file_path) as tif:
                tags        = tif.pages[0].tags
                x_res_tag   = tags.get('XResolution')
                y_res_tag   = tags.get('YResolution')
                res_unit_tag = tags.get('ResolutionUnit')
                if x_res_tag and y_res_tag:
                    x_num, x_den = x_res_tag.value
                    y_num, y_den = y_res_tag.value
                    x_ppu = x_num / x_den if x_den else 0
                    y_ppu = y_num / y_den if y_den else 0
                    rv    = res_unit_tag.value if res_unit_tag else 1
                    x_scale = 1.0 / x_ppu if x_ppu > 0 else 1.0
                    y_scale = 1.0 / y_ppu if y_ppu > 0 else 1.0
                    tiff_unit = {2: 'inch', 3: 'cm'}.get(rv, 'pixel')
                    scales['X'] = {'scale': x_scale, 'unit': tiff_unit}
                    scales['Y'] = {'scale': y_scale, 'unit': tiff_unit}
                shape       = tif.pages[0].shape
                dims['height'] = shape[0]
                dims['width']  = shape[1] if len(shape) > 1 else 1
                dims['pages']  = len(tif.pages)

        elif is_ome or suffix in ['.ome.tif', '.ome.tiff']:
            with tifffile.TiffFile(file_path) as tif:
                ome_xml = tif.ome_metadata
                if ome_xml:
                    root    = ET.fromstring(ome_xml)
                    ns      = {'ome': 'http://www.openmicroscopy.org/Schemas/OME/2016-06'}
                    pixels  = root.find('.//ome:Pixels', ns)
                    if pixels is not None:
                        for attr in ['SizeX', 'SizeY', 'SizeZ', 'SizeC', 'SizeT']:
                            val = pixels.attrib.get(attr)
                            if val:
                                dims[attr] = int(val)
                        if 'PhysicalSizeX' in pixels.attrib:
                            px   = float(pixels.attrib['PhysicalSizeX'])
                            py   = float(pixels.attrib['PhysicalSizeY'])
                            pz   = float(pixels.attrib.get('PhysicalSizeZ', 0))
                            unit = pixels.attrib.get('PhysicalSizeXUnit', 'µm')
                            scales['X'] = {'scale': px, 'unit': unit}
                            scales['Y'] = {'scale': py, 'unit': unit}
                            if pz > 0:
                                scales['Z'] = {'scale': pz, 'unit': unit}

        elif suffix == '.lif':
            try:
                lif     = LifFile(file_path)
                img     = lif.get_image(0)
                scale_n = img.info.get("scale_n")
                if scale_n:
                    for idx, ax in enumerate(['X', 'Y', 'Z']):
                        if idx < len(scale_n) and scale_n[idx] and scale_n[idx] > 0:
                            scales[ax] = {'scale': 1.0 / scale_n[idx], 'unit': 'µm'}
                lif_dims = img.info.get("dims")
                if lif_dims:
                    dims.update({k: v for k, v in zip(['X', 'Y', 'Z', 'T'], lif_dims) if v})
            except Exception:
                if AICSImage is not None:
                    img  = AICSImage(file_path)
                    phys = img.physical_pixel_sizes
                    for ax in ['X', 'Y', 'Z']:
                        val = getattr(phys, ax, None)
                        if val is not None:
                            scales[ax] = {'scale': val, 'unit': 'µm'}

        elif suffix in ['.dcm', '.dicom']:
            ds = pydicom.dcmread(file_path)
            if hasattr(ds, 'PixelSpacing'):
                scales['X'] = {'scale': float(ds.PixelSpacing[1]), 'unit': 'mm'}
                scales['Y'] = {'scale': float(ds.PixelSpacing[0]), 'unit': 'mm'}
            if hasattr(ds, 'SliceThickness'):
                scales['Z'] = {'scale': float(ds.SliceThickness), 'unit': 'mm'}
            if hasattr(ds, 'Rows'):
                dims['height'] = int(ds.Rows)
            if hasattr(ds, 'Columns'):
                dims['width'] = int(ds.Columns)
            dicom_imaging: Dict[str, Any] = {}
            for attr_pair in [
                ('PixelSpacing', lambda v: [float(x) for x in v]),
                ('SliceThickness', float), ('SpacingBetweenSlices', float),
                ('ImageOrientationPatient', lambda v: [float(x) for x in v]),
                ('ImagePositionPatient',    lambda v: [float(x) for x in v]),
            ]:
                attr, fn = attr_pair
                if hasattr(ds, attr):
                    dicom_imaging[attr] = fn(getattr(ds, attr))
            for attr in ['Rows', 'Columns', 'BitsAllocated', 'BitsStored',
                         'PixelRepresentation', 'SamplesPerPixel']:
                if hasattr(ds, attr):
                    dicom_imaging[attr] = int(getattr(ds, attr))
            if hasattr(ds, 'PhotometricInterpretation'):
                dicom_imaging['PhotometricInterpretation'] = str(ds.PhotometricInterpretation)
            for attr in ['WindowCenter', 'WindowWidth', 'RescaleSlope', 'RescaleIntercept']:
                if hasattr(ds, attr):
                    val = getattr(ds, attr)
                    dicom_imaging[attr] = (
                        [float(v) for v in val]
                        if isinstance(val, pydicom.multival.MultiValue)
                        else float(val)
                    )
            if hasattr(ds, 'Modality'):
                dicom_imaging['Modality'] = str(ds.Modality)
            result['dicom_imaging'] = dicom_imaging

    except Exception as e:
        warnings.warn(f"Could not extract metadata from {file_path}: {e}")

    stats = _compute_standalone_stats(file_path, suffix, is_ome)
    if stats:
        result['intensity_statistics']  = stats
        result['threshold_suggestions'] = _suggest_threshold_from_stats(stats, scales)
        result['filter_suggestions']    = _suggest_filter_from_stats(stats)

    return result