"""
Core image processing functionality for CBZ files.
"""

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from PIL import Image
from tqdm import tqdm

from .exceptions import CBZProcessingError, ChapterExtractionError
from .metadata import Metadata

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
KEEP_FORMAT_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _convert_to_jpg(source_path: Path, target_path: Path) -> None:
    try:
        with Image.open(source_path) as img:
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                alpha = img.convert("RGBA")
                background = Image.new("RGB", alpha.size, (255, 255, 255))
                background.paste(alpha, mask=alpha.split()[-1])
                background.save(target_path, format="JPEG", quality=95)
            else:
                img.convert("RGB").save(target_path, format="JPEG", quality=95)
    except Exception as e:
        raise CBZProcessingError(f"Failed to convert image to JPG ({source_path.name}): {e}")


def extract_chapter_number(filename: str) -> int:
    """
    Extract chapter number from CBZ filename.

    Args:
        filename: The CBZ filename to parse

    Returns:
        The extracted chapter number

    Raises:
        ChapterExtractionError: If chapter number cannot be extracted
    """
    patterns = [
        r" - (\d+)\.cbz$",           # Format: "Series - 19.cbz"
        r"chapitre (\d+)\.cbz$",      # Format: "Series chapitre 1.cbz"
        r"chapter (\d+)\.cbz$",       # Format: "Series chapter 1.cbz"
        r"ch\.? ?(\d+)\.cbz$",        # Format: "Series ch. 1.cbz" or "Series ch 1.cbz"
        r"[- ](\d+)\.cbz$",           # Format: "Series-1.cbz" or "Series 1.cbz"
    ]

    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return int(match.group(1))

    raise ChapterExtractionError(
        f"Cannot extract chapter number from '{filename}'. "
        f"Expected formats: 'Series - 1.cbz', 'Series chapter 1.cbz', etc."
    )


