"""
CBZ Convertor - Command-line interface.
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .exceptions import CBZConvertorError, CBZProcessingError, InvalidJSONError
from .modes import regroup_cbz, rename_cbz_images


def main():
    """Main entry point for the CBZ Convertor CLI."""
    parser = argparse.ArgumentParser(
        description="CBZ Convertor: regroup chapters or rename images for e-readers.",
        epilog="Examples:\n"
               "  Rename images: cbz-convertor --input input.cbz --output output.cbz\n"
               "  Regroup chapters: cbz-convertor --input chapters/ --output tomes/ --series 'Series Name' --infos config.json",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--input", type=str, required=True, help="Input CBZ file or directory containing CBZ files")
    parser.add_argument("--output", type=str, required=True, help="Output CBZ file or directory for processed CBZ files")
    parser.add_argument("--series", type=str, help="Series name (required for regrouping mode)")
    parser.add_argument("--infos", type=str, help="JSON file with tomes configuration (required for regrouping mode)")
    parser.add_argument("--postfix", type=str, default="", help="Postfix to append to output filenames (optional)")

    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    postfix = args.postfix

    try:
        # Validate input path exists
        if not input_path.exists():
            raise CBZProcessingError(f"Input path does not exist: {input_path}")

        # Check if regrouping mode is requested
        if args.series and args.infos:
            _run_regroup_mode(input_path, output_path, args.series, args.infos, postfix)
        else:
            _validate_mode_arguments(args.series, args.infos)
            _run_rename_mode(input_path, output_path, postfix)

    except (CBZConvertorError, InvalidJSONError, CBZProcessingError) as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def _run_regroup_mode(input_path: Path, output_path: Path, series_name: str, infos_file: str, postfix: str):
    """
    Run the regroup mode with validation.

    Args:
        input_path: Input directory path
        output_path: Output directory path
        series_name: Series name
        infos_file: Path to JSON configuration file
        postfix: Output filename postfix

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
    regroup_cbz(input_path, output_path, series_name, infos, postfix)


def _run_rename_mode(input_path: Path, output_path: Path, postfix: str):
    """
    Run the rename mode.

    Args:
        input_path: Input CBZ file or directory
        output_path: Output CBZ file or directory
        postfix: Output filename postfix
    """
    rename_cbz_images(input_path, output_path, postfix)


def _validate_mode_arguments(series: str | None, infos: str | None):
    """
    Validate that mode arguments are consistent.

    Args:
        series: Series name argument
        infos: Infos file argument

    Raises:
        CBZProcessingError: If arguments are inconsistent
    """
    if series or infos:
        raise CBZProcessingError(
            "Both --series and --infos must be provided together for regrouping mode. "
            "Omit both for simple rename mode."
        )


if __name__ == "__main__":
    main()

