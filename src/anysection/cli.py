from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

from .catalog import SectionCatalog
from .importers.dlubal import DlubalClient, DlubalScraper
from .io import (
    write_json,
    write_properties_csv,
    write_sections_csv,
    write_wide_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anysection",
        description="ANYsection catalogue and cross-section tooling",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    dlubal = subparsers.add_parser("dlubal", help="Dlubal catalogue tools")
    dlubal_sub = dlubal.add_subparsers(dest="dlubal_command", required=True)

    discover = dlubal_sub.add_parser(
        "discover",
        help="Discover Dlubal cross-section series URLs from the published sitemap",
    )
    discover.add_argument(
        "--output",
        type=Path,
        help="Optional output text file; one series URL per line",
    )
    discover.add_argument("--delay", type=float, default=0.25)
    discover.add_argument("--timeout", type=float, default=30.0)
    discover.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".dlubal-cache"),
    )

    scrape = dlubal_sub.add_parser(
        "scrape",
        help="Scrape Dlubal series property tables into a local SQLite catalogue",
    )
    scrape.add_argument("--db", type=Path, default=Path("anysection.sqlite"))
    scrape.add_argument(
        "--limit",
        type=int,
        help="Only scrape the first N discovered series (useful for validation)",
    )
    scrape.add_argument("--delay", type=float, default=0.5)
    scrape.add_argument("--timeout", type=float, default=30.0)
    scrape.add_argument("--retries", type=int, default=3)
    scrape.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".dlubal-cache"),
    )
    scrape.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-fetch series already marked successful",
    )
    scrape.add_argument(
        "--errors",
        type=Path,
        default=Path("scrape_errors.csv"),
        help="Write failed series to this CSV",
    )

    export = subparsers.add_parser(
        "export",
        help="Export a SQLite catalogue to CSV/JSON",
    )
    export.add_argument("--db", type=Path, default=Path("anysection.sqlite"))
    export.add_argument("--sections", type=Path)
    export.add_argument("--properties", type=Path)
    export.add_argument("--wide", type=Path)
    export.add_argument("--json", type=Path)

    stats = subparsers.add_parser("stats", help="Show catalogue counts")
    stats.add_argument("--db", type=Path, default=Path("anysection.sqlite"))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "dlubal":
        return _run_dlubal(args)
    if args.command == "export":
        return _run_export(args)
    if args.command == "stats":
        return _run_stats(args)
    raise AssertionError(args.command)


def _client_from_args(args: argparse.Namespace) -> DlubalClient:
    return DlubalClient(
        delay=args.delay,
        timeout=args.timeout,
        retries=getattr(args, "retries", 3),
        cache_dir=args.cache_dir,
    )


def _run_dlubal(args: argparse.Namespace) -> int:
    scraper = DlubalScraper(_client_from_args(args))

    if args.dlubal_command == "discover":
        urls = scraper.discover()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text("\n".join(urls) + "\n", encoding="utf-8")
        else:
            print("\n".join(urls))
        print(f"Discovered {len(urls)} Dlubal series.", file=sys.stderr)
        return 0

    if args.dlubal_command == "scrape":
        catalog = SectionCatalog(args.db)

        def progress(index: int, total: int, url: str, status: str) -> None:
            print(f"[{index}/{total}] {status} {url}", file=sys.stderr)

        stats = scraper.scrape_into(
            catalog,
            limit=args.limit,
            resume=not args.no_resume,
            on_progress=progress,
        )
        _write_errors(args.errors, catalog.scrape_errors())
        print(json.dumps(stats, indent=2))
        return 0 if stats["series_failed"] == 0 else 2

    raise AssertionError(args.dlubal_command)


def _run_export(args: argparse.Namespace) -> int:
    outputs = [args.sections, args.properties, args.wide, args.json]
    if not any(outputs):
        print(
            "At least one export destination is required: "
            "--sections, --properties, --wide, or --json",
            file=sys.stderr,
        )
        return 2

    catalog = SectionCatalog(args.db)
    sections = list(catalog.iter_sections())

    for path in outputs:
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    if args.sections:
        write_sections_csv(args.sections, sections)
    if args.properties:
        write_properties_csv(args.properties, sections)
    if args.wide:
        write_wide_csv(args.wide, sections)
    if args.json:
        write_json(args.json, sections)

    print(
        json.dumps(
            {
                "sections": len(sections),
                "properties": sum(len(section.properties) for section in sections),
            },
            indent=2,
        )
    )
    return 0


def _run_stats(args: argparse.Namespace) -> int:
    catalog = SectionCatalog(args.db)
    print(
        json.dumps(
            {
                "sections": catalog.count_sections(),
                "properties": catalog.count_properties(),
                "scrape_errors": len(catalog.scrape_errors()),
            },
            indent=2,
        )
    )
    return 0


def _write_errors(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["source_url", "status", "section_count", "message", "updated_at"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
