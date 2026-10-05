from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import html as html_module
from pathlib import Path
import re
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from ..catalog import SectionCatalog
from ..model import Section, SectionProperty, normalize_property_key


DEFAULT_SITEMAP_INDEX = (
    "https://www.dlubal.com/sitemap-index-cross-section-properties-en.xml"
)
DEFAULT_USER_AGENT = (
    "ANYsection/0.1 (+https://github.com/audunarn/ANYsection; "
    "engineering catalogue extraction)"
)

_GROUP_NAMES = {
    "Geometry",
    "Sectional Area",
    "Bending",
    "Shear",
    "Torsion",
    "Warping",
    "Stability",
    "Plasticity",
    "Other",
}

_PROPERTY_NAMES = {
    "A": "Sectional area",
    "I_y": "Area moment of inertia about y-axis",
    "I_z": "Area moment of inertia about z-axis",
    "I_p": "Polar area moment of inertia",
    "i_y": "Radius of gyration about y-axis",
    "i_z": "Radius of gyration about z-axis",
    "i_p": "Polar radius of gyration",
    "max_S_y": "Maximum statical moment of area about y-axis",
    "max_S_z": "Maximum statical moment of area about z-axis",
    "W_y": "Elastic section modulus about y-axis",
    "W_z": "Elastic section modulus about z-axis",
    "A_y": "Shear area in y-direction",
    "A_z": "Shear area in z-direction",
    "I_t": "Torsional constant",
    "I_t_s": "Secondary torsional constant",
    "I_t_StVen": "Torsional constant (St. Venant)",
    "I_t_Bredt": "Torsional constant (Bredt)",
    "W_t": "Section modulus for torsion",
    "I_omega": "Warping constant",
    "i_omega": "Warping radius of gyration",
    "W_omega": "Warping section modulus",
    "W_pl_y": "Plastic section modulus about y-axis",
    "W_pl_z": "Plastic section modulus about z-axis",
    "W_pl_omega": "Plastic warping section modulus",
    "alpha_pl_y": "Plastic shape factor about y-axis",
    "alpha_pl_z": "Plastic shape factor about z-axis",
    "alpha_pl_omega": "Plastic warping shape factor",
    "A_pl_y": "Plastic shear area in y-direction",
    "A_pl_z": "Plastic shear area in z-direction",
    "N_pl": "Plastic limiting axial force",
    "V_pl_y": "Plastic limiting shear force in y-direction",
    "V_pl_z": "Plastic limiting shear force in z-direction",
    "M_pl_y": "Plastic limiting bending moment about y-axis",
    "M_pl_z": "Plastic limiting bending moment about z-axis",
    "N_u": "Ultimate resistance to axial force",
    "G": "Weight",
    "A_m": "Surface area per unit length",
    "V": "Volume per unit length",
    "A_m_per_V": "Section factor",
    "A_cell": "Cell area",
}


class DlubalError(RuntimeError):
    pass


@dataclass(slots=True)
class DlubalClient:
    delay: float = 0.5
    timeout: float = 30.0
    retries: int = 3
    user_agent: str = DEFAULT_USER_AGENT
    cache_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.cache_dir is not None:
            self.cache_dir = Path(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, url: str) -> str:
        cache_path = self._cache_path(url)
        if cache_path is not None and cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.delay > 0:
                time.sleep(self.delay)
            request = Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "gzip",
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = response.read()
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        payload = gzip.decompress(payload)
                    charset = response.headers.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                if cache_path is not None:
                    cache_path.write_text(text, encoding="utf-8")
                return text
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(min(2 ** attempt, 5))

        raise DlubalError(f"Failed to fetch {url}: {last_error}")

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        suffix = ".xml" if urlparse(url).path.endswith(".xml") else ".html"
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}{suffix}"


