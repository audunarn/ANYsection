from pathlib import Path

from anysection.importers.dlubal import discover_series_urls, parse_series_page


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_series_page():
    html = (FIXTURES / "dlubal_series.html").read_text(encoding="utf-8")
    sections = parse_series_page(
        html,
        "https://www.dlubal.com/en/cross-section-properties/series-dn-en-10220-2002-12",
    )
    assert len(sections) == 1
    section = sections[0]
    assert section.name == "DN 50 (60.3x2.9)"
    assert section.series == "DN"
    assert section.standard == "EN 10220:2002-12"
    assert section.value("A") == 5.23
    assert section.value("Iy") == 21.59
    assert section.value("It") == 43.18
    assert section.property("I_y").unit == "cm^4"
    assert section.property("A").group == "Sectional Area"
    assert section.source_url.endswith("dn-50-60-3x2-9-din-2605-2")


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads

    def fetch(self, url):
        return self.payloads[url]


def test_discover_series_urls_recurses_sitemap_index():
    index = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.test/part-1.xml</loc></sitemap>
      <sitemap><loc>https://example.test/part-2.xml</loc></sitemap>
    </sitemapindex>"""
    part1 = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://www.dlubal.com/en/cross-section-properties/series-ipe-en-10365</loc></url>
      <url><loc>https://www.dlubal.com/en/cross-section-properties/ipe-300-en-10365</loc></url>
    </urlset>"""
    part2 = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://www.dlubal.com/en/cross-section-properties/series-rhs-en-10210</loc></url>
      <url><loc>https://www.dlubal.com/de/querschnittswerte/series-rhs</loc></url>
    </urlset>"""

    client = FakeClient(
        {
            "https://example.test/index.xml": index,
            "https://example.test/part-1.xml": part1,
            "https://example.test/part-2.xml": part2,
        }
    )
    urls = discover_series_urls(client, "https://example.test/index.xml")
    assert urls == [
        "https://www.dlubal.com/en/cross-section-properties/series-ipe-en-10365",
        "https://www.dlubal.com/en/cross-section-properties/series-rhs-en-10210",
    ]
