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


class ImageMetadataAnalyzer:
    """
    Analyze metadata and intensity statistics for PyImageJ datasets.
    Compatible with images loaded in ImageJ/Fiji via PyImageJ.
    """
    
    def __init__(self, ij, dataset=None):
        """
        Initialize analyzer with PyImageJ instance and optional dataset.
        
        Args:
            ij: PyImageJ instance
            dataset: ImageJ Dataset object (if None, uses active dataset)
        """
        self.ij = ij
        self.dataset = dataset if dataset is not None else ij.py.active_dataset()
        
        if self.dataset is None:
            raise ValueError("No dataset provided and no active image in ImageJ GUI")
        
        self.metadata = {}
        self.calibration = {}
        self.intensity_stats = {}
        self.structure = {}
        self.dicom_metadata = {}
        self._lif_dims = None

    def analyze(self, compute_histogram: bool = True, n_bins: int = 256, 
                compute_percentiles: bool = True) -> Dict[str, Any]:
        """
        Main analysis function that extracts all metadata and statistics.
        
        Args:
            compute_histogram: Whether to compute intensity histogram
            n_bins: Number of bins for histogram
            compute_percentiles: Whether to compute percentile statistics
            
        Returns:
            Dictionary containing all metadata and statistics
        """
        # Extract metadata and calibration
        self._extract_metadata()
        self._extract_calibration()
        
        # Compute statistics using ImageJ Ops
        self._compute_statistics_via_ops(compute_percentiles)
        
        # Optionally compute histogram
        if compute_histogram:
            self._compute_histogram(n_bins)
        
        return self._compile_results()
    
    def _extract_metadata(self):
        """Extract basic metadata from dataset."""
        self.metadata['name'] = str(self.dataset.getName())
        self.metadata['source'] = str(self.dataset.getSource()) if hasattr(self.dataset, 'getSource') else None
        
        # Get pixel type
        try:
            self.metadata['pixel_type'] = str(self.dataset.getType().getClass().getSimpleName())
        except:
            self.metadata['pixel_type'] = 'unknown'
        
        # Extract dimensional structure
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

        # --- ImageJ2 axis-based
        for i in range(self.dataset.numDimensions()):
            axis = self.dataset.axis(i)
            label = str(axis.type().getLabel())

            if label in ['X', 'Y', 'Z']:
                scale = float(axis.averageScale(0, 1))
                unit = axis.unit()
                scales[label] = {'scale': scale, 'unit': str(unit) if unit else None}

        # --- File-based fallback for DICOM/TIFF/LIF/OME-TIFF
        src_path = self.metadata.get('source')
        if src_path and Path(src_path).exists():
            p = Path(src_path)
            suffix = p.suffix.lower()
            name_lower = p.name.lower()
            is_ome = '.ome.' in name_lower
            try:
                if suffix in ['.tif', '.tiff'] and not is_ome:
                    # --- Standard TIFF: use rational XResolution/YResolution
                    with tifffile.TiffFile(src_path) as tif:
                        tags = tif.pages[0].tags
                        x_res_tag = tags.get('XResolution')
                        y_res_tag = tags.get('YResolution')
                        res_unit_tag = tags.get('ResolutionUnit')

                        if x_res_tag and y_res_tag:
                            # Rational value: (numerator, denominator)
                            x_num, x_den = x_res_tag.value
                            y_num, y_den = y_res_tag.value
                            x_pixels_per_unit = x_num / x_den if x_den else 0
                            y_pixels_per_unit = y_num / y_den if y_den else 0

                            res_unit_value = res_unit_tag.value if res_unit_tag else 1

                            if x_pixels_per_unit > 0:
                                x_scale = 1.0 / x_pixels_per_unit
                            else:
                                x_scale = 1.0
                            if y_pixels_per_unit > 0:
                                y_scale = 1.0 / y_pixels_per_unit
                            else:
                                y_scale = 1.0

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
                    # --- OME-TIFF: parse OME XML for PhysicalSize attributes
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
                    # --- LIF: try readlif first, then AICSImage fallback
                    try:
                        lif = LifFile(src_path)
                        # Use first series for calibration
                        img = lif.get_image(0)
                        scale_n = img.info.get("scale_n")
                        if scale_n:
                            # scale_n contains px-per-micron values; invert to get µm-per-px
                            for idx, ax in enumerate(['X', 'Y', 'Z']):
                                if idx < len(scale_n) and scale_n[idx] and scale_n[idx] > 0:
                                    scales.setdefault(ax, {'scale': 1.0, 'unit': None})
                                    scales[ax]['scale'] = 1.0 / scale_n[idx]
                                    if not scales[ax]['unit'] or scales[ax]['unit'] == 'pixel':
                                        scales[ax]['unit'] = 'µm'
                        self._lif_dims = img.info.get("dims")
                    except Exception:
                        # Fallback to AICSImage for LIF
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
                    # --- DICOM: spatial calibration + full imaging metadata
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

                    # Extract full DICOM imaging metadata
                    self.dicom_metadata = self._extract_dicom_imaging_metadata(src_path)

                elif AICSImage is not None:
                    # --- Generic OME fallback via AICSImage
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
                warnings.warn(f"Could not read physical pixel size from file {src_path}: {e}")

        # --- Final fallback
        for ax in scales:
            if not scales[ax]['unit']:
                scales[ax]['unit'] = "pixel"

        self.calibration = scales

    def _extract_dicom_imaging_metadata(self, src_path: str) -> Dict[str, Any]:
        """Extract comprehensive DICOM imaging metadata beyond spatial calibration."""
        ds = pydicom.dcmread(src_path)
        meta = {}

        # Spatial
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

        # Pixel characteristics
        for attr in ['Rows', 'Columns', 'BitsAllocated', 'BitsStored',
                     'PixelRepresentation', 'SamplesPerPixel']:
            if hasattr(ds, attr):
                meta[attr] = int(getattr(ds, attr))
        if hasattr(ds, 'PhotometricInterpretation'):
            meta['PhotometricInterpretation'] = str(ds.PhotometricInterpretation)

        # Display
        for attr in ['WindowCenter', 'WindowWidth', 'RescaleSlope', 'RescaleIntercept']:
            if hasattr(ds, attr):
                val = getattr(ds, attr)
                # These can be multi-valued
                if isinstance(val, pydicom.multival.MultiValue):
                    meta[attr] = [float(v) for v in val]
                else:
                    meta[attr] = float(val)

        # General
        if hasattr(ds, 'Modality'):
            meta['Modality'] = str(ds.Modality)

        return meta
        
    def _compute_statistics_via_ops(self, compute_percentiles: bool = True):
        """Compute intensity statistics using ImageJ Ops for efficiency."""
        try:
            ops = self.ij.op()
            
            # Basic statistics via Ops (fast, no array conversion needed)
            self.intensity_stats['min'] = float(ops.stats().min(self.dataset).getRealDouble())
            self.intensity_stats['max'] = float(ops.stats().max(self.dataset).getRealDouble())
            self.intensity_stats['mean'] = float(ops.stats().mean(self.dataset).getRealDouble())
            self.intensity_stats['std'] = float(ops.stats().stdDev(self.dataset).getRealDouble())
            
            # Derived statistics
            self.intensity_stats['dynamic_range'] = (
                self.intensity_stats['max'] - self.intensity_stats['min']
            )
            
            # Compute percentiles if requested (requires array conversion)
            if compute_percentiles:
                try:
                    # Convert to numpy array for percentile computation
                    img_array = self.ij.py.from_java(self.dataset)
                    data = np.asarray(img_array).flatten()
                    
                    self.intensity_stats['median'] = float(np.median(data))
                    self.intensity_stats['q1'] = float(np.percentile(data, 25))
                    self.intensity_stats['q3'] = float(np.percentile(data, 75))
                    self.intensity_stats['q95'] = float(np.percentile(data, 95))
                    self.intensity_stats['q99'] = float(np.percentile(data, 99))
                    
                except Exception as e:
                    warnings.warn(f"Could not compute percentiles: {e}")
                    self.intensity_stats['median'] = None
            
        except Exception as e:
            raise RuntimeError(f"Error computing statistics via ImageJ Ops: {e}")
    
    def _compute_histogram(self, n_bins: int = 256):
        """Compute intensity histogram using ImageJ Ops or NumPy."""
        try:
            # Try to use ImageJ histogram op first (faster)
            ops = self.ij.op()
            
            # Convert to numpy for histogram (ImageJ histogram ops can be complex)
            img_array = self.ij.py.from_java(self.dataset)
            data = np.asarray(img_array).flatten()
            
            hist, bins = np.histogram(data, bins=n_bins)
            
            self.intensity_stats['histogram'] = hist.tolist()
            self.intensity_stats['histogram_bins'] = bins.tolist()
            
        except Exception as e:
            warnings.warn(f"Could not compute histogram: {e}")
    
    def _compile_results(self) -> Dict[str, Any]:
        """Compile all results into single dictionary."""
        result = {
            'filename': self.metadata['name'],
            'source': self.metadata.get('source'),
            'structure': self.structure,
            'metadata': self.metadata,
            'calibration': self.calibration,
            'statistics': self.intensity_stats,
            'is_3d': self.metadata['is_3d'],
            'is_time_series': self.metadata['is_time_series'],
            'is_multichannel': self.metadata['is_multichannel']
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
        
        suggestions = {}
        
        # Otsu-like suggestion (between mean and max)
        suggestions['otsu_like_estimate'] = self.intensity_stats['mean'] + self.intensity_stats['std']
        
        # Percentile-based thresholds (if available)
        if 'q75' in self.intensity_stats and self.intensity_stats['q75'] is not None:
            suggestions['threshold_conservative'] = self.intensity_stats['q95']
            suggestions['threshold_moderate'] = self.intensity_stats['q75']
            suggestions['threshold_aggressive'] = self.intensity_stats.get('median', self.intensity_stats['mean'])
        
        # Min-max normalization range
        suggestions['normalization_range'] = (
            self.intensity_stats['min'], 
            self.intensity_stats['max']
        )
        
        # Robust normalization (if percentiles available)
        if 'q99' in self.intensity_stats and self.intensity_stats['q99'] is not None:
            suggestions['robust_normalization_range'] = (
                self.intensity_stats['min'], 
                self.intensity_stats['q99']
            )
        
        # Calibration-aware suggestions for filters
        x_info = self.calibration.get('X')
        if x_info and x_info['unit'] != 'pixel':
            x_scale = x_info['scale']
            unit = x_info['unit']
            suggestions['pixel_size'] = f"{x_scale:.4f} {unit}/pixel"
            
            # Suggest filter sizes in physical units
            # Target features at 0.5, 1.0, and 2.0 units
            small_feature_pixels = max(2, int(0.5 / x_scale))
            medium_feature_pixels = max(3, int(1.0 / x_scale))
            large_feature_pixels = max(5, int(2.0 / x_scale))
            
            suggestions['gaussian_sigma_small'] = {
                'pixels': small_feature_pixels,
                'physical': f"~0.5 {unit}"
            }
            suggestions['gaussian_sigma_medium'] = {
                'pixels': medium_feature_pixels,
                'physical': f"~1.0 {unit}"
            }
            suggestions['gaussian_sigma_large'] = {
                'pixels': large_feature_pixels,
                'physical': f"~2.0 {unit}"
            }
            
            # Morphological operation suggestions
            suggestions['morphology_kernel_small'] = {
                'pixels': max(3, int(0.3 / x_scale)),
                'physical': f"~0.3 {unit}"
            }
            suggestions['morphology_kernel_medium'] = {
                'pixels': max(5, int(0.5 / x_scale)),
                'physical': f"~0.5 {unit}"
            }
        
        return suggestions
    
    def suggest_filter_params(self) -> Dict[str, Any]:
        """Suggest filtering parameters based on noise characteristics."""
        if not self.intensity_stats:
            return {}
        
        suggestions = {}
        
        # Estimate SNR (simple approach)
        mean = self.intensity_stats['mean']
        std = self.intensity_stats['std']
        snr = mean / std if std > 0 else float('inf')
        
        suggestions['estimated_snr'] = snr
        
        # Suggest filtering strategy based on SNR
        if snr < 2:
            suggestions['noise_level'] = 'high'
            suggestions['recommended_filter'] = 'median or bilateral'
            suggestions['median_radius'] = 2
        elif snr < 5:
            suggestions['noise_level'] = 'moderate'
            suggestions['recommended_filter'] = 'gaussian'
            suggestions['gaussian_sigma'] = 1.5
        else:
            suggestions['noise_level'] = 'low'
            suggestions['recommended_filter'] = 'mild gaussian or none'
            suggestions['gaussian_sigma'] = 0.5
        
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
        
        # Histogram
        axes[0].bar(bin_centers, hist, width=np.diff(bins)[0], edgecolor='black', alpha=0.7)
        axes[0].axvline(self.intensity_stats['mean'], color='r', linestyle='--', 
                       label=f"Mean: {self.intensity_stats['mean']:.1f}")
        if 'median' in self.intensity_stats and self.intensity_stats['median'] is not None:
            axes[0].axvline(self.intensity_stats['median'], color='g', linestyle='--', 
                           label=f"Median: {self.intensity_stats['median']:.1f}")
        axes[0].set_xlabel('Intensity')
        axes[0].set_ylabel('Frequency')
        axes[0].set_title(f'Intensity Distribution - {self.metadata["name"]}')
        axes[0].legend()
        axes[0].grid(alpha=0.3)
        
        # Cumulative histogram
        cumsum = np.cumsum(hist) / np.sum(hist)
        axes[1].plot(bin_centers, cumsum, linewidth=2)
        if 'q95' in self.intensity_stats and self.intensity_stats['q95'] is not None:
            axes[1].axhline(0.95, color='r', linestyle='--', alpha=0.5, label='95th percentile')
            axes[1].axvline(self.intensity_stats['q95'], color='r', linestyle='--', alpha=0.5)
        axes[1].set_xlabel('Intensity')
        axes[1].set_ylabel('Cumulative Probability')
        axes[1].set_title('Cumulative Distribution')
        axes[1].legend()
        axes[1].grid(alpha=0.3)
        
        plt.tight_layout()
        plt.show()
    
    def print_report(self):
        """Print a formatted analysis report."""
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
            print(f"  Mean: {self.intensity_stats['mean']:.2f}")
            if 'median' in self.intensity_stats and self.intensity_stats['median'] is not None:
                print(f"  Median: {self.intensity_stats['median']:.2f}")
            print(f"  Std Dev: {self.intensity_stats['std']:.2f}")
            if 'q1' in self.intensity_stats and self.intensity_stats['q1'] is not None:
                print(f"  Q1 (25%): {self.intensity_stats['q1']:.2f}")
                print(f"  Q3 (75%): {self.intensity_stats['q3']:.2f}")
                print(f"  Q95 (95%): {self.intensity_stats['q95']:.2f}")
            print(f"  Dynamic Range: {self.intensity_stats['dynamic_range']:.2f}")
            
            print("\nSUGGESTED THRESHOLDING PARAMETERS:")
            print("-" * 70)
            suggestions = self.suggest_threshold_params()
            for key, value in suggestions.items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for k, v in value.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  {key}: {value}")
            
            print("\nSUGGESTED FILTERING PARAMETERS:")
            print("-" * 70)
            filter_suggestions = self.suggest_filter_params()
            for key, value in filter_suggestions.items():
                print(f"  {key}: {value}")
        
        print("=" * 70)


# Convenience function for quick analysis
def quick_analyze(ij, dataset=None, show_plot=True):
    """
    Quick analysis with default settings.
    
    Args:
        ij: PyImageJ instance
        dataset: Optional dataset (uses active if None)
        show_plot: Whether to display histogram plots
        
    Returns:
        ImageMetadataAnalyzer instance
    """
    analyzer = ImageMetadataAnalyzer(ij, dataset)
    analyzer.analyze(compute_histogram=True, compute_percentiles=True)
    analyzer.print_report()
    
    if show_plot:
        analyzer.plot_intensity_distribution()
    
    return analyzer


def _compute_standalone_stats(file_path: str, suffix: str, is_ome: bool) -> Dict[str, Any]:
    """
    Read pixel data directly (no ImageJ instance) and compute intensity
    statistics.  Returns a dict with min, max, mean, std, median, q1, q3,
    q95, q99, dynamic_range — or an empty dict on failure.
    """
    try:
        data: Optional[np.ndarray] = None

        if suffix in ['.tif', '.tiff']:
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
            'min': float(np.min(flat)),
            'max': float(np.max(flat)),
            'mean': float(np.mean(flat)),
            'std': float(np.std(flat)),
            'median': float(np.median(flat)),
            'q1': float(np.percentile(flat, 25)),
            'q3': float(np.percentile(flat, 75)),
            'q95': float(np.percentile(flat, 95)),
            'q99': float(np.percentile(flat, 99)),
            'dynamic_range': float(np.max(flat) - np.min(flat)),
        }
    except Exception as e:
        warnings.warn(f"Could not compute standalone pixel statistics for {file_path}: {e}")
        return {}