def discover_series_urls(
    client: DlubalClient,
    sitemap_index: str = DEFAULT_SITEMAP_INDEX,
) -> list[str]:
    """Discover Dlubal English cross-section series pages from the published sitemap."""
    pending = [sitemap_index]
    visited: set[str] = set()
    urls: set[str] = set()

    while pending:
        sitemap_url = pending.pop()
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)
        xml_text = client.fetch(sitemap_url)
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise DlubalError(f"Invalid sitemap XML at {sitemap_url}: {exc}") from exc

        local_name = root.tag.rsplit("}", 1)[-1]
        locs = [
            (node.text or "").strip()
            for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "loc" and (node.text or "").strip()
        ]

        if local_name == "sitemapindex":
            pending.extend(locs)
            continue

        for url in locs:
            parsed = urlparse(url)
            if "/en/cross-section-properties/" not in parsed.path:
                continue
            slug = parsed.path.rstrip("/").rsplit("/", 1)[-1]
            if slug.startswith("series-"):
                urls.add(url)

    return sorted(urls)


def parse_series_page(html: str, source_url: str) -> list[Section]:
    """Parse one Dlubal series page into normalized Section objects."""
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise DlubalError(
            "Dlubal HTML parsing requires beautifulsoup4. "
            'Install with: python -m pip install -e ".[scrape]"'
        ) from exc

    soup = BeautifulSoup(html, "html.parser")
    series, standard, manufacturer = _page_identity(soup, source_url)

    sections: dict[str, Section] = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header_index = _find_property_header_row(rows)
        if header_index is None:
            continue

        header_cells = rows[header_index].find_all(["th", "td"], recursive=False)
        if not header_cells:
            header_cells = rows[header_index].find_all(["th", "td"])
        headers = [_render_cell(cell) for cell in header_cells]
        section_column = _find_section_column(headers)
        if section_column is None:
            continue

        groups = _extract_groups(rows[:header_index], len(headers))
        parsed_headers: list[tuple[str, str | None, str | None, str]] = []
        for index, header in enumerate(headers):
            if index == section_column:
                parsed_headers.append(("Section", None, None, ""))
                continue
            symbol, unit = _parse_header(header)
            key = normalize_property_key(symbol)
            group = groups[index] if index < len(groups) else None
            if not group:
                group = _infer_group(key)
            parsed_headers.append((symbol, unit, group, key))

        for row in rows[header_index + 1 :]:
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells:
                cells = row.find_all(["td", "th"])
            if not cells:
                continue

            cells = _align_data_cells(cells, len(headers), section_column)
            if len(cells) != len(headers):
                continue

            section_cell = cells[section_column]
            name = _clean_section_name(_render_cell(section_cell))
            if not name or name.lower() in {"section", "select all"}:
                continue

            link = section_cell.find("a", href=True)
            detail_url = urljoin(source_url, link["href"]) if link else None

            section = Section(
                name=name,
                series=series,
                standard=standard,
                manufacturer=manufacturer,
                source="Dlubal",
                source_url=detail_url or source_url,
                metadata={
                    "source_series_url": source_url,
                    **({"source_detail_url": detail_url} if detail_url else {}),
                },
            )

            for index, cell in enumerate(cells):
                if index == section_column:
                    continue
                symbol, unit, group, key = parsed_headers[index]
                raw_value = _render_cell(cell)
                value = _parse_number(raw_value)
                if value is None:
                    continue
                section.add_property(
                    SectionProperty(
                        key=key,
                        symbol=symbol,
                        name=_property_name(key, symbol),
                        group=group,
                        value=value,
                        unit=unit,
                        source="Dlubal",
                        source_url=detail_url or source_url,
                        raw_value=raw_value,
                    )
                )

            if section.properties:
                sections[section.identifier] = section

    return sorted(sections.values(), key=lambda item: item.name)


