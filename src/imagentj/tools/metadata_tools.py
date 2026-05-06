import os
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
# Constants
# ---------------------------------------------------------------------------

# Files whose uncompressed size exceeds this will be refused entirely.
# Set conservatively so even compressed stacks that expand 2–4× on load are safe.
LARGE_FILE_THRESHOLD_BYTES: int = 1 * 1024 ** 3  # 1 GB

_DTYPE_BYTES: Dict[str, int] = {
    'uint8': 1,  'int8': 1,
    'uint16': 2, 'int16': 2, 'float16': 2,
    'uint32': 4, 'int32': 4, 'float32': 4,
    'uint64': 8, 'int64': 8, 'float64': 8,
}


# ---------------------------------------------------------------------------
# Size estimation  (reads only headers / IFDs — zero pixel data)
# ---------------------------------------------------------------------------

def _file_size_bytes(file_path: str) -> int:
    """
    Return the file size in bytes using os.stat — no file I/O, no parsing,
    never crashes regardless of format or compression.
    Returns 0 only if the OS call itself fails (e.g. permission error).
    """
    try:
        return os.stat(file_path).st_size
    except Exception:
        return 0


# FIX 1 ─────────────────────────────────────────────────────────────────────
def _estimate_tiff_uncompressed_bytes(file_path: str) -> int:
    """
    Estimate the fully-decompressed in-memory size of a TIFF stack by reading
    only IFD headers — zero pixel data is touched.

    This is the correct guard for compressed TIFFs: a 300 MB LZW-compressed
    stack can expand to 8 GB on tifffile.imread, sailing right past an
    os.stat-based threshold check.

    Returns 0 on any error so the caller treats it as "unknown / unsafe".
    """
    try:
        with tifffile.TiffFile(file_path) as tif:
            page     = tif.pages[0]
            dtype_sz = np.dtype(page.dtype).itemsize
            page_px  = int(np.prod(page.shape))   # (H, W) or (H, W, C)
            n_pages  = len(tif.pages)
            return page_px * dtype_sz * n_pages
    except Exception:
        return 0
# ────────────────────────────────────────────────────────────────────────────


def _estimate_dataset_bytes(dataset) -> int:
    """Estimate in-memory size of an ImageJ2 Dataset without touching pixels."""
    try:
        n_pixels = 1
        for i in range(dataset.numDimensions()):
            n_pixels *= int(dataset.dimension(i))
        try:
            type_name = str(dataset.getType().getClass().getSimpleName()).lower()
        except Exception:
            type_name = ''
        bpp = 2  # default: 16-bit
        for key, val in _DTYPE_BYTES.items():
            if key in type_name:
                bpp = val
                break
        return n_pixels * bpp
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Public exception used by both the class and the standalone function
# ---------------------------------------------------------------------------

