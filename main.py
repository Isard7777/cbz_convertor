import argparse
import zipfile
from pathlib import Path
import re
import tempfile
import json
import sys
from tqdm import tqdm

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def extract_chapter_number(filename: str) -> int:
    # Try multiple patterns to extract chapter numbers
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

    raise ValueError(f"Cannot extract chapter number: {filename}")


def sorted_images(zip_file: zipfile.ZipFile):
    images = [
        name for name in zip_file.namelist()
        if Path(name).suffix.lower() in IMAGE_EXTENSIONS
    ]
    def sort_key(x):
        try:
            return (0, int(Path(x).stem))  # numeric names sort first
        except ValueError:
            return (1, x)  # non-numeric names sort after, alphabetically
    return sorted(images, key=sort_key)


def process_cbz_images(cbz_files, output_cbz):
    """
    Extracts images from cbz_files, renames them sequentially, and writes to output_cbz.
    """
    # 1. Count the total images to process
    total_images = 0
    for cbz in cbz_files:
        with zipfile.ZipFile(cbz, "r") as z:
            total_images += len(sorted_images(z))

    # 2. Dynamic padding (at least 3 digits)
    padding = max(3, len(str(total_images)))

    # 3. Single progress bar for both extraction and writing (total = extract + write)
    with tqdm(total=total_images * 2, desc=f"Processing {output_cbz.name}", unit="") as pbar:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            page_counter = 1

            # Extract and rename images
            for cbz in cbz_files:
                with zipfile.ZipFile(cbz, "r") as z:
                    for img_name in sorted_images(z):
                        ext = Path(img_name).suffix.lower()
                        new_name = f"{page_counter:0{padding}d}{ext}"
                        z.extract(img_name, tmp_path)
                        (tmp_path / img_name).rename(tmp_path / new_name)
                        page_counter += 1
                        pbar.update(1)

            # Write to output zip
            images_to_write = sorted(tmp_path.glob("*"))
            with zipfile.ZipFile(output_cbz, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
                for img in images_to_write:
                    out_zip.write(img, img.name)
                    pbar.update(1)


def rename_cbz_images(input_path, output_path, postfix=""):
    """Rename images in CBZ file(s). Works with single files or directories."""
    # Collect CBZ files and their output paths
    cbz_files_to_process = []

    if input_path.is_file():
        output_path.parent.mkdir(exist_ok=True)
        cbz_files_to_process.append((input_path, output_path))
    else:
        output_path.mkdir(exist_ok=True)
        for cbz in input_path.glob("*.cbz"):
            out_name = cbz.stem + postfix + ".cbz"
            output_cbz = output_path / out_name
            cbz_files_to_process.append((cbz, output_cbz))

    # Process all files
    for cbz, output_cbz in cbz_files_to_process:
        print(f"Renaming images in {cbz.name}")
        process_cbz_images([cbz], output_cbz)
        print(f"✅ {cbz.name} processed: {output_cbz}")

    print("🎉 Done")


def regroup_cbz(input_path, output_path, series_name, tomes, postfix=""):
    """Regroup CBZ files by chapters into tomes. Only works with directories."""
    if input_path.is_file():
        print("Error: Regroup mode (--series) only works with directories, not single files.", file=sys.stderr)
        exit(1)

    output_path.mkdir(exist_ok=True)
    chapters = {extract_chapter_number(cbz.name): cbz for cbz in input_path.glob("*.cbz")}

    for tome, (start, end) in tomes.items():
        print(f"📘 Creating Tome {tome} ({start} → {end})")
        imgs_cbz = [chapters[chap] for chap in range(start, end + 1) if chap in chapters]
        out_name = f"{series_name} - Tome {tome:02d}{postfix}.cbz"
        output_cbz = output_path / out_name
        process_cbz_images(imgs_cbz, output_cbz)
        print(f"✅ Tome {tome} created: {output_cbz}")

    print("🎉 Done")


def main():
    parser = argparse.ArgumentParser(description="CBZ Convertor: regroup chapters or rename images for e-readers.")
    parser.add_argument("--input", type=str, required=True, help="Input CBZ file or directory containing CBZ files")
    parser.add_argument("--output", type=str, required=True, help="Output CBZ file or directory for processed CBZ files")
    parser.add_argument("--series", type=str, help="Series name (for regrouping mode)")
    parser.add_argument("--tomes", type=str, help="JSON file with tome structure (for regrouping mode)")
    parser.add_argument("--postfix", type=str, default="", help="Postfix to append to output filenames in directory mode (optional)")
    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    postfix = args.postfix

    # Validate input path exists
    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}", file=sys.stderr)
        exit(1)

    if args.series and args.tomes:
        with open(args.tomes, "r", encoding="utf-8") as f:
            tomes = json.load(f)
        tomes = {int(k): tuple(v) for k, v in tomes.items()}
        regroup_cbz(input_path, output_path, args.series, tomes, postfix)
    else:
        rename_cbz_images(input_path, output_path, postfix)

if __name__ == "__main__":
    main()
