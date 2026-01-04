"""
Core image processing functionality for CBZ files.
"""

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from tqdm import tqdm

from .exceptions import CBZProcessingError, ChapterExtractionError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


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


def sorted_images(zip_file: zipfile.ZipFile):
    """
    Extract and sort images from a ZIP file.

    Numeric names sort first, then alphabetically.

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

    def sort_key(x):
        try:
            return (0, int(Path(x).stem))
        except ValueError:
            return (1, x)

    return sorted(images, key=sort_key)


def process_cbz_images(cbz_files, output_cbz, cover_path=None):
    """
    Extracts images from CBZ files, renames them sequentially, and writes to output CBZ.

    Args:
        cbz_files: List of Path objects to CBZ files
        output_cbz: Path where output CBZ will be written
        cover_path: Optional Path to cover image file

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

        # Process with progress bar
        with tqdm(total=total_images * 2, desc=f"Processing {output_cbz.name}", unit="") as pbar:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                page_counter = 1

                # Add cover as first page if present
                if cover_path and cover_path.exists():
                    try:
                        cover_ext = cover_path.suffix.lower()
                        cover_dest = tmp_path / f"{0:0{padding}d}{cover_ext}"
                        shutil.copy2(cover_path, cover_dest)
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
                                    new_name = f"{page_counter:0{padding}d}{ext}"
                                    z.extract(img_name, tmp_path)
                                    (tmp_path / img_name).rename(tmp_path / new_name)
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

