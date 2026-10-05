"""External catalogue adapters."""

from .dlubal import (
    DEFAULT_SITEMAP_INDEX,
    DlubalClient,
    DlubalScraper,
    discover_series_urls,
    parse_series_page,
)

__all__ = [
    "DEFAULT_SITEMAP_INDEX",
    "DlubalClient",
    "DlubalScraper",
    "discover_series_urls",
    "parse_series_page",
]