def _extract_number_from_string(text: str) -> tuple:
    """
    Extract numbers and text parts from a string for natural sorting.

    Args:
        text: The string to parse

    Returns:
        Tuple of (int, str) parts for sorting
    """
    parts = re.findall(r"\d+|\D+", text.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _extract_chapter_number(path: str) -> int:
    """
    Try to extract a chapter number from the directory path.

    Looks for patterns like "Chapitre XXXX", "Chapter XXXX", etc.

    Args:
        path: Full path in the ZIP file

    Returns:
        Chapter number if found, or 0 if not found
    """
    # Extract directory name (first component of path)
    parts = Path(path).parts
    if len(parts) > 1:
        dir_name = parts[0].lower()
        # Look for chapter/chapitre patterns
        patterns = [
            r"chapitre\s+(\d+)",  # French: Chapitre 1145
            r"chapter\s+(\d+)",   # English: Chapter 1145
            r"ch\.?\s+(\d+)",     # Abbreviated: Ch. 1145 or Ch 1145
            r"^(\d+)",            # Just numbers: 1145
        ]
        for pattern in patterns:
            match = re.search(pattern, dir_name)
            if match:
                return int(match.group(1))
    return 0


def sorted_images(zip_file: zipfile.ZipFile):
    """
    Extract and sort images from a ZIP file, respecting nested chapter structure.

    Sorts by:
    1. Chapter number (if in nested directory structure)
    2. Natural sort of filename (numeric chunks as integers)

    This handles both flat structures (page_001.jpg, page_002.jpg) and
    nested structures (Chapitre 1145/page_001.jpg, Chapitre 1146/page_001.jpg).

    Args:
        zip_file: Open ZipFile object

    Returns:
        Sorted list of image filenames

    Raises:
        CBZProcessingError: If images cannot be read
    """
    try:
        images = [
            name for name in zip_file.namelist()
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS
        ]
    except Exception as e:
        raise CBZProcessingError(f"Failed to read ZIP contents: {e}")

    if not images:
        raise CBZProcessingError("No image files found in CBZ")

    def sort_key(path: str):
        # Extract chapter number if in nested structure
        chapter_num = _extract_chapter_number(path)

        # Extract filename for natural sort
        filename_stem = Path(path).stem.lower()
        filename_key = _extract_number_from_string(filename_stem)

        # Sort: first by chapter number, then by filename
        return (chapter_num, filename_key)

    return sorted(images, key=sort_key)


def process_cbz_images(cbz_files, output_cbz, cover_path=None, metadata=None, show_progress=True):
    """
    Extracts images from CBZ files, renames them sequentially, and writes to output CBZ.

    Args:
        cbz_files: List of Path objects to CBZ files
        output_cbz: Path where output CBZ will be written
        cover_path: Optional Path to cover image file
        metadata: Optional Metadata object to use for ComicInfo.xml
        show_progress: Whether to render a progress bar for this job

    Raises:
        CBZProcessingError: If CBZ processing fails
    """
    try:
        # Validate input files exist
        for cbz in cbz_files:
            if not cbz.exists():
                raise CBZProcessingError(f"Input CBZ file not found: {cbz}")
            if not cbz.is_file():
                raise CBZProcessingError(f"Input path is not a file: {cbz}")

        # Validate cover file if provided
        if cover_path and not cover_path.exists():
            raise CBZProcessingError(f"Cover image not found: {cover_path}")

        # Count total images to process
        total_images = 0
        for cbz in cbz_files:
            try:
                with zipfile.ZipFile(cbz, "r") as z:
                    total_images += len(sorted_images(z))
            except zipfile.BadZipFile as e:
                raise CBZProcessingError(f"Invalid or corrupted CBZ file: {cbz} - {e}")

        if cover_path:
            total_images += 1

        if total_images == 0:
            raise CBZProcessingError("No images found in any CBZ files")

        # Dynamic padding (at least 3 digits)
        padding = max(3, len(str(total_images)))

        if metadata is None:
            metadata = Metadata()

        metadata.page_count = total_images

        comic_info_str = metadata.to_comicinfo_xml()


        # Process with progress bar
        with tqdm(total=total_images * 2 + 1, desc=f"Processing {output_cbz.name}", unit="", bar_format="{desc}: {percentage:3.0f}%|{bar}| [{elapsed}<{remaining}]", disable=not show_progress) as pbar:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                page_counter = 1

                comicinfo_path = tmp_path / "ComicInfo.xml"
                comicinfo_path.write_text(comic_info_str, encoding="utf-8", newline="\n")
                pbar.update(1)

                # Add cover as first page if present
                if cover_path and cover_path.exists():
                    try:
                        cover_ext = cover_path.suffix.lower()
                        if cover_ext in KEEP_FORMAT_EXTENSIONS:
                            output_ext = ".png" if cover_ext == ".png" else ".jpg"
                            cover_dest = tmp_path / f"{0:0{padding}d}{output_ext}"
                            shutil.copy2(cover_path, cover_dest)
                        else:
                            cover_dest = tmp_path / f"{0:0{padding}d}.jpg"
                            _convert_to_jpg(cover_path, cover_dest)
                        pbar.update(1)
                    except IOError as e:
                        raise CBZProcessingError(f"Failed to copy cover image: {e}")

                # Extract and rename images
                for cbz in cbz_files:
                    try:
                        with zipfile.ZipFile(cbz, "r") as z:
                            for img_name in sorted_images(z):
                                try:
                                    ext = Path(img_name).suffix.lower()
                                    output_ext = ".png" if ext == ".png" else ".jpg"
                                    new_name = f"{page_counter:0{padding}d}{output_ext}"
                                    z.extract(img_name, tmp_path)
                                    extracted_path = tmp_path / img_name
                                    destination_path = tmp_path / new_name

                                    if ext in KEEP_FORMAT_EXTENSIONS:
                                        extracted_path.rename(destination_path)
                                    else:
                                        _convert_to_jpg(extracted_path, destination_path)
                                        extracted_path.unlink(missing_ok=True)

                                    page_counter += 1
                                    pbar.update(1)
                                except Exception as e:
                                    raise CBZProcessingError(
                                        f"Failed to extract image {img_name} from {cbz.name}: {e}"
                                    )
                    except zipfile.BadZipFile as e:
                        raise CBZProcessingError(f"Invalid CBZ file: {cbz} - {e}")

                # Write to output zip
                try:
                    images_to_write = sorted(tmp_path.glob("*"))
                    if not images_to_write:
                        raise CBZProcessingError("No images to write to output CBZ")

                    output_cbz.parent.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(output_cbz, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
                        for img in images_to_write:
                            out_zip.write(img, img.name)
                            pbar.update(1)
                except IOError as e:
                    raise CBZProcessingError(f"Failed to write output CBZ file: {e}")

    except CBZProcessingError:
        raise
    except Exception as e:
        raise CBZProcessingError(f"Unexpected error during CBZ processing: {e}")


def cbz_to_epub(cbz_path: Path, epub_path: Path):
    cbz_path = cbz_path.resolve()
    epub_path = epub_path.resolve()

    # Get ComicInfo.xml from cbz if it is present
    with zipfile.ZipFile(cbz_path, "r") as z:
        names = z.namelist()

        comicinfo_bytes = None
        if "ComicInfo.xml" in names:
            comicinfo_bytes = z.read("ComicInfo.xml")
        else:
            for n in names:
                if n.lower().endswith("/comicinfo.xml") or n.lower() == "comicinfo.xml":
                    comicinfo_bytes = z.read(n)
                    break


def convert_nested_directory_to_cbz(
    input_dir: Path,
    output_cbz: Path,
    metadata: Metadata = None,
    show_progress: bool = True,
) -> None:
    """
    Convert a directory with nested chapter structure (Chapitre XXXX/page_XXX.jpg) to flat CBZ.

    This handles e-reader incompatible structures where images are organized in chapter folders.
    Images are extracted recursively, sorted, and packed into a single flat CBZ file.

    Args:
        input_dir: Path to directory containing nested Chapitre folders
        output_cbz: Path where output CBZ will be written
        metadata: Optional Metadata object for ComicInfo.xml
        show_progress: Whether to show a progress bar

    Raises:
        CBZProcessingError: If conversion fails
    """
    if not input_dir.is_dir():
        raise CBZProcessingError(f"Input path is not a directory: {input_dir}")

    # Recursively find all image files
    image_files = []
    for ext in IMAGE_EXTENSIONS:
        image_files.extend(input_dir.rglob(f"*{ext}"))

    if not image_files:
        raise CBZProcessingError(f"No image files found in {input_dir}")

    # Sort respecting chapter structure (similar to sorted_images from ZIP)
    def sort_key(path: Path):
        # Extract chapter number from directory if in nested structure
        relative_path = path.relative_to(input_dir)
        path_parts = relative_path.parts
        
        chapter_num = 0
        if len(path_parts) > 1:
            dir_name = path_parts[0].lower()
            # Look for chapter/chapitre patterns
            patterns = [
                r"chapitre\s+(\d+)",  # French: Chapitre 1145
                r"chapter\s+(\d+)",   # English: Chapter 1145
                r"ch\.?\s+(\d+)",     # Abbreviated: Ch. 1145 or Ch 1145
                r"^(\d+)",            # Just numbers: 1145
            ]
            for pattern in patterns:
                match = re.search(pattern, dir_name)
                if match:
                    chapter_num = int(match.group(1))
                    break
        
        # Extract filename for natural sort
        filename_stem = path.stem.lower()
        filename_key = _extract_number_from_string(filename_stem)
        
        return (chapter_num, filename_key)

    image_files.sort(key=sort_key)

    if metadata is None:
        metadata = Metadata()

    metadata.page_count = len(image_files)
    comic_info_str = metadata.to_comicinfo_xml()

    # Process with progress bar
    padding = max(3, len(str(len(image_files))))
    total_operations = len(image_files) + 1  # +1 for comicinfo

    with tqdm(
        total=total_operations,
        desc=f"Converting {input_dir.name} to {output_cbz.name}",
        unit="file",
        disable=not show_progress,
    ) as pbar:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Write ComicInfo.xml
            comicinfo_path = tmp_path / "ComicInfo.xml"
            comicinfo_path.write_text(comic_info_str, encoding="utf-8", newline="\n")
            pbar.update(1)

            # Process and rename images
            for i, img_path in enumerate(image_files, 1):
                try:
                    ext = img_path.suffix.lower()
                    output_ext = ".png" if ext == ".png" else ".jpg"
                    new_name = f"{i:0{padding}d}{output_ext}"
                    dest_path = tmp_path / new_name

                    if ext in KEEP_FORMAT_EXTENSIONS:
                        shutil.copy2(img_path, dest_path)
                    else:
                        _convert_to_jpg(img_path, dest_path)

                    pbar.update(1)
                except Exception as e:
                    raise CBZProcessingError(f"Failed to process image {img_path.name}: {e}")

            # Create output CBZ
            try:
                output_cbz.parent.mkdir(parents=True, exist_ok=True)
                images_to_write = sorted(tmp_path.glob("*"))

                with zipfile.ZipFile(output_cbz, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for img in images_to_write:
                        zf.write(img, img.name)

            except IOError as e:
                raise CBZProcessingError(f"Failed to create output CBZ: {e}")


def sorted_files(files):
    """
    Sort files using natural sort (respecting nested directory structure if present).

    This is the filesystem equivalent of sorted_images() for ZIP files.
    It can handle both flat lists of files and paths with directory prefixes.

    Args:
        files: Iterable of Path objects to sort

    Returns:
        Sorted list of Path objects
    """
    def sort_key(path: Path):
        # Extract chapter number from parent directory if applicable
        chapter_num = _extract_chapter_number(str(path.parent / "dummy.jpg"))
        
        # Extract filename for natural sort
        filename_stem = path.stem.lower()
        filename_key = _extract_number_from_string(filename_stem)
        
        return (chapter_num, filename_key)

    return sorted(files, key=sort_key)
