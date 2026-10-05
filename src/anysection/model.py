from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable


_GREEK_REPLACEMENTS = {
    "α": "alpha",
    "ω": "omega",
    "φ": "phi",
    "θ": "theta",
    "λ": "lambda",
    "ρ": "rho",
    "μ": "mu",
    "ν": "nu",
}

_ALIAS_MAP = {
    "a": "A",
    "area": "A",
    "iy": "Iy",
    "i_y": "Iy",
    "iz": "Iz",
    "i_z": "Iz",
    "ip": "Ip",
    "i_p": "Ip",
    "it": "It",
    "i_t": "It",
    "iw": "Iw",
    "iomega": "Iw",
    "i_omega": "Iw",
    "ay": "Ay",
    "a_y": "Ay",
    "asy": "Ay",
    "as_y": "Ay",
    "az": "Az",
    "a_z": "Az",
    "asz": "Az",
    "as_z": "Az",
    "wy": "Wy",
    "w_y": "Wy",
    "wz": "Wz",
    "w_z": "Wz",
    "wply": "Wply",
    "w_pl_y": "Wply",
    "wplz": "Wplz",
    "w_pl_z": "Wplz",
}


def normalize_property_key(text: str) -> str:
    """Return a stable ASCII-ish lookup key for a property symbol or heading.

    The source symbol is never discarded; this key only supports storage and lookup.
    """
    value = (text or "").strip()
    for source, replacement in _GREEK_REPLACEMENTS.items():
        value = value.replace(source, replacement)

    value = value.replace("Ω", "omega")
    value = value.replace("²", "2").replace("³", "3")
    value = re.sub(r"\^\{?([^}]*)\}?", r"\1", value)
    value = re.sub(r"_\{([^}]*)\}", r"_\1", value)
    value = value.replace("{", "").replace("}", "")
    value = value.replace("max ", "max_").replace("min ", "min_")
    value = value.replace("/", "_per_")
    value = re.sub(r"[^0-9A-Za-z_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "property"


def _lookup_forms(text: str) -> set[str]:
    normalized = normalize_property_key(text)
    collapsed = normalized.replace("_", "")
    lower = normalized.lower()
    forms = {normalized, collapsed, lower, collapsed.lower()}
    alias = _ALIAS_MAP.get(lower) or _ALIAS_MAP.get(collapsed.lower())
    if alias:
        forms.add(alias)
        forms.add(alias.lower())
    return forms


@dataclass(slots=True)
class SectionProperty:
    key: str
    value: float
    unit: str | None = None
    symbol: str | None = None
    name: str | None = None
    group: str | None = None
    source: str | None = None
    source_url: str | None = None
    raw_value: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.key = normalize_property_key(self.key or self.symbol or self.name or "property")
        self.value = float(self.value)
        if self.unit:
            self.unit = self.unit.strip()
        if self.group:
            self.group = self.group.strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "symbol": self.symbol,
            "name": self.name,
            "group": self.group,
            "source": self.source,
            "source_url": self.source_url,
            "raw_value": self.raw_value,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SectionProperty":
        return cls(
            key=data.get("key") or data.get("symbol") or data.get("name") or "property",
            value=data["value"],
            unit=data.get("unit"),
            symbol=data.get("symbol"),
            name=data.get("name"),
            group=data.get("group"),
            source=data.get("source"),
            source_url=data.get("source_url"),
            raw_value=data.get("raw_value"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class Section:
    name: str
    series: str | None = None
    standard: str | None = None
    manufacturer: str | None = None
    region: str | None = None
    shape: str | None = None
    manufacturing_type: str | None = None
    material: str | None = None
    source: str | None = None
    source_url: str | None = None
    identifier: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    properties: dict[str, SectionProperty] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.identifier:
            self.identifier = self.make_identifier(
                self.name,
                self.series,
                self.standard,
                self.manufacturer,
                self.source,
                self.source_url,
            )

    @staticmethod
    def make_identifier(*parts: str | None) -> str:
        payload = "\x1f".join((part or "").strip().lower() for part in parts)
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
        human = normalize_property_key(parts[0] or "section").lower()[:48]
        return f"{human}-{digest}"

    def add_property(self, prop: SectionProperty, *, overwrite: bool = True) -> None:
        key = prop.key
        if key in self.properties and not overwrite:
            raise KeyError(f"Property {key!r} already exists on {self.name!r}")
        self.properties[key] = prop

    def extend_properties(
        self,
        properties: Iterable[SectionProperty],
        *,
        overwrite: bool = True,
    ) -> None:
        for prop in properties:
            self.add_property(prop, overwrite=overwrite)

    def property(self, key_or_symbol: str) -> SectionProperty:
        if key_or_symbol in self.properties:
            return self.properties[key_or_symbol]

        requested = _lookup_forms(key_or_symbol)
        alias_target = None
        for form in requested:
            alias_target = _ALIAS_MAP.get(form.lower()) or alias_target

        for prop in self.properties.values():
            candidates: set[str] = set()
            candidates.update(_lookup_forms(prop.key))
            if prop.symbol:
                candidates.update(_lookup_forms(prop.symbol))
            if prop.name:
                candidates.update(_lookup_forms(prop.name))

            canonical = _canonical_solver_alias(prop)
            if canonical:
                candidates.update(_lookup_forms(canonical))

            if requested & candidates:
                return prop
            if alias_target and canonical == alias_target:
                return prop

        raise KeyError(f"Property {key_or_symbol!r} not found on section {self.name!r}")

    def get_property(self, key_or_symbol: str, default: Any = None) -> SectionProperty | Any:
        try:
            return self.property(key_or_symbol)
        except KeyError:
            return default

    def value(self, key_or_symbol: str, default: Any = None) -> float | Any:
        prop = self.get_property(key_or_symbol)
        if prop is None:
            return default
        return prop.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "name": self.name,
            "series": self.series,
            "standard": self.standard,
            "manufacturer": self.manufacturer,
            "region": self.region,
            "shape": self.shape,
            "manufacturing_type": self.manufacturing_type,
            "material": self.material,
            "source": self.source,
            "source_url": self.source_url,
            "metadata": dict(self.metadata),
            "properties": [
                prop.to_dict()
                for prop in sorted(self.properties.values(), key=lambda item: item.key)
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Section":
        section = cls(
            identifier=data.get("identifier"),
            name=data["name"],
            series=data.get("series"),
            standard=data.get("standard"),
            manufacturer=data.get("manufacturer"),
            region=data.get("region"),
            shape=data.get("shape"),
            manufacturing_type=data.get("manufacturing_type"),
            material=data.get("material"),
            source=data.get("source"),
            source_url=data.get("source_url"),
            metadata=dict(data.get("metadata") or {}),
        )
        raw_properties = data.get("properties") or []
        if isinstance(raw_properties, dict):
            raw_properties = raw_properties.values()
        section.extend_properties(SectionProperty.from_dict(item) for item in raw_properties)
        return section

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _canonical_solver_alias(prop: SectionProperty) -> str | None:
    symbol = (prop.symbol or prop.key or "").strip()
    normalized = normalize_property_key(symbol).lower().replace("_", "")

    direct = {
        "a": "A",
        "iy": "Iy",
        "iz": "Iz",
        "ip": "Ip",
        "it": "It",
        "iomega": "Iw",
        "ay": "Ay",
        "az": "Az",
        "wy": "Wy",
        "wz": "Wz",
        "wply": "Wply",
        "wplz": "Wplz",
    }
    if normalized in direct:
        return direct[normalized]

    if normalized in {"iomega", "iw"}:
        return "Iw"
    return None
