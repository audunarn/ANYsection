"""ANYsection public API."""

from .model import Section, SectionProperty, normalize_property_key
from .catalog import SectionCatalog

__all__ = [
    "Section",
    "SectionProperty",
    "SectionCatalog",
    "normalize_property_key",
]

__version__ = "0.1.0"
