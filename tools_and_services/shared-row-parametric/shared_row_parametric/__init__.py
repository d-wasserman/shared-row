"""shared-row-parametric: a parametric layer over the shared-row specification.

Describe a street by parameters -- right-of-way width, archetype, mode
priorities -- and get a specification-compliant cross-section out, in any of
the three shared-row representations.

    >>> from shared_row_parametric import templates, metrics
    >>> result = templates.get("main_street").fit(22.0)
    >>> result.section.total_width
    22.0
    >>> metrics.allocation(result.section).auto_share
    0.6255
"""

from .fit import FitReport, FitResult, SliceSpec, fit
from .metrics import Allocation, Comparison, allocation, compare, network_summary
from .model import CrossSection, Slice, feature_collection
from .templates import Template, get, library, suggest

__version__ = "0.1.0"

__all__ = [
    "Slice", "CrossSection", "feature_collection",
    "SliceSpec", "Template", "fit", "FitResult", "FitReport",
    "get", "library", "suggest",
    "allocation", "compare", "network_summary", "Allocation", "Comparison",
    "__version__",
]
