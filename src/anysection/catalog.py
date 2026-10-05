from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .model import Section, SectionProperty


_SCHEMA_VERSION = 1


class SectionCatalog:
    """SQLite-backed storage for sections and normalized properties."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sections (
                    identifier TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    series TEXT,
                    standard TEXT,
                    manufacturer TEXT,
                    region TEXT,
                    shape TEXT,
                    manufacturing_type TEXT,
                    material TEXT,
                    source TEXT,
                    source_url TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_sections_name ON sections(name);
                CREATE INDEX IF NOT EXISTS idx_sections_series ON sections(series);
                CREATE INDEX IF NOT EXISTS idx_sections_standard ON sections(standard);
                CREATE INDEX IF NOT EXISTS idx_sections_manufacturer ON sections(manufacturer);

                CREATE TABLE IF NOT EXISTS properties (
                    section_id TEXT NOT NULL,
                    property_key TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT,
                    symbol TEXT,
                    name TEXT,
                    group_name TEXT,
                    source TEXT,
                    source_url TEXT,
                    raw_value TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (section_id, property_key),
                    FOREIGN KEY (section_id)
                        REFERENCES sections(identifier)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_properties_key
                    ON properties(property_key);
                CREATE INDEX IF NOT EXISTS idx_properties_symbol
                    ON properties(symbol);
                CREATE INDEX IF NOT EXISTS idx_properties_group
                    ON properties(group_name);

                CREATE TABLE IF NOT EXISTS scrape_log (
                    source_url TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    section_count INTEGER NOT NULL DEFAULT 0,
                    message TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(_SCHEMA_VERSION),),
            )

    def upsert(self, section: Section) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sections(
                    identifier, name, series, standard, manufacturer, region,
                    shape, manufacturing_type, material, source, source_url,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identifier) DO UPDATE SET
                    name=excluded.name,
                    series=excluded.series,
                    standard=excluded.standard,
                    manufacturer=excluded.manufacturer,
                    region=excluded.region,
                    shape=excluded.shape,
                    manufacturing_type=excluded.manufacturing_type,
                    material=excluded.material,
                    source=excluded.source,
                    source_url=excluded.source_url,
                    metadata_json=excluded.metadata_json
                """,
                (
                    section.identifier,
                    section.name,
                    section.series,
                    section.standard,
                    section.manufacturer,
                    section.region,
                    section.shape,
                    section.manufacturing_type,
                    section.material,
                    section.source,
                    section.source_url,
                    json.dumps(section.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
            connection.execute(
                "DELETE FROM properties WHERE section_id = ?",
                (section.identifier,),
            )
            connection.executemany(
                """
                INSERT INTO properties(
                    section_id, property_key, value, unit, symbol, name,
                    group_name, source, source_url, raw_value, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        section.identifier,
                        prop.key,
                        prop.value,
                        prop.unit,
                        prop.symbol,
                        prop.name,
                        prop.group,
                        prop.source,
                        prop.source_url,
                        prop.raw_value,
                        json.dumps(prop.metadata, ensure_ascii=False, sort_keys=True),
                    )
                    for prop in section.properties.values()
                ],
            )

    def upsert_many(self, sections: Iterator[Section] | list[Section]) -> int:
        count = 0
        for section in sections:
            self.upsert(section)
            count += 1
        return count

    def get(self, identifier: str) -> Section | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sections WHERE identifier = ?",
                (identifier,),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate(connection, row)

    def get_by_name(
        self,
        name: str,
        *,
        series: str | None = None,
        standard: str | None = None,
    ) -> Section | None:
        clauses = ["name = ?"]
        params: list[str] = [name]
        if series is not None:
            clauses.append("series = ?")
            params.append(series)
        if standard is not None:
            clauses.append("standard = ?")
            params.append(standard)

        query = "SELECT * FROM sections WHERE " + " AND ".join(clauses) + " LIMIT 1"
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
            if row is None:
                return None
            return self._hydrate(connection, row)

    def find(
        self,
        *,
        name: str | None = None,
        series: str | None = None,
        standard: str | None = None,
        manufacturer: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[Section]:
        clauses: list[str] = []
        params: list[object] = []
        for column, value in (
            ("name", name),
            ("series", series),
            ("standard", standard),
            ("manufacturer", manufacturer),
            ("source", source),
        ):
            if value is not None:
                clauses.append(f"LOWER({column}) LIKE LOWER(?)")
                params.append(f"%{value}%")

        query = "SELECT * FROM sections"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY series, name LIMIT ?"
        params.append(limit)

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
            return [self._hydrate(connection, row) for row in rows]

    def iter_sections(self) -> Iterator[Section]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sections ORDER BY series, standard, name"
            ).fetchall()
            for row in rows:
                yield self._hydrate(connection, row)

    def count_sections(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM sections").fetchone()[0])

    def count_properties(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM properties").fetchone()[0])

    def record_scrape(
        self,
        source_url: str,
        *,
        status: str,
        section_count: int = 0,
        message: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO scrape_log(source_url, status, section_count, message, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_url) DO UPDATE SET
                    status=excluded.status,
                    section_count=excluded.section_count,
                    message=excluded.message,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (source_url, status, section_count, message),
            )

    def scrape_status(self, source_url: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status FROM scrape_log WHERE source_url = ?",
                (source_url,),
            ).fetchone()
            return None if row is None else str(row["status"])

    def scrape_errors(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_url, status, section_count, message, updated_at
                FROM scrape_log
                WHERE status != 'ok'
                ORDER BY updated_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def _hydrate(connection: sqlite3.Connection, row: sqlite3.Row) -> Section:
        section = Section(
            identifier=row["identifier"],
            name=row["name"],
            series=row["series"],
            standard=row["standard"],
            manufacturer=row["manufacturer"],
            region=row["region"],
            shape=row["shape"],
            manufacturing_type=row["manufacturing_type"],
            material=row["material"],
            source=row["source"],
            source_url=row["source_url"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
        property_rows = connection.execute(
            """
            SELECT *
            FROM properties
            WHERE section_id = ?
            ORDER BY property_key
            """,
            (section.identifier,),
        ).fetchall()
        for prop_row in property_rows:
            section.add_property(
                SectionProperty(
                    key=prop_row["property_key"],
                    value=prop_row["value"],
                    unit=prop_row["unit"],
                    symbol=prop_row["symbol"],
                    name=prop_row["name"],
                    group=prop_row["group_name"],
                    source=prop_row["source"],
                    source_url=prop_row["source_url"],
                    raw_value=prop_row["raw_value"],
                    metadata=json.loads(prop_row["metadata_json"] or "{}"),
                )
            )
        return section
