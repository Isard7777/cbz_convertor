"""cbz-scraper CLI: download manga chapters and package them as CBZ files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .exceptions import ScraperError
from .scraper import ScraperConfig, run_scraper
from .utils import console_prefix

DEFAULT_TEMPLATE = (
    "https://www.scan-vf.net/uploads/manga/{manga}/chapters/chapter-{chapter}/{page:02d}.webp"
)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("must be a positive integer") from e
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("must be a positive number") from e
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cbz-scraper",
        description=(
            "Download manga chapters from a URL template and package them as CBZ files.\n\n"
            "Pass all options via a JSON --config file, or directly on the command line.\n"
            "Command-line arguments override values from the config file."
        ),
        epilog=(
            "JSON config example:\n"
            "  {\n"
            '    "manga": "one_piece",\n'
            '    "start": 1167,\n'
            '    "end": 1188,\n'
            '    "series_name": "One Piece",\n'
            '    "author": "Eiichiro Oda",\n'
            '    "convert_to": "jpg",\n'
            '    "output": "./scans"\n'
            "  }"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", "-c", type=str, metavar="FILE",
                        help="Path to a JSON config file describing the scraping job")
    parser.add_argument("--template", "-t", type=str, default=None,
                        help="URL template with {manga}, {chapter}, {page} placeholders")
    parser.add_argument("--manga", "-m", type=str, default=None,
                        help="Manga slug used in the URL template")
    parser.add_argument("--start", "-s", type=int, default=None,
                        help="First chapter to download")
    parser.add_argument("--end", "-e", type=int, default=None,
                        help="Last chapter to download (inclusive). Omit for open-ended mode.")
    parser.add_argument("--max-chapters", type=_positive_int, default=None,
                        help="Maximum number of chapters to process from --start")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output directory for CBZ files (default: current directory)")
    parser.add_argument("--convert-to", type=str, default=None,
                        choices=["jpg", "png", "webp"],
                        metavar="{jpg,png,webp}",
                        help="Convert all pages to this format (default: keep original)")
    parser.add_argument("--series-name", type=str, default=None,
                        help="Series name for ComicInfo.xml and CBZ filenames")
    parser.add_argument("--author", type=str, default=None,
                        help="Author/writer name for ComicInfo.xml")
    parser.add_argument("--max-pages", type=_positive_int, default=None,
                        help="Maximum pages per chapter (default: 60)")
    parser.add_argument("--delay", type=_positive_float, default=None,
                        help="Delay in seconds between requests (default: 0.2)")
    parser.add_argument("--workers", type=_positive_int, default=None,
                        help="Parallel chapter workers for finite chapter ranges (default: 1)")
    parser.add_argument("--stop-after-empty-chapters", type=_positive_int, default=None,
                        help="Stop open-ended mode after N consecutive empty chapters (default: 2)")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Probe URLs without writing files")
    parser.add_argument("--verbose", action="store_true", default=False,
                        help="Show detailed per-page logs")

    return parser


def _load_config_file(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise ScraperError(f"Config file not found: {config_path}")
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ScraperError(f"Invalid JSON in config file: {e}")
    if not isinstance(data, dict):
        raise ScraperError("Config file must be a JSON object")
    return data


def _build_scraper_config(args: argparse.Namespace) -> ScraperConfig:
    base: dict = {}
    if args.config:
        base = _load_config_file(args.config)

    cli_map = {
        "template": args.template,
        "manga": args.manga,
        "start": args.start,
        "end": args.end,
        "max_chapters": args.max_chapters,
        "output": args.output,
        "convert_to": args.convert_to,
        "series_name": args.series_name,
        "author": args.author,
        "max_pages": args.max_pages,
        "delay": args.delay,
        "workers": args.workers,
        "stop_after_empty_chapters": args.stop_after_empty_chapters,
    }
    for key, value in cli_map.items():
        if value is not None:
            base[key] = value

    if args.dry_run:
        base["dry_run"] = True
    if args.verbose:
        base["verbose"] = True

    if "template" not in base and "manga" in base:
        base["template"] = DEFAULT_TEMPLATE

    if "template" not in base:
        raise ScraperError(
            "A URL template is required. Use --template or set 'template' in the config file."
        )

    # 'start' is required only when tomes are not defined
    if "start" not in base and "tomes" not in base:
        raise ScraperError(
            "A start chapter is required. Use --start or set 'start' / 'tomes' in the config file."
        )

    return ScraperConfig.from_dict(base)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    try:
        cfg = _build_scraper_config(args)

        if cfg.tomes is None:
            if cfg.end is not None and cfg.start is not None and cfg.end < cfg.start:
                raise ScraperError("--end must be >= --start")
            if cfg.dry_run and cfg.end is None and cfg.max_chapters is None:
                raise ScraperError(
                    "--dry-run in open-ended mode requires --end or --max-chapters"
                )

        print(f"Template : {cfg.template}")
        if cfg.manga:
            print(f"Manga    : {cfg.manga}")
        if cfg.series_name:
            print(f"Series   : {cfg.series_name}")
        if cfg.author:
            print(f"Author   : {cfg.author}")
        if cfg.convert_to:
            print(f"Convert  : -> {cfg.convert_to.upper()}")
        if cfg.tomes:
            nums = [str(t.number) for t in cfg.tomes]
            print(f"Tomes    : {len(cfg.tomes)} tome(s) [{', '.join(nums)}]")
        print(f"Output   : {cfg.output.resolve()}")
        if cfg.dry_run:
            print("[DRY RUN - no files will be written]")
        print()

        total = run_scraper(cfg)

        label = "found (dry run)" if cfg.dry_run else "downloaded"
        print(f"\nDone. Total pages {label}: {total}")

    except ScraperError as e:
        print(f"{console_prefix('error', sys.stderr)}: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{console_prefix('warning', sys.stderr)}: Cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"{console_prefix('error', sys.stderr)}: Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
