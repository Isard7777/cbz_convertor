"""
Operation modes: rename and regroup functionalities.
"""

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from importlib.metadata import metadata
from pathlib import Path

from .core import extract_chapter_number, process_cbz_images
from .exceptions import CBZProcessingError, ChapterExtractionError, InvalidJSONError
from .utils import get_nested_value, console_prefix
from .metadata import Metadata


def _extract_tome_number_from_filename(filename: str) -> int | None:
    stem = Path(filename).stem
    patterns = [
        r"(?i)\b(?:tome|vol(?:ume)?)\s*0*(\d+)\b",
        r"(?i)\bT\s*0*(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, stem)
        if match:
            return int(match.group(1))

    return None


def _build_rename_metadata(cbz: Path, series_name: str | None, author: str | None) -> Metadata | None:
    tome_number = _extract_tome_number_from_filename(cbz.name)

    metadata = Metadata()
    has_value = False

    if series_name:
        metadata.series = series_name
        has_value = True

    if author:
        metadata.writers = [author]
        has_value = True

    if tome_number is not None:
        metadata.volume = str(tome_number)
        metadata.number = str(tome_number)
        has_value = True

    return metadata if has_value else None


def _rename_single_cbz(
    cbz: Path,
    output_cbz: Path,
    show_progress: bool,
    series_name: str | None,
    author: str | None,
) -> tuple[Path, Path]:
    metadata = _build_rename_metadata(cbz, series_name, author)
    process_cbz_images([cbz], output_cbz, metadata=metadata, show_progress=show_progress)
    return cbz, output_cbz


def _resolve_worker_count(total_jobs: int, workers: int | None) -> int:
    if total_jobs <= 1:
        return 1

    if workers is not None:
        return min(total_jobs, workers)

    return min(total_jobs, max(1, (os.cpu_count() or 1) - 1))


def _build_tome_metadata(base_metadata: Metadata, infos: dict, tome_num: int) -> Metadata:
    metadata = deepcopy(base_metadata)
    metadata.title = get_nested_value(infos, "tomes", f"{tome_num}", "title")
    metadata.number = tome_num
    metadata.volume = tome_num
    metadata.summary = get_nested_value(infos, "tomes", f"{tome_num}", "summary")
    metadata.year = get_nested_value(infos, "tomes", f"{tome_num}", "year")
    metadata.month = get_nested_value(infos, "tomes", f"{tome_num}", "month")
    metadata.day = get_nested_value(infos, "tomes", f"{tome_num}", "day")
    metadata.identifier = get_nested_value(infos, "tomes", f"{tome_num}", "identifier")

    additional_notes = get_nested_value(infos, "tomes", f"{tome_num}", "notes")
    if additional_notes:
        metadata.notes = f"{metadata.notes}\n {additional_notes}" if metadata.notes else additional_notes

    return metadata


def _create_tome(
    tome_num: int,
    chapter_range: tuple[int, int],
    chapters: dict[int, Path],
    covers: dict[int, Path],
    filenames: str,
    output_path: Path,
    postfix: str,
    tome_padding: int,
    base_metadata: Metadata,
    infos: dict,
    show_progress: bool,
) -> tuple[int, Path]:
    start, end = chapter_range
    tome_metadata = _build_tome_metadata(base_metadata, infos, tome_num)
    cover_path = covers.get(tome_num)

    imgs_cbz = []
    for chap in range(start, end + 1):
        if chap in chapters:
            imgs_cbz.append(chapters[chap])

    out_name = f"{filenames} - Tome {tome_num:0{tome_padding}d}{postfix}.cbz"
    output_cbz = output_path / out_name
    process_cbz_images(imgs_cbz, output_cbz, cover_path, tome_metadata, show_progress=show_progress)
    return tome_num, output_cbz


def rename_cbz_images(
    input_path,
    output_path,
    postfix="",
    workers: int | None = None,
    series_name: str | None = None,
    author: str | None = None,
):
    """
    Rename images in CBZ file(s). Works with single files or directories.

    Args:
        input_path: Path to input CBZ file or directory
        output_path: Path to output CBZ file or directory
        postfix: Optional postfix to append to output filenames
        workers: Optional number of parallel workers to use
        series_name: Optional series name for ComicInfo.xml metadata
        author: Optional writer name for ComicInfo.xml metadata

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
                # Generate output filename with series/author format if provided
                if series_name and author:
                    tome_number = _extract_tome_number_from_filename(cbz.name)
                    print(f"{console_prefix('info')}: Processing '{cbz.name}' - extracted tome: {tome_number}")
                    if tome_number is not None:
                        out_name = f"{series_name} - T{tome_number:03d} - {author}{postfix}.cbz"
                    else:
                        out_name = f"{series_name} - {author}{postfix}.cbz"
                else:
                    out_name = cbz.stem + postfix + ".cbz"
                
                output_cbz = output_path / out_name
                cbz_files_to_process.append((cbz, output_cbz))

        if len(cbz_files_to_process) == 1:
            cbz, output_cbz = cbz_files_to_process[0]
            print(f"Renaming images in {cbz.name}")
            metadata = _build_rename_metadata(cbz, series_name, author)
            process_cbz_images([cbz], output_cbz, metadata=metadata)
            print(f"{console_prefix('ok')}: {cbz.name} processed: {output_cbz}")
        else:
            max_workers = _resolve_worker_count(len(cbz_files_to_process), workers)
            print(f"Parallel rename enabled: {len(cbz_files_to_process)} file(s), {max_workers} worker(s)")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_rename_single_cbz, cbz, output_cbz, False, series_name, author): (cbz, output_cbz)
                    for cbz, output_cbz in cbz_files_to_process
                }

                for future in as_completed(futures):
                    cbz, output_cbz = futures[future]
                    try:
                        future.result()
                        print(f"{console_prefix('ok')}: {cbz.name} processed: {output_cbz}")
                    except Exception as e:
                        raise CBZProcessingError(f"Failed to process {cbz.name}: {e}") from e

        print(console_prefix("done"))

    except CBZProcessingError:
        raise
    except Exception as e:
        raise CBZProcessingError(f"Unexpected error during rename operation: {e}")


def regroup_cbz(input_path, output_path, filenames, infos, postfix="", workers: int | None = None):
    """
    Regroup CBZ files by chapters into tomes. Only works with directories.

    Args:
        input_path: Directory containing CBZ files
        output_path: Output directory for regrouped tomes
        filenames: Name of the series
        infos: Dictionary with tomes configuration from JSON
        postfix: Optional postfix to append to output filenames
        workers: Optional number of parallel workers to use

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
                        f"{console_prefix('warning', sys.stderr)}: Cover image not found for Tome {tome_num}: {cover_path}",
                        file=sys.stderr
                    )
                else:
                    covers[tome_num] = cover_path

        # Extract optional series metadata from JSON
        metadata = Metadata(series=get_nested_value(infos, "series", "title"),
                            notes=get_nested_value(infos, "series", "notes"),
                            writers=get_nested_value(infos, "series", "writers"),
                            pencilers=get_nested_value(infos, "series", "pencilers"),
                            inkers=get_nested_value(infos, "series", "inkers"),
                            colorists=get_nested_value(infos, "series", "colorists"),
                            letterers=get_nested_value(infos, "series", "letterers"),
                            cover_artists=get_nested_value(infos, "series", "cover_artists"),
                            editors=get_nested_value(infos, "series", "editors"),
                            translators=get_nested_value(infos, "series", "translators"),
                            publishers=get_nested_value(infos, "series", "publishers"),
                            genres=get_nested_value(infos, "series", "genres"),
                            tags=get_nested_value(infos, "series", "tags"),
                            language=get_nested_value(infos, "series", "language"),
                            )


        # Calculate padding for consistent tome numbering
        max_tome = max(tomes.keys())
        tome_padding = len(str(max_tome))

        tome_jobs = []
        for tome_num, chapter_range in tomes.items():
            start, end = chapter_range
            print(f"{console_prefix('info')}: Creating Tome {tome_num} ({start} -> {end})")

            missing_chapters = [
                chap for chap in range(start, end + 1)
                if chap not in chapters
            ]

            if missing_chapters:
                print(
                    f"{console_prefix('warning', sys.stderr)}: Missing chapters for Tome {tome_num}: {', '.join(map(str, missing_chapters))}",
                    file=sys.stderr
                )

            tome_jobs.append((tome_num, chapter_range))

        max_workers = _resolve_worker_count(len(tome_jobs), workers)

        if max_workers == 1:
            for tome_num, chapter_range in tome_jobs:
                try:
                    _, output_cbz = _create_tome(
                        tome_num,
                        chapter_range,
                        chapters,
                        covers,
                        filenames,
                        output_path,
                        postfix,
                        tome_padding,
                        metadata,
                        infos,
                        True,
                    )
                    print(f"{console_prefix('ok')}: Tome {tome_num} created: {output_cbz}")
                except CBZProcessingError as e:
                    print(f"{console_prefix('error', sys.stderr)}: Failed to create Tome {tome_num}: {e}", file=sys.stderr)
                    raise
        else:
            print(f"Parallel regroup enabled: {len(tome_jobs)} tome(s), {max_workers} worker(s)")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _create_tome,
                        tome_num,
                        chapter_range,
                        chapters,
                        covers,
                        filenames,
                        output_path,
                        postfix,
                        tome_padding,
                        metadata,
                        infos,
                        False,
                    ): tome_num
                    for tome_num, chapter_range in tome_jobs
                }

                for future in as_completed(futures):
                    tome_num = futures[future]
                    try:
                        _, output_cbz = future.result()
                        print(f"{console_prefix('ok')}: Tome {tome_num} created: {output_cbz}")
                    except Exception as e:
                        print(f"{console_prefix('error', sys.stderr)}: Failed to create Tome {tome_num}: {e}", file=sys.stderr)
                        raise CBZProcessingError(f"Failed to create Tome {tome_num}: {e}") from e

        print(console_prefix("done"))

    except (InvalidJSONError, CBZProcessingError):
        raise
    except Exception as e:
        raise CBZProcessingError(f"Unexpected error during regrouping: {e}")

