from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .model import Section, SectionProperty


SECTION_FIELDS = [
    "identifier",
    "name",
    "series",
    "standard",
    "manufacturer",
    "region",
    "shape",
    "manufacturing_type",
    "material",
    "source",
    "source_url",
]

PROPERTY_FIELDS = [
    *SECTION_FIELDS,
    "property_group",
    "property_key",
    "property_name",
    "property_symbol",
    "value",
    "unit",
    "property_source",
    "property_source_url",
    "raw_value",
]


def write_json(path: str | Path, sections: Iterable[Section]) -> None:
    payload = [section.to_dict() for section in sections]
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json(path: str | Path) -> list[Section]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    return [Section.from_dict(item) for item in payload]


def write_sections_csv(path: str | Path, sections: Iterable[Section]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=SECTION_FIELDS)
        writer.writeheader()
        for section in sections:
            writer.writerow(_section_row(section))


def write_properties_csv(path: str | Path, sections: Iterable[Section]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROPERTY_FIELDS)
        writer.writeheader()
        for section in sections:
            section_row = _section_row(section)
            for prop in sorted(
                section.properties.values(),
                key=lambda item: ((item.group or ""), item.key),
            ):
                writer.writerow(
                    {
                        **section_row,
                        "property_group": prop.group,
                        "property_key": prop.key,
                        "property_name": prop.name,
                        "property_symbol": prop.symbol,
                        "value": repr(prop.value),
                        "unit": prop.unit,
                        "property_source": prop.source,
                        "property_source_url": prop.source_url,
                        "raw_value": prop.raw_value,
                    }
                )


def read_properties_csv(path: str | Path) -> list[Section]:
    sections: dict[str, Section] = {}
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            identifier = row.get("identifier") or Section.make_identifier(
                row.get("name"),
                row.get("series"),
                row.get("standard"),
                row.get("manufacturer"),
                row.get("source"),
            )
            if identifier not in sections:
                sections[identifier] = Section(
                    identifier=identifier,
                    name=row["name"],
                    series=_none(row.get("series")),
                    standard=_none(row.get("standard")),
                    manufacturer=_none(row.get("manufacturer")),
                    region=_none(row.get("region")),
                    shape=_none(row.get("shape")),
                    manufacturing_type=_none(row.get("manufacturing_type")),
                    material=_none(row.get("material")),
                    source=_none(row.get("source")),
                    source_url=_none(row.get("source_url")),
                )
            section = sections[identifier]
            if row.get("property_key") and row.get("value") not in (None, ""):
                section.add_property(
                    SectionProperty(
                        key=row["property_key"],
                        value=float(row["value"]),
                        unit=_none(row.get("unit")),
                        symbol=_none(row.get("property_symbol")),
                        name=_none(row.get("property_name")),
                        group=_none(row.get("property_group")),
                        source=_none(row.get("property_source")),
                        source_url=_none(row.get("property_source_url")),
                        raw_value=_none(row.get("raw_value")),
                    )
                )
    return list(sections.values())


def write_wide_csv(path: str | Path, sections: Iterable[Section]) -> None:
    sections = list(sections)
    property_columns: set[tuple[str, str]] = set()
    for section in sections:
        for prop in section.properties.values():
            property_columns.add((prop.key, prop.unit or ""))

    ordered_properties = sorted(property_columns, key=lambda item: (item[0], item[1]))
    labels = {
        item: f"{item[0]} [{item[1]}]" if item[1] else item[0]
        for item in ordered_properties
    }
    fieldnames = [*SECTION_FIELDS, *(labels[item] for item in ordered_properties)]

    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for section in sections:
            row = _section_row(section)
            for prop in section.properties.values():
                row[labels[(prop.key, prop.unit or "")]] = repr(prop.value)
            writer.writerow(row)


def _section_row(section: Section) -> dict[str, str | None]:
    return {
        "identifier": section.identifier,
        "name": section.name,
        "series": section.series,
        "standard": section.standard,
        "manufacturer": section.manufacturer,
        "region": section.region,
        "shape": section.shape,
        "manufacturing_type": section.manufacturing_type,
        "material": section.material,
        "source": section.source,
        "source_url": section.source_url,
    }


def _none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
