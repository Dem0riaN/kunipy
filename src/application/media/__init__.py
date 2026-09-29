"""Media extraction subsystem.

Provides extensible media content extraction for various file types.
"""

from .extractor import MediaExtractor
from .image_processor import ImageProcessor
from .registry import MediaExtractorRegistry
from .txt_extractor import TxtExtractor

__all__ = ["ImageProcessor", "MediaExtractor", "MediaExtractorRegistry", "TxtExtractor"]