def _suggest_threshold_from_stats(stats: Dict[str, Any],
                                   calibration: Dict[str, Any]) -> Dict[str, Any]:
    """Derive threshold / normalisation suggestions from intensity stats."""
    if not stats:
        return {}

    suggestions: Dict[str, Any] = {}

    # Otsu-like estimate
    suggestions['otsu_like_estimate'] = stats['mean'] + stats['std']

    # Percentile-based thresholds
    suggestions['threshold_conservative'] = stats['q95']
    suggestions['threshold_moderate'] = stats['q3']
    suggestions['threshold_aggressive'] = stats['median']

    # Normalisation ranges
    suggestions['normalization_range'] = [stats['min'], stats['max']]
    suggestions['robust_normalization_range'] = [stats['min'], stats['q99']]

    # Calibration-aware filter / morphology sizes
    x_info = calibration.get('X')
    if x_info and x_info.get('unit') not in (None, 'pixel'):
        x_scale = x_info['scale']
        unit = x_info['unit']
        suggestions['pixel_size'] = f"{x_scale:.4f} {unit}/pixel"

        small_px = max(2, int(0.5 / x_scale))
        medium_px = max(3, int(1.0 / x_scale))
        large_px = max(5, int(2.0 / x_scale))

        suggestions['gaussian_sigma_small'] = {'pixels': small_px, 'physical': f"~0.5 {unit}"}
        suggestions['gaussian_sigma_medium'] = {'pixels': medium_px, 'physical': f"~1.0 {unit}"}
        suggestions['gaussian_sigma_large'] = {'pixels': large_px, 'physical': f"~2.0 {unit}"}

        suggestions['morphology_kernel_small'] = {'pixels': max(3, int(0.3 / x_scale)), 'physical': f"~0.3 {unit}"}
        suggestions['morphology_kernel_medium'] = {'pixels': max(5, int(0.5 / x_scale)), 'physical': f"~0.5 {unit}"}

    return suggestions


def _suggest_filter_from_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Derive filter / denoising suggestions from intensity stats."""
    if not stats:
        return {}

    suggestions: Dict[str, Any] = {}
    mean = stats['mean']
    std = stats['std']
    snr = mean / std if std > 0 else float('inf')
    suggestions['estimated_snr'] = snr

    if snr < 2:
        suggestions['noise_level'] = 'high'
        suggestions['recommended_filter'] = 'median or bilateral'
        suggestions['median_radius'] = 2
    elif snr < 5:
        suggestions['noise_level'] = 'moderate'
        suggestions['recommended_filter'] = 'gaussian'
        suggestions['gaussian_sigma'] = 1.5
    else:
        suggestions['noise_level'] = 'low'
        suggestions['recommended_filter'] = 'mild gaussian or none'
        suggestions['gaussian_sigma'] = 0.5

    return suggestions


def extract_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract format-specific metadata from a file without requiring an ImageJ
    instance or open dataset.  Returns a JSON-serializable dict with:
      - file_path, file_format
      - calibration (pixel scale / unit per axis)
      - dimensions (image dimensions)
      - dicom_imaging (only for DICOM files)

    This can be called by the agent before or after loading an image to get
    metadata for threshold / filter guidance.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = p.suffix.lower()
    name_lower = p.name.lower()
    is_ome = '.ome.' in name_lower

    result: Dict[str, Any] = {
        'file_path': str(p),
        'file_format': suffix.lstrip('.'),
        'calibration': {},
        'dimensions': {},
    }

    scales = result['calibration']
    dims = result['dimensions']

    try:
        if suffix in ['.tif', '.tiff'] and not is_ome:
            # --- Standard TIFF
            with tifffile.TiffFile(file_path) as tif:
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

                    scales['X'] = {'scale': x_scale, 'unit': tiff_unit}
                    scales['Y'] = {'scale': y_scale, 'unit': tiff_unit}

                # Dimensions from shape
                shape = tif.pages[0].shape
                dims['height'] = shape[0]
                dims['width'] = shape[1] if len(shape) > 1 else 1
                dims['pages'] = len(tif.pages)

        elif is_ome or suffix in ['.ome.tif', '.ome.tiff']:
            # --- OME-TIFF
            with tifffile.TiffFile(file_path) as tif:
                ome_xml = tif.ome_metadata
                if ome_xml:
                    root = ET.fromstring(ome_xml)
                    ns = {'ome': 'http://www.openmicroscopy.org/Schemas/OME/2016-06'}
                    pixels = root.find('.//ome:Pixels', ns)
                    if pixels is not None:
                        for attr in ['SizeX', 'SizeY', 'SizeZ', 'SizeC', 'SizeT']:
                            val = pixels.attrib.get(attr)
                            if val:
                                dims[attr] = int(val)

                        if 'PhysicalSizeX' in pixels.attrib:
                            px = float(pixels.attrib['PhysicalSizeX'])
                            py = float(pixels.attrib['PhysicalSizeY'])
                            pz = float(pixels.attrib.get('PhysicalSizeZ', 0))
                            unit = pixels.attrib.get('PhysicalSizeXUnit', 'µm')
                            scales['X'] = {'scale': px, 'unit': unit}
                            scales['Y'] = {'scale': py, 'unit': unit}
                            if pz > 0:
                                scales['Z'] = {'scale': pz, 'unit': unit}

        elif suffix == '.lif':
            # --- LIF via readlif
            try:
                lif = LifFile(file_path)
                img = lif.get_image(0)
                scale_n = img.info.get("scale_n")
                if scale_n:
                    for idx, ax in enumerate(['X', 'Y', 'Z']):
                        if idx < len(scale_n) and scale_n[idx] and scale_n[idx] > 0:
                            scales[ax] = {'scale': 1.0 / scale_n[idx], 'unit': 'µm'}
                lif_dims = img.info.get("dims")
                if lif_dims:
                    dims.update({k: v for k, v in zip(['X', 'Y', 'Z', 'T'], lif_dims) if v})
            except Exception:
                # Fallback to AICSImage
                if AICSImage is not None:
                    img = AICSImage(file_path)
                    phys = img.physical_pixel_sizes
                    for ax in ['X', 'Y', 'Z']:
                        val = getattr(phys, ax, None)
                        if val is not None:
                            scales[ax] = {'scale': val, 'unit': 'µm'}

        elif suffix in ['.dcm', '.dicom']:
            # --- DICOM
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

            # Full DICOM imaging metadata
            dicom_imaging: Dict[str, Any] = {}
            if hasattr(ds, 'PixelSpacing'):
                dicom_imaging['PixelSpacing'] = [float(v) for v in ds.PixelSpacing]
            if hasattr(ds, 'SliceThickness'):
                dicom_imaging['SliceThickness'] = float(ds.SliceThickness)
            if hasattr(ds, 'SpacingBetweenSlices'):
                dicom_imaging['SpacingBetweenSlices'] = float(ds.SpacingBetweenSlices)
            if hasattr(ds, 'ImageOrientationPatient'):
                dicom_imaging['ImageOrientationPatient'] = [float(v) for v in ds.ImageOrientationPatient]
            if hasattr(ds, 'ImagePositionPatient'):
                dicom_imaging['ImagePositionPatient'] = [float(v) for v in ds.ImagePositionPatient]
            for attr in ['Rows', 'Columns', 'BitsAllocated', 'BitsStored',
                         'PixelRepresentation', 'SamplesPerPixel']:
                if hasattr(ds, attr):
                    dicom_imaging[attr] = int(getattr(ds, attr))
            if hasattr(ds, 'PhotometricInterpretation'):
                dicom_imaging['PhotometricInterpretation'] = str(ds.PhotometricInterpretation)
            for attr in ['WindowCenter', 'WindowWidth', 'RescaleSlope', 'RescaleIntercept']:
                if hasattr(ds, attr):
                    val = getattr(ds, attr)
                    if isinstance(val, pydicom.multival.MultiValue):
                        dicom_imaging[attr] = [float(v) for v in val]
                    else:
                        dicom_imaging[attr] = float(val)
            if hasattr(ds, 'Modality'):
                dicom_imaging['Modality'] = str(ds.Modality)
            result['dicom_imaging'] = dicom_imaging

    except Exception as e:
        warnings.warn(f"Could not extract metadata from {file_path}: {e}")

    # --- Intensity statistics & suggestions (standalone, no ImageJ needed) ---
    stats = _compute_standalone_stats(file_path, suffix, is_ome)
    if stats:
        result['intensity_statistics'] = stats
        result['threshold_suggestions'] = _suggest_threshold_from_stats(stats, scales)
        result['filter_suggestions'] = _suggest_filter_from_stats(stats)

    return result
