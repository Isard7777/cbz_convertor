"""
CBZ Convertor - Command-line interface.
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import convert_nested_directory_to_cbz
from .exceptions import CBZConvertorError, CBZProcessingError, InvalidJSONError
from .modes import regroup_cbz, rename_cbz_images
from .utils import console_prefix


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("--workers must be a positive integer") from e

    if parsed < 1:
        raise argparse.ArgumentTypeError("--workers must be a positive integer")

    return parsed


def main():
    """Main entry point for the CBZ Convertor CLI."""
    parser = argparse.ArgumentParser(
        description="CBZ Convertor: regroup chapters or rename images for e-readers.",
        epilog="Examples:\n"
               "  Rename images: cbz-convertor --input input.cbz --output output.cbz\n"
               "  Regroup chapters: cbz-convertor --input chapters/ --output tomes/ --series 'Series Name' --infos config.json\n"
               "  Convert nested dirs: cbz-convertor --input 'Chapitre XXX/' --output tome.cbz --convert-nested",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--input", type=str, required=True, help="Input CBZ file or directory containing CBZ files")
    parser.add_argument("--output", type=str, required=True, help="Output CBZ file or directory for processed CBZ files")
    parser.add_argument(
        "--filenames",
        "--series",
        dest="filenames",
        type=str,
        help="Series name to use for output tome filenames (required for regrouping mode)",
    )
    parser.add_argument("--infos", type=str, help="JSON file with tomes configuration (required for regrouping mode)")
    parser.add_argument("--postfix", type=str, default="", help="Postfix to append to output filenames (optional)")
    parser.add_argument("--comic-series", type=str, help="Series name to write in ComicInfo.xml (rename mode)")
    parser.add_argument("--comic-author", type=str, help="Writer name to write in ComicInfo.xml (rename mode)")
    parser.add_argument(
        "--convert-nested",
        action="store_true",
        help="Convert nested directory structure (Chapitre XXX/page_XXX.jpg) to flat CBZ",
    )
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=8,
        help="Number of parallel workers to use for independent files or tomes (default: 8)",
    )

    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    postfix = args.postfix
    workers = args.workers
    comic_series = args.comic_series
    comic_author = args.comic_author
    convert_nested = args.convert_nested

    try:
        # Validate input path exists
        if not input_path.exists():
            raise CBZProcessingError(f"Input path does not exist: {input_path}")

        # Check if nested conversion mode is requested
        if convert_nested:
            _run_convert_nested_mode(input_path, output_path, comic_series, comic_author)
        # Check if regrouping mode is requested
        elif args.filenames and args.infos:
            _run_regroup_mode(input_path, output_path, args.filenames, args.infos, postfix, workers)
        else:
            _validate_mode_arguments(args.filenames, args.infos)
            _run_rename_mode(input_path, output_path, postfix, workers, comic_series, comic_author)

    except (CBZConvertorError, InvalidJSONError, CBZProcessingError) as e:
        print(f"{console_prefix('error', sys.stderr)}: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{console_prefix('warning', sys.stderr)}: Operation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"{console_prefix('error', sys.stderr)}: Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def _run_regroup_mode(
    input_path: Path,
    output_path: Path,
    series_name: str,
    infos_file: str,
    postfix: str,
    workers: int | None,
):
    """
    Run the regroup mode with validation.

    Args:
        input_path: Input directory path
        output_path: Output directory path
        series_name: Series name
        infos_file: Path to JSON configuration file
        postfix: Output filename postfix
        workers: Optional parallel worker count

    Raises:
        CBZProcessingError: If validation fails
        InvalidJSONError: If JSON is invalid
    """
    # Validate series name
    if not series_name.strip():
        raise CBZProcessingError("--series must not be empty")

    # Validate and load JSON
    infos_path = Path(infos_file)
    if not infos_path.exists():
        raise CBZProcessingError(f"JSON infos file not found: {infos_path}")

    try:
        with open(infos_path, "r", encoding="utf-8") as f:
            infos = json.load(f)
    except json.JSONDecodeError as e:
        raise InvalidJSONError(f"Invalid JSON format in {infos_path}: {e}")
    except IOError as e:
        raise CBZProcessingError(f"Failed to read JSON file {infos_path}: {e}")

    # Run regroup mode
    regroup_cbz(input_path, output_path, series_name, infos, postfix, workers)


def _run_rename_mode(
    input_path: Path,
    output_path: Path,
    postfix: str,
    workers: int | None,
    comic_series: str | None,
    comic_author: str | None,
):
    """
    Run the rename mode.

    Args:
        input_path: Input CBZ file or directory
        output_path: Output CBZ file or directory
        postfix: Output filename postfix
        workers: Optional parallel worker count
        comic_series: Optional series name for ComicInfo.xml
        comic_author: Optional writer name for ComicInfo.xml
    """
    rename_cbz_images(input_path, output_path, postfix, workers, comic_series, comic_author)


def _validate_mode_arguments(filename: str | None, infos: str | None):
    """
    Validate that mode arguments are consistent.

    Args:
        filename: filename argument
        infos: Infos file argument

    Raises:
        CBZProcessingError: If arguments are inconsistent
    """
    if filename or infos:
        raise CBZProcessingError(
            "Both --series and --infos must be provided together for regrouping mode. "
            "Omit both for simple rename mode."
        )


def _run_convert_nested_mode(
    input_path: Path,
    output_path: Path,
    comic_series: str | None,
    comic_author: str | None,
):
    """
    Convert a directory with nested chapter structure to flat CBZ.

    Args:
        input_path: Directory containing nested Chapitre folders
        output_path: Output CBZ file path
        comic_series: Optional series name for ComicInfo.xml
        comic_author: Optional writer name for ComicInfo.xml

    Raises:
        CBZProcessingError: If conversion fails
    """
    from .metadata import Metadata

    if not input_path.is_dir():
        raise CBZProcessingError(f"Input path must be a directory, got: {input_path}")

    # Build metadata for ComicInfo.xml
    metadata = Metadata()
    if comic_series:
        metadata.series = comic_series
    if comic_author:
        metadata.author = comic_author

    print(f"Converting nested structure: {input_path.name}")
    convert_nested_directory_to_cbz(input_path, output_path, metadata, show_progress=True)
    print(f"✓ Successfully created: {output_path}")


if __name__ == "__main__":
    main()