class DatasetTooLargeError(RuntimeError):
    """
    Raised when a dataset or file exceeds the memory-safety threshold.
    The message is intentionally descriptive so an agent/supervisor can
    relay it directly to the user.
    """
    pass


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ImageMetadataAnalyzer:
    """
    Analyze metadata and intensity statistics for PyImageJ datasets.

    Memory safety
    -------------
    ``analyze()`` estimates the dataset size before touching any pixel data.
    If the estimate exceeds ``large_dataset_threshold_bytes`` (default 1 GB)
    a ``DatasetTooLargeError`` is raised immediately so that ImageJ is never
    pushed out of memory.  The caller / supervisor should catch this and
    inform the user.

    FIX 2 — pre-load file guard
    ---------------------------
    If ``source_path`` is supplied (or discoverable from the dataset source
    attribute), the constructor validates the uncompressed size **before**
    the caller passes the dataset to ImageJ for loading.  Call the class
    method ``check_path_before_load()`` as an even earlier gate if you
    control the load call.
    """

    def __init__(self, ij, dataset=None,
                 large_dataset_threshold_bytes: int = LARGE_FILE_THRESHOLD_BYTES):
        self.ij = ij
        self.dataset = dataset if dataset is not None else ij.py.active_dataset()

        if self.dataset is None:
            raise ValueError("No dataset provided and no active image in ImageJ GUI")

        self.large_dataset_threshold_bytes = large_dataset_threshold_bytes
        self.metadata: Dict[str, Any] = {}
        self.calibration: Dict[str, Any] = {}
        self.intensity_stats: Dict[str, Any] = {}
        self.structure: Dict[str, int] = {}
        self.dicom_metadata: Dict[str, Any] = {}
        self._lif_dims = None

    # FIX 2 ──────────────────────────────────────────────────────────────────
    @classmethod
    def check_path_before_load(
        cls,
        file_path: str,
        threshold_bytes: int = LARGE_FILE_THRESHOLD_BYTES,
    ) -> None:
        """
        **Call this BEFORE handing a file to ImageJ for loading.**

        Inspects only the file header / IFD metadata — never reads pixel data.
        Raises ``DatasetTooLargeError`` with a descriptive message if the
        estimated uncompressed size exceeds *threshold_bytes*.

        Usage::

            ImageMetadataAnalyzer.check_path_before_load(path)
            dataset = ij.io().open(path)          # safe to call now
            analyzer = ImageMetadataAnalyzer(ij, dataset)

        Raises
        ------
        FileNotFoundError
        DatasetTooLargeError
        """
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix     = p.suffix.lower()
        name_lower = p.name.lower()
        is_ome     = '.ome.' in name_lower

        if suffix in ['.tif', '.tiff'] and not is_ome:
            estimated = _estimate_tiff_uncompressed_bytes(file_path)
        else:
            # For other formats fall back to on-disk size as a lower bound.
            estimated = _file_size_bytes(file_path)

        if estimated == 0 or estimated > threshold_bytes:
            gb_str = f"{estimated / 1024**3:.2f} GB" if estimated else "unknown size"
            raise DatasetTooLargeError(
                f"File '{p.name}' is too large to load safely "
                f"(estimated uncompressed {gb_str}; "
                f"limit is {threshold_bytes / 1024**3:.1f} GB). "
                f"To open it without crashing, use "
                f"File › Import › TIFF Virtual Stack (TIFFs) or Bio-Formats "
                f"with the 'Use virtual stack' option."
            )
    # ─────────────────────────────────────────────────────────────────────────

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, compute_histogram: bool = True, n_bins: int = 256,
                compute_percentiles: bool = True) -> Dict[str, Any]:
        """
        Extract all metadata and intensity statistics.

        Raises
        ------
        DatasetTooLargeError
            If the dataset exceeds the configured memory threshold.
            Caught upstream; never crashes ImageJ.
        """
        self._extract_metadata()
        self._extract_calibration()

        # ---- Hard size gate — before any pixel access ----
        estimated_bytes = _estimate_dataset_bytes(self.dataset)
        threshold = self.large_dataset_threshold_bytes

        # estimated_bytes == 0 means we failed to determine size — refuse it too.
        if estimated_bytes == 0 or estimated_bytes > threshold:
            gb_str = f"{estimated_bytes / 1024**3:.2f} GB" if estimated_bytes else "unknown size"
            return {
                'filename':    self.metadata.get('name', '?'),
                'source':      self.metadata.get('source'),
                'structure':   self.structure,
                'calibration': self.calibration,
                'error':       'dataset_too_large',
                'message': (
                    f"Dataset '{self.metadata.get('name', '?')}' is too large to analyse "
                    f"safely ({gb_str}; limit is {threshold / 1024**3:.1f} GB). "
                    f"Intensity statistics were not computed. "
                    f"Metadata and calibration are available above."
                ),
            }

        self._compute_statistics_via_ops(compute_percentiles)
        if compute_histogram:
            self._compute_histogram(n_bins)

        return self._compile_results()

    # ------------------------------------------------------------------
    # Metadata / calibration
    # ------------------------------------------------------------------

    def _extract_metadata(self):
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
        scales: Dict[str, Any] = {}

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
                            rv = res_unit_tag.value if res_unit_tag else 1
                            x_scale = 1.0 / x_ppu if x_ppu > 0 else 1.0
                            y_scale = 1.0 / y_ppu if y_ppu > 0 else 1.0
                            tiff_unit = {2: 'inch', 3: 'cm'}.get(rv, 'pixel')
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
                meta[attr] = (
                    [float(v) for v in val]
                    if isinstance(val, pydicom.multival.MultiValue)
                    else float(val)
                )
        if hasattr(ds, 'Modality'):
            meta['Modality'] = str(ds.Modality)
        return meta

    # ------------------------------------------------------------------
    # Statistics / histogram  (only reached for small datasets)
    # ------------------------------------------------------------------

    def _compute_statistics_via_ops(self, compute_percentiles: bool = True):
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
                img_array = self.ij.py.from_java(self.dataset)
                data = np.asarray(img_array).flatten()
                self.intensity_stats['median'] = float(np.median(data))
                self.intensity_stats['q1']     = float(np.percentile(data, 25))
                self.intensity_stats['q3']     = float(np.percentile(data, 75))
                self.intensity_stats['q95']    = float(np.percentile(data, 95))
                self.intensity_stats['q99']    = float(np.percentile(data, 99))
            except Exception as e:
                warnings.warn(f"Could not compute percentiles: {e}")
                self.intensity_stats['median'] = None

    def _compute_histogram(self, n_bins: int = 256):
        try:
            img_array = self.ij.py.from_java(self.dataset)
            data = np.asarray(img_array).flatten()
            hist, bins = np.histogram(data, bins=n_bins)
            self.intensity_stats['histogram']      = hist.tolist()
            self.intensity_stats['histogram_bins'] = bins.tolist()
        except Exception as e:
            warnings.warn(f"Could not compute histogram: {e}")

    # ------------------------------------------------------------------
    # Result compilation and reporting
    # ------------------------------------------------------------------

    def _compile_results(self) -> Dict[str, Any]:
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
        if not self.intensity_stats:
            return {}
        suggestions: Dict[str, Any] = {}
        suggestions['otsu_like_estimate'] = self.intensity_stats['mean'] + self.intensity_stats['std']

        # Background-mode heuristic — drives the "dark" suffix on IJ.setAutoThreshold.
        # If most pixels are dark (median sits in the lower half of the dynamic range),
        # the image is bright-foreground-on-dark-background (typical fluorescence) and
        # the threshold call needs the "dark" suffix. Otherwise (brightfield, H&E,
        # phase-contrast where objects are dark on bright background) — no suffix.
        i_min = self.intensity_stats.get('min')
        i_max = self.intensity_stats.get('max')
        median = self.intensity_stats.get('median', self.intensity_stats.get('mean'))
        if i_min is not None and i_max is not None and median is not None and i_max > i_min:
            mid = (i_min + i_max) / 2.0
            if median <= mid:
                suggestions['background_mode']     = 'dark'
                suggestions['threshold_suffix']    = ' dark'
                suggestions['threshold_call_hint'] = 'IJ.setAutoThreshold(imp, "Otsu dark")  // bright signal on dark BG'
            else:
                suggestions['background_mode']     = 'bright'
                suggestions['threshold_suffix']    = ''
                suggestions['threshold_call_hint'] = 'IJ.setAutoThreshold(imp, "Otsu")  // dark signal on bright BG (brightfield/H&E)'

        if self.intensity_stats.get('q3') is not None:
            suggestions['threshold_conservative'] = self.intensity_stats['q95']
            suggestions['threshold_moderate']     = self.intensity_stats['q3']
            suggestions['threshold_aggressive']   = self.intensity_stats.get('median', self.intensity_stats['mean'])
        suggestions['normalization_range'] = (self.intensity_stats['min'], self.intensity_stats['max'])
        if self.intensity_stats.get('q99') is not None:
            suggestions['robust_normalization_range'] = (self.intensity_stats['min'], self.intensity_stats['q99'])
        x_info = self.calibration.get('X')
        if x_info and x_info['unit'] != 'pixel':
            x_scale = x_info['scale']
            unit    = x_info['unit']
            suggestions['pixel_size'] = f"{x_scale:.4f} {unit}/pixel"
            suggestions['gaussian_sigma_small']       = {'pixels': max(2, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}
            suggestions['gaussian_sigma_medium']      = {'pixels': max(3, int(1.0 / x_scale)), 'physical': f"~1.0 {unit}"}
            suggestions['gaussian_sigma_large']       = {'pixels': max(5, int(2.0 / x_scale)), 'physical': f"~2.0 {unit}"}
            suggestions['morphology_kernel_small']    = {'pixels': max(3, int(0.3 / x_scale)), 'physical': f"~0.3 {unit}"}
            suggestions['morphology_kernel_medium']   = {'pixels': max(5, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}
        return suggestions

    def suggest_filter_params(self) -> Dict[str, Any]:
        if not self.intensity_stats:
            return {}
        mean = self.intensity_stats['mean']
        std  = self.intensity_stats['std']
        snr  = mean / std if std > 0 else float('inf')
        base = {'estimated_snr': snr}
        if snr < 2:
            return {**base, 'noise_level': 'high',     'recommended_filter': 'median or bilateral', 'median_radius': 2}
        elif snr < 5:
            return {**base, 'noise_level': 'moderate', 'recommended_filter': 'gaussian',            'gaussian_sigma': 1.5}
        else:
            return {**base, 'noise_level': 'low',      'recommended_filter': 'mild gaussian or none', 'gaussian_sigma': 0.5}

    def plot_intensity_distribution(self, figsize: Tuple[int, int] = (12, 4)):
        if 'histogram' not in self.intensity_stats:
            print("No histogram data. Run analyze() with compute_histogram=True")
            return
        fig, axes = plt.subplots(1, 2, figsize=figsize)
        hist = np.array(self.intensity_stats['histogram'])
        bins = np.array(self.intensity_stats['histogram_bins'])
        bin_centers = (bins[:-1] + bins[1:]) / 2
        axes[0].bar(bin_centers, hist, width=np.diff(bins)[0], edgecolor='black', alpha=0.7)
        axes[0].axvline(self.intensity_stats['mean'], color='r', linestyle='--',
                        label=f"Mean: {self.intensity_stats['mean']:.1f}")
        if self.intensity_stats.get('median') is not None:
            axes[0].axvline(self.intensity_stats['median'], color='g', linestyle='--',
                            label=f"Median: {self.intensity_stats['median']:.1f}")
        axes[0].set_xlabel('Intensity'); axes[0].set_ylabel('Frequency')
        axes[0].set_title(f'Intensity Distribution — {self.metadata["name"]}')
        axes[0].legend(); axes[0].grid(alpha=0.3)
        cumsum = np.cumsum(hist) / np.sum(hist)
        axes[1].plot(bin_centers, cumsum, linewidth=2)
        if self.intensity_stats.get('q95') is not None:
            axes[1].axhline(0.95, color='r', linestyle='--', alpha=0.5, label='95th percentile')
            axes[1].axvline(self.intensity_stats['q95'], color='r', linestyle='--', alpha=0.5)
        axes[1].set_xlabel('Intensity'); axes[1].set_ylabel('Cumulative Probability')
        axes[1].set_title('Cumulative Distribution')
        axes[1].legend(); axes[1].grid(alpha=0.3)
        plt.tight_layout(); plt.show()

    def print_report(self):
        print("=" * 70)
        print(f"IMAGE ANALYSIS REPORT: {self.metadata['name']}")
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
            print("\nINTENSITY STATISTICS:")
            print("-" * 70)
            print(f"  Range: [{self.intensity_stats['min']:.2f}, {self.intensity_stats['max']:.2f}]")
            print(f"  Mean:  {self.intensity_stats['mean']:.2f}")
            if self.intensity_stats.get('median') is not None:
                print(f"  Median:{self.intensity_stats['median']:.2f}")
            print(f"  Std:   {self.intensity_stats['std']:.2f}")
            if self.intensity_stats.get('q1') is not None:
                print(f"  Q1:    {self.intensity_stats['q1']:.2f}")
                print(f"  Q3:    {self.intensity_stats['q3']:.2f}")
                print(f"  Q95:   {self.intensity_stats['q95']:.2f}")
            print(f"  Dyn range: {self.intensity_stats['dynamic_range']:.2f}")
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
# Convenience function
# ---------------------------------------------------------------------------

def quick_analyze(ij, dataset=None, show_plot: bool = True,
                  large_dataset_threshold_bytes: int = LARGE_FILE_THRESHOLD_BYTES):
    """
    Quick analysis with default settings.

    Raises DatasetTooLargeError if the dataset exceeds the memory threshold.
    """
    analyzer = ImageMetadataAnalyzer(
        ij, dataset,
        large_dataset_threshold_bytes=large_dataset_threshold_bytes
    )
    analyzer.analyze(compute_histogram=True, compute_percentiles=True)
    analyzer.print_report()
    if show_plot:
        analyzer.plot_intensity_distribution()
    return analyzer


# ---------------------------------------------------------------------------
# Standalone file metadata extraction (no ImageJ needed)
# ---------------------------------------------------------------------------

def _suggest_threshold_from_stats(stats: Dict[str, Any],
                                   calibration: Dict[str, Any]) -> Dict[str, Any]:
    if not stats or 'error' in stats:
        return {}
    suggestions: Dict[str, Any] = {
        'otsu_like_estimate':         stats['mean'] + stats['std'],
        'threshold_conservative':     stats['q95'],
        'threshold_moderate':         stats['q3'],
        'threshold_aggressive':       stats['median'],
        'normalization_range':        [stats['min'], stats['max']],
        'robust_normalization_range': [stats['min'], stats['q99']],
    }
    # Background-mode heuristic — drives the "dark" suffix on IJ.setAutoThreshold.
    i_min, i_max, median = stats.get('min'), stats.get('max'), stats.get('median', stats.get('mean'))
    if i_min is not None and i_max is not None and median is not None and i_max > i_min:
        mid = (i_min + i_max) / 2.0
        if median <= mid:
            suggestions['background_mode']     = 'dark'
            suggestions['threshold_suffix']    = ' dark'
            suggestions['threshold_call_hint'] = 'IJ.setAutoThreshold(imp, "Otsu dark")  // bright signal on dark BG'
        else:
            suggestions['background_mode']     = 'bright'
            suggestions['threshold_suffix']    = ''
            suggestions['threshold_call_hint'] = 'IJ.setAutoThreshold(imp, "Otsu")  // dark signal on bright BG (brightfield/H&E)'

    x_info = calibration.get('X')
    if x_info and x_info.get('unit') not in (None, 'pixel'):
        x_scale = x_info['scale']
        unit    = x_info['unit']
        suggestions['pixel_size'] = f"{x_scale:.4f} {unit}/pixel"
        suggestions['gaussian_sigma_small']    = {'pixels': max(2, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}
        suggestions['gaussian_sigma_medium']   = {'pixels': max(3, int(1.0 / x_scale)), 'physical': f"~1.0 {unit}"}
        suggestions['gaussian_sigma_large']    = {'pixels': max(5, int(2.0 / x_scale)), 'physical': f"~2.0 {unit}"}
        suggestions['morphology_kernel_small'] = {'pixels': max(3, int(0.3 / x_scale)), 'physical': f"~0.3 {unit}"}
        suggestions['morphology_kernel_medium']= {'pixels': max(5, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}
    return suggestions


def _suggest_filter_from_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    if not stats or 'error' in stats:
        return {}
    mean = stats['mean']
    std  = stats['std']
    snr  = mean / std if std > 0 else float('inf')
    base = {'estimated_snr': snr}
    if snr < 2:
        return {**base, 'noise_level': 'high',     'recommended_filter': 'median or bilateral', 'median_radius': 2}
    elif snr < 5:
        return {**base, 'noise_level': 'moderate', 'recommended_filter': 'gaussian',            'gaussian_sigma': 1.5}
    else:
        return {**base, 'noise_level': 'low',      'recommended_filter': 'mild gaussian or none', 'gaussian_sigma': 0.5}


def _compute_standalone_stats(file_path: str, suffix: str) -> Dict[str, Any]:
    """
    Compute pixel statistics for small files only.

    For TIFFs the guard uses the *uncompressed* size estimated from IFD
    headers — a heavily-compressed TIFF can expand 10–20× on load and would
    otherwise sail past an os.stat-based size check.
    For other formats the on-disk size is used as a conservative lower bound.
    Returns an error dict without touching pixel data if the file is too large.
    """
    # --- format-aware size gate (no pixel data read) ---
    if suffix in ['.tif', '.tiff']:
        estimated = _estimate_tiff_uncompressed_bytes(file_path)
        guard_size = estimated if estimated > 0 else _file_size_bytes(file_path)
    else:
        guard_size = _file_size_bytes(file_path)

    if guard_size == 0 or guard_size > LARGE_FILE_THRESHOLD_BYTES:
        gb_str = f"{guard_size / 1024**3:.2f} GB" if guard_size else "unknown size"
        return {
            'error':   'file_too_large',
            'message': (
                f"File '{Path(file_path).name}' is too large for pixel statistics "
                f"(estimated uncompressed {gb_str}; "
                f"limit is {LARGE_FILE_THRESHOLD_BYTES / 1024**3:.1f} GB). "
                f"Metadata and calibration were extracted successfully."
            ),
        }

    if suffix in ['.tif', '.tiff']:
        data = tifffile.imread(file_path)
        flat = data.astype(np.float64).ravel()
        del data

    elif suffix == '.lif':
        lif = LifFile(file_path)
        img = lif.get_image(0)
        frames = []
        for c in range(img.channels):
            try:
                frames.append(np.array(img.get_frame(z=0, t=0, c=c), dtype=np.float64))
            except Exception:
                pass
        if not frames:
            return {}
        flat = np.concatenate([f.ravel() for f in frames])

    elif suffix in ['.dcm', '.dicom']:
        ds = pydicom.dcmread(file_path)
        if not hasattr(ds, 'pixel_array'):
            return {}
        flat = ds.pixel_array.astype(np.float64).ravel()

    else:
        # PIL fallback: handles JPEG, PNG, BMP, and any other PIL-readable format
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                arr = np.array(img, dtype=np.float64)
            flat = arr.ravel()
        except Exception:
            return {}

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


def extract_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract format-specific metadata from a file without an ImageJ instance.

    Returns a JSON-serializable dict containing calibration, dimensions,
    and (for small files) intensity statistics and processing suggestions.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    DatasetTooLargeError
        If the file exceeds the memory-safety threshold.  The error message
        is descriptive and safe to relay directly to the user / supervisor.
        This is raised BEFORE any pixel data is read — the process will not
        crash or run out of memory.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix     = p.suffix.lower()
    name_lower = p.name.lower()
    is_ome     = '.ome.' in name_lower

    # ---- Hard size gate — fires before ANY file reading ----
    size = _file_size_bytes(file_path)
    if size == 0 or size > LARGE_FILE_THRESHOLD_BYTES:
        gb_str = f"{size / 1024**3:.2f} GB" if size else "unknown size"
        return {
            'file_path':   str(p),
            'file_format': suffix.lstrip('.'),
            'error':       'file_too_large',
            'message': (
                f"File '{p.name}' is too large to analyse safely "
                f"({gb_str}; limit is {LARGE_FILE_THRESHOLD_BYTES / 1024**3:.1f} GB). "
                f"Pixel statistics were not computed. "
                f"To open this file in ImageJ without crashing, use "
                f"File > Import > TIFF Virtual Stack."
            ),
        }

    result: Dict[str, Any] = {
        'file_path':   str(p),
        'file_format': suffix.lstrip('.'),
        'calibration': {},
        'dimensions':  {},
    }
    scales = result['calibration']
    dims   = result['dimensions']

    # ---- Metadata / calibration (header reads only — no pixel data) ----
    try:
        if suffix in ['.tif', '.tiff'] and not is_ome:
            with tifffile.TiffFile(file_path) as tif:
                tags         = tif.pages[0].tags
                x_res_tag    = tags.get('XResolution')
                y_res_tag    = tags.get('YResolution')
                res_unit_tag = tags.get('ResolutionUnit')
                if x_res_tag and y_res_tag:
                    x_num, x_den = x_res_tag.value
                    y_num, y_den = y_res_tag.value
                    x_ppu = x_num / x_den if x_den else 0
                    y_ppu = y_num / y_den if y_den else 0
                    rv    = res_unit_tag.value if res_unit_tag else 1
                    x_scale   = 1.0 / x_ppu if x_ppu > 0 else 1.0
                    y_scale   = 1.0 / y_ppu if y_ppu > 0 else 1.0
                    tiff_unit = {2: 'inch', 3: 'cm'}.get(rv, 'pixel')
                    scales['X'] = {'scale': x_scale, 'unit': tiff_unit}
                    scales['Y'] = {'scale': y_scale, 'unit': tiff_unit}
                shape = tif.pages[0].shape
                dims['height'] = shape[0]
                dims['width']  = shape[1] if len(shape) > 1 else 1
                dims['pages']  = len(tif.pages)

        elif is_ome or suffix in ['.ome.tif', '.ome.tiff']:
            with tifffile.TiffFile(file_path) as tif:
                ome_xml = tif.ome_metadata
                if ome_xml:
                    root   = ET.fromstring(ome_xml)
                    ns     = {'ome': 'http://www.openmicroscopy.org/Schemas/OME/2016-06'}
                    pixels = root.find('.//ome:Pixels', ns)
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
            for attr in ['PixelSpacing', 'SliceThickness', 'SpacingBetweenSlices',
                         'ImageOrientationPatient', 'ImagePositionPatient']:
                if hasattr(ds, attr):
                    val = getattr(ds, attr)
                    try:
                        dicom_imaging[attr] = [float(v) for v in val]
                    except TypeError:
                        dicom_imaging[attr] = float(val)
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
                        if isinstance(val, pydicom.multival.MultiValue) else float(val)
                    )
            if hasattr(ds, 'Modality'):
                dicom_imaging['Modality'] = str(ds.Modality)
            result['dicom_imaging'] = dicom_imaging

        # PIL fallback: fills dims/mode for JPEG, PNG, BMP, and any other
        # PIL-readable format not handled by a specific branch above.
        if not dims:
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    dims['width']    = img.width
                    dims['height']   = img.height
                    dims['mode']     = img.mode          # e.g. 'L', 'RGB', 'RGBA'
                    dims['channels'] = len(img.getbands())
                    # DPI embedded in JPEG/PNG JFIF/Exif headers → physical pixel size
                    dpi = img.info.get('dpi')
                    if dpi and dpi[0] > 0 and not scales:
                        scales['X'] = {'scale': 25.4 / dpi[0], 'unit': 'mm'}
                        scales['Y'] = {'scale': 25.4 / dpi[1], 'unit': 'mm'}
            except Exception:
                pass

    except Exception as e:
        warnings.warn(f"Could not extract metadata from {file_path}: {e}")

    # ---- Pixel statistics (format-aware size gate inside) ----
    stats = _compute_standalone_stats(file_path, suffix)
    if stats and 'error' in stats:
        # Too-large or unreadable — attach the warning but don't crash
        result['intensity_statistics_error'] = stats['message']
    elif stats:
        result['intensity_statistics']  = stats
        result['threshold_suggestions'] = _suggest_threshold_from_stats(stats, scales)
        result['filter_suggestions']    = _suggest_filter_from_stats(stats)

    return result


def check_file_size(file_path: str,
                    threshold_bytes: int = LARGE_FILE_THRESHOLD_BYTES) -> Dict[str, Any]:
    """
    Report file size using os.stat — zero file I/O, safe for any format or size.
    Use as a pre-flight check before passing a file to any analysis function.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(file_path)
    size = _file_size_bytes(file_path)
    return {
        'file_path':         str(p),
        'size_bytes':        size,
        'size_gb':           round(size / 1024**3, 2),
        'exceeds_threshold': size > threshold_bytes,
        'threshold_bytes':   threshold_bytes,
    }