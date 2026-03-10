"""
EMR ROI (Region of Interest) Analysis Module

This package contains all ROI-related functionality for thermal image analysis,
including C++ accelerated masking algorithms and Python utilities.

Components:
- cpp/: C++ implementation of high-performance ROI masking operations
- python/: Python bindings, analysis tools, and utility scripts
"""

__version__ = "1.0.0"
__author__ = "EMR Team"

# Convenience imports
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / "python"))
    
    from roi_mediapipe_dynamic import (
        rect_mask, polygon_mask, segment_mask, calc_stats
    )
    from roi_masks_binding import is_c_lib_available
    
    __all__ = [
        'rect_mask',
        'polygon_mask', 
        'segment_mask',
        'calc_stats',
        'is_c_lib_available',
    ]
except ImportError:
    # Optional: Allow package to load even if Python module unavailable
    __all__ = []
