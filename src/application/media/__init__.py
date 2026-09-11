"""Media extraction subsystem.

Provides extensible media content extraction for various file types.
"""

from .extractor import MediaExtractor
from .registry import MediaExtractorRegistry
from .txt_extractor import TxtExtractor

__all__ = ["MediaExtractor", "MediaExtractorRegistry", "TxtExtractor"]
