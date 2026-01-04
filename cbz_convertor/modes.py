"""
Operation modes: rename and regroup functionalities.
"""

import sys
from pathlib import Path

from .core import extract_chapter_number, process_cbz_images
from .exceptions import CBZProcessingError, ChapterExtractionError, InvalidJSONError


def rename_cbz_images(input_path, output_path, postfix=""):
    """
    Rename images in CBZ file(s). Works with single files or directories.

    Args:
        input_path: Path to input CBZ file or directory
        output_path: Path to output CBZ file or directory
        postfix: Optional postfix to append to output filenames

    Raises:
        CBZProcessingError: If processing fails
    """
    try:
        cbz_files_to_process = []

        if input_path.is_file():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cbz_files_to_process.append((input_path, output_path))
        else:
            cbz_files = list(input_path.glob("*.cbz"))
            if not cbz_files:
                raise CBZProcessingError(f"No CBZ files found in directory: {input_path}")

            output_path.mkdir(parents=True, exist_ok=True)
            for cbz in cbz_files:
                out_name = cbz.stem + postfix + ".cbz"
                output_cbz = output_path / out_name
                cbz_files_to_process.append((cbz, output_cbz))

        # Process all files
        for cbz, output_cbz in cbz_files_to_process:
            print(f"Renaming images in {cbz.name}")
            process_cbz_images([cbz], output_cbz)
            print(f"✅ {cbz.name} processed: {output_cbz}")

        print("🎉 Done")

    except CBZProcessingError:
        raise
    except Exception as e:
        raise CBZProcessingError(f"Unexpected error during rename operation: {e}")


def regroup_cbz(input_path, output_path, series_name, infos, postfix=""):
    """
    Regroup CBZ files by chapters into tomes. Only works with directories.

    Args:
        input_path: Directory containing CBZ files
        output_path: Output directory for regrouped tomes
        series_name: Name of the series
        infos: Dictionary with tomes configuration from JSON
        postfix: Optional postfix to append to output filenames

    Raises:
        CBZProcessingError: If regrouping fails
        InvalidJSONError: If JSON structure is invalid
    """
    try:
        if input_path.is_file():
            raise CBZProcessingError(
                "Regroup mode (--series) only works with directories, not single files."
            )

        output_path.mkdir(parents=True, exist_ok=True)

        # Extract chapters from input directory
        cbz_files = list(input_path.glob("*.cbz"))
        if not cbz_files:
            raise CBZProcessingError(f"No CBZ files found in directory: {input_path}")

        # Extract and validate chapter numbers
        chapters = {}
        failed_extractions = []
        for cbz in cbz_files:
            try:
                chapter_num = extract_chapter_number(cbz.name)
                chapters[chapter_num] = cbz
            except ChapterExtractionError as e:
                failed_extractions.append((cbz.name, str(e)))

        if failed_extractions:
            error_msg = "Failed to extract chapter numbers from the following files:\n"
            for filename, error in failed_extractions:
                error_msg += f"  - {filename}: {error}\n"
            raise InvalidJSONError(error_msg)

        # Validate and parse tomes from infos
        try:
            if "tomes" not in infos:
                raise KeyError("tomes")

            tomes = {}
            for tome_key, tome_data in infos["tomes"].items():
                try:
                    tome_num = int(tome_key)

                    if "chapters" not in tome_data:
                        raise InvalidJSONError(
                            f"Tome {tome_num}: missing 'chapters' key. "
                            "Expected format: {\"chapters\": [start, end]}"
                        )

                    chapters_range = tome_data["chapters"]
                    if not isinstance(chapters_range, (list, tuple)) or len(chapters_range) != 2:
                        raise InvalidJSONError(
                            f"Tome {tome_num}: 'chapters' must be a list/tuple with 2 elements [start, end]"
                        )

                    start, end = chapters_range
                    tomes[tome_num] = (int(start), int(end))
                except (ValueError, TypeError) as e:
                    raise InvalidJSONError(f"Invalid tome number or chapter range: {e}")

        except KeyError as e:
            raise InvalidJSONError(
                f"Invalid JSON structure. Missing '{e.args[0]}' key. "
                "Expected structure: {'tomes': {'1': {'chapters': [1, 5], 'cover': 'path.jpg'}, ...}}"
            )

        if not tomes:
            raise InvalidJSONError("No tomes found in JSON configuration")

        # Extract cover paths (optional)
        covers = {}
        for tome_key, tome_data in infos["tomes"].items():
            tome_num = int(tome_key)
            if "cover" in tome_data and tome_data["cover"]:
                cover_path = Path(tome_data["cover"])
                if not cover_path.exists():
                    print(
                        f"⚠️  Warning: Cover image not found for Tome {tome_num}: {cover_path}",
                        file=sys.stderr
                    )
                else:
                    covers[tome_num] = cover_path

        # Calculate padding for consistent tome numbering
        max_tome = max(tomes.keys())
        tome_padding = len(str(max_tome))

        # Process each tome
        for tome_num, (start, end) in tomes.items():
            print(f"📘 Creating Tome {tome_num} ({start} → {end})")
            cover_path = covers.get(tome_num, None)

            # Collect chapters for this tome and track missing ones
            imgs_cbz = []
            missing_chapters = []
            for chap in range(start, end + 1):
                if chap in chapters:
                    imgs_cbz.append(chapters[chap])
                else:
                    missing_chapters.append(chap)

            # Warn if chapters are missing
            if missing_chapters:
                print(
                    f"⚠️  Warning: Missing chapters for Tome {tome_num}: {', '.join(map(str, missing_chapters))}",
                    file=sys.stderr
                )

            # Create output tome
            out_name = f"{series_name} - Tome {tome_num:0{tome_padding}d}{postfix}.cbz"
            output_cbz = output_path / out_name

            try:
                process_cbz_images(imgs_cbz, output_cbz, cover_path)
                print(f"✅ Tome {tome_num} created: {output_cbz}")
            except CBZProcessingError as e:
                print(f"❌ Failed to create Tome {tome_num}: {e}", file=sys.stderr)
                raise

        print("🎉 Done")

    except (InvalidJSONError, CBZProcessingError):
        raise
    except Exception as e:
        raise CBZProcessingError(f"Unexpected error during regrouping: {e}")

