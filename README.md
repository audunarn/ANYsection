# ANYsection

`ANYsection` is the cross-section layer for the ANY engineering ecosystem.

It is intentionally independent of `ANYsolver`: a solver should consume a section object and its engineering properties without caring whether those properties came from a standard catalogue, an external database, a user-defined section, or an in-house property calculator.

## Scope

The first implementation provides:

- a generic `Section` / `SectionProperty` model that preserves symbols, units, property groups, provenance, and raw source values;
- SQLite-backed catalogue storage and search;
- normalized CSV and JSON import/export;
- a wide CSV export for convenient engineering use;
- a Dlubal catalogue adapter that discovers the English cross-section sitemap and extracts complete property tables from series pages;
- a resumable command-line workflow suitable for building a local catalogue;
- tests and GitHub Actions CI.

No scraped third-party dataset is committed to this repository. The extraction code stores source URLs and provenance so catalogue data can be regenerated and audited.

## Installation

Core package:

```bash
python -m pip install -e .
```

For Dlubal extraction:

```bash
python -m pip install -e ".[scrape]"
```

For development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Python API

```python
from anysection import Section, SectionProperty

section = Section(
    name="Example",
    series="EX",
    standard="EN example",
)

section.add_property(
    SectionProperty(
        key="A",
        symbol="A",
        name="Sectional area",
        group="Sectional Area",
        value=53.8,
        unit="cm^2",
    )
)

print(section.value("A"))
```

Common solver-style aliases are supported when the source symbol can be identified:

```python
section.value("Iy")
section.value("Iz")
section.value("It")
section.value("Iw")
section.value("Ay")
section.value("Az")
```

The original Dlubal symbol is still retained.

## Dlubal extraction

Discover the catalogue:

```bash
anysection dlubal discover --output dlubal_series_urls.txt
```

Scrape all discovered series to SQLite:

```bash
anysection dlubal scrape --db anysection.sqlite
```

A smaller validation run:

```bash
anysection dlubal scrape --db anysection.sqlite --limit 5
```

Resume is the default. Series already recorded as successful are skipped. Use `--no-resume` to force a refresh.

Export the resulting catalogue:

```bash
anysection export \
    --db anysection.sqlite \
    --sections sections.csv \
    --properties properties.csv \
    --wide sections_wide.csv \
    --json sections.json
```

### Output model

`properties.csv` is the master normalized representation: one property per row.

Typical columns include:

- section identity and catalogue metadata;
- property group (`Geometry`, `Bending`, `Shear`, `Torsion`, `Warping`, `Stability`, `Plasticity`, `Other`, ...);
- normalized key;
- source symbol;
- descriptive name where known;
- numeric value;
- unit;
- source URL;
- raw source value.

`sections_wide.csv` is a convenience pivot with one section per row. Because different section families expose different properties, the normalized representation should be treated as authoritative.

## Architecture

```text
ANYsection
├── model          section/property objects and key normalization
├── catalog        SQLite storage, search, and scrape-state tracking
├── io             CSV/JSON import/export
├── importers
│   └── dlubal     sitemap discovery and Dlubal property-table parser
└── cli            reproducible extraction/export commands
```

The intended dependency direction is:

```text
ANYmaterial ─────┐
                 │
ANYsection ──────┼──> ANYsolver
                 │
ANYgeometry ─────┘
        │
     ANYmesh
```

`ANYsection` does not depend on `ANYsolver`.

## Data provenance

The Dlubal importer:

1. starts from Dlubal's published cross-section sitemap index;
2. keeps only English cross-section-property series URLs;
3. parses the server-rendered series tables;
4. preserves the source series URL and, where available, the individual section URL;
5. records scrape success/failure in SQLite so large runs are resumable.

Before redistributing a generated third-party catalogue, verify the relevant source terms/licensing. The package itself is designed so the same schema can later be populated from standards/manufacturer geometry and properties calculated independently.

## License

Original source code is licensed under the [Mozilla Public License 2.0](LICENSE).
Original narrative documentation is licensed under [CC BY 4.0](docs/LICENSE.md);
embedded code and configuration remain MPL-2.0. Third-party catalogue data,
quotations and resources retain their owners’ terms and are not relicensed.