class DlubalScraper:
    def __init__(
        self,
        client: DlubalClient | None = None,
        *,
        sitemap_index: str = DEFAULT_SITEMAP_INDEX,
    ):
        self.client = client or DlubalClient()
        self.sitemap_index = sitemap_index

    def discover(self) -> list[str]:
        return discover_series_urls(self.client, self.sitemap_index)

    def scrape_into(
        self,
        catalog: SectionCatalog,
        *,
        limit: int | None = None,
        resume: bool = True,
        on_progress: Callable[[int, int, str, str], None] | None = None,
    ) -> dict[str, int]:
        urls = self.discover()
        if limit is not None:
            urls = urls[: max(0, limit)]

        stats = {
            "series_total": len(urls),
            "series_ok": 0,
            "series_skipped": 0,
            "series_failed": 0,
            "sections_written": 0,
        }

        for index, url in enumerate(urls, start=1):
            if resume and catalog.scrape_status(url) == "ok":
                stats["series_skipped"] += 1
                if on_progress:
                    on_progress(index, len(urls), url, "skipped")
                continue

            try:
                html = self.client.fetch(url)
                sections = parse_series_page(html, url)
                if not sections:
                    raise DlubalError("No section property rows found")
                count = catalog.upsert_many(iter(sections))
                catalog.record_scrape(url, status="ok", section_count=count)
                stats["series_ok"] += 1
                stats["sections_written"] += count
                if on_progress:
                    on_progress(index, len(urls), url, f"ok:{count}")
            except Exception as exc:
                catalog.record_scrape(url, status="error", message=str(exc))
                stats["series_failed"] += 1
                if on_progress:
                    on_progress(index, len(urls), url, f"error:{exc}")

        return stats


def _page_identity(soup, source_url: str) -> tuple[str | None, str | None, str | None]:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    parts = [
        html_module.unescape(part).strip()
        for part in title.split("|")
        if html_module.unescape(part).strip()
    ]
    parts = [
        part
        for part in parts
        if "cross-section properties" not in part.lower()
        and "dlubal" not in part.lower()
    ]

    series = parts[0] if parts else None
    standard = parts[1] if len(parts) > 1 and parts[1] not in {"--", "-"} else None
    manufacturer = parts[2] if len(parts) > 2 and parts[2] not in {"--", "-"} else None

    if not series:
        slug = urlparse(source_url).path.rstrip("/").rsplit("/", 1)[-1]
        series = slug.removeprefix("series-").replace("-", " ").upper()
    return series, standard, manufacturer


def _find_property_header_row(rows) -> int | None:
    best: tuple[int, int] | None = None
    for index, row in enumerate(rows):
        cells = row.find_all(["th", "td"], recursive=False) or row.find_all(["th", "td"])
        texts = [_render_cell(cell) for cell in cells]
        section_positions = [
            pos for pos, text in enumerate(texts) if text.strip().lower() == "section"
        ]
        if not section_positions:
            continue
        score = len(cells)
        if best is None or score > best[1]:
            best = (index, score)
    return None if best is None else best[0]


def _find_section_column(headers: list[str]) -> int | None:
    for index, header in enumerate(headers):
        if header.strip().lower() == "section":
            return index
    return None


def _extract_groups(rows, header_count: int) -> list[str | None]:
    candidate: list[str | None] | None = None
    best_score = -1
    for row in rows:
        cells = row.find_all(["th", "td"], recursive=False) or row.find_all(["th", "td"])
        expanded: list[str | None] = []
        score = 0
        for cell in cells:
            text = _render_cell(cell).strip()
            colspan_raw = cell.get("colspan", 1)
            try:
                colspan = max(1, int(colspan_raw))
            except (TypeError, ValueError):
                colspan = 1
            group = text if text in _GROUP_NAMES else None
            if group:
                score += 1
            expanded.extend([group] * colspan)
        if score > best_score:
            candidate = expanded
            best_score = score

    if not candidate or best_score <= 0:
        return [None] * header_count

    if len(candidate) > header_count:
        candidate = candidate[-header_count:]
    elif len(candidate) < header_count:
        candidate = [None] * (header_count - len(candidate)) + candidate
    return candidate


def _align_data_cells(cells, header_count: int, section_column: int):
    cells = list(cells)
    if len(cells) == header_count:
        return cells

    while len(cells) > header_count:
        first_text = _render_cell(cells[0]).strip()
        first_has_link = bool(cells[0].find("a", href=True))
        if not first_text or (not first_has_link and cells[0].find("input") is not None):
            cells.pop(0)
        else:
            break

    if len(cells) > header_count:
        link_index = next(
            (
                index
                for index, cell in enumerate(cells)
                if cell.find("a", href=re.compile(r"/cross-section-properties/"))
            ),
            None,
        )
        if link_index is not None:
            start = link_index - section_column
            if start >= 0 and start + header_count <= len(cells):
                cells = cells[start : start + header_count]

    return cells


def _render_cell(cell) -> str:
    try:
        from bs4 import NavigableString, Tag
    except ImportError:
        return cell.get_text(" ", strip=True)

    def render(node) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ""
        name = (node.name or "").lower()
        content = "".join(render(child) for child in node.children)
        if name == "sub":
            return f"_{{{content.strip()}}}"
        if name == "sup":
            content = content.strip()
            return f"^{{{content}}}" if content else ""
        if name in {"br"}:
            return " "
        return content

    text = html_module.unescape(render(cell))
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_header(text: str) -> tuple[str, str | None]:
    text = text.strip()
    unit_match = re.search(r"\[([^\]]+)\]", text)
    if unit_match:
        unit = _normalize_unit(unit_match.group(1))
        symbol = (text[: unit_match.start()] + text[unit_match.end() :]).strip()
    else:
        unit = None
        symbol = text
    symbol = re.sub(r"\^\{\s*\}", "", symbol)
    symbol = re.sub(r"\s+", " ", symbol).strip()
    return symbol, unit


def _normalize_unit(unit: str) -> str:
    unit = re.sub(r"\s+", "", unit.strip())
    unit = re.sub(r"\^\{([^}]*)\}", r"^\1", unit)
    unit = (
        unit.replace("^{2}", "^2")
        .replace("^{3}", "^3")
        .replace("^{4}", "^4")
        .replace("^{6}", "^6")
    )
    return unit


def _parse_number(text: str) -> float | None:
    raw = text.strip()
    if not raw or raw in {"--", "-", "—", "–", "n/a", "N/A"}:
        return None

    raw = raw.replace("\u2212", "-").replace("\xa0", "").strip()
    raw = re.sub(r"\s+", "", raw)

    if "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    raw = raw.replace("'", "")

    match = re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", raw)
    if not match:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _clean_section_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+i$", "", text)
    return text


def _property_name(key: str, symbol: str) -> str:
    return _PROPERTY_NAMES.get(key, symbol)


def _infer_group(key: str) -> str:
    if key == "A" or key.startswith("e_"):
        return "Sectional Area"

    if key.startswith("I_t") or key == "W_t" or key.startswith("beta_"):
        return "Torsion"

    if "omega" in key and not key.startswith(("W_pl", "alpha_pl")):
        return "Warping"

    if key.startswith(("r_", "lambda_")):
        return "Stability"

    if key.startswith(
        ("W_pl", "alpha_pl", "A_pl", "N_pl", "V_pl", "M_pl", "y_pl", "z_pl")
    ):
        return "Plasticity"

    if key in {"A_y", "A_z", "y_SC", "z_SC"}:
        return "Shear"

    if key.startswith(("I_", "i_", "max_S_", "min_S_", "W_")):
        return "Bending"

    if key in {
        "N_u",
        "G",
        "A_m",
        "A_m_per_V",
        "V",
        "A_w",
        "A_cell",
    }:
        return "Other"

    return "Geometry"
