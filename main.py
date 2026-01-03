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


def process_cbz_images(cbz_files, output_cbz, image_names=None, start_index=1):
    """
    Extracts images from cbz_files, renames them in order, and writes to output_cbz.
    If image_names is provided, only those images are processed (in order).
    start_index: starting index for image numbering.
    """
    # 1. Compter le nombre total d'images à traiter
    total_images = 0
    if image_names:
        total_images = len(image_names) * len(cbz_files)
    else:
        for cbz in cbz_files:
            with zipfile.ZipFile(cbz, "r") as z:
                total_images += len(sorted_images(z))
    # 2. Calcul du padding dynamique
    padding = max(3, len(str(start_index + total_images - 1)))
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        page_counter = start_index
        with tqdm(total=total_images, desc=f"Extracting {output_cbz.name}", unit="img") as pbar:
            for cbz in cbz_files:
                with zipfile.ZipFile(cbz, "r") as z:
                    imgs = image_names if image_names else sorted_images(z)
                    for img_name in imgs:
                        ext = Path(img_name).suffix.lower()
                        new_name = f"{page_counter:0{padding}d}{ext}"
                        z.extract(img_name, tmp_path)
                        (tmp_path / img_name).rename(tmp_path / new_name)
                        page_counter += 1
                        pbar.update(1)
        # Phase d'écriture dans le zip
        images_to_write = sorted(tmp_path.glob("*"))
        with tqdm(total=len(images_to_write), desc=f"Writing {output_cbz.name}", unit="img") as pbar_write:
            with zipfile.ZipFile(output_cbz, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
                for img in images_to_write:
                    out_zip.write(img, img.name)
                    pbar_write.update(1)


def rename_cbz_images(input_path, output_path, postfix=""):
    if input_path.is_file():
        output_path.parent.mkdir(exist_ok=True)
        cbz = input_path
        print(f"Renaming images in {cbz.name}")
        process_cbz_images([cbz], output_path)
        print(f"✅ {cbz.name} processed: {output_path}")
    else:
        output_path.mkdir(exist_ok=True)
        for cbz in input_path.glob("*.cbz"):
            print(f"Renaming images in {cbz.name}")
            out_name = cbz.stem + postfix + ".cbz"
            output_cbz = output_path / out_name
            process_cbz_images([cbz], output_cbz)
            print(f"✅ {cbz.name} processed: {output_cbz}")
    print("🎉 Done")


def regroup_cbz(input_path, output_path, series_name, tomes, postfix=""):
    if input_path.is_file():
        output_path.parent.mkdir(exist_ok=True)
        cbz_files = [input_path]
        tome, (start, end) = next(iter(tomes.items()))
        chapters = {extract_chapter_number(cbz.name): cbz for cbz in cbz_files}
        print(f"📘 Creating Tome {tome} ({start} → {end})")
        imgs_cbz = [chapters[chap] for chap in range(start, end + 1) if chap in chapters]
        process_cbz_images(imgs_cbz, output_path)
        print(f"✅ Tome {tome} created: {output_path}")
    else:
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
    # Enforce file/directory logic
    if input_path.is_file() and not output_path.suffix == ".cbz":
        print("If input is a file, output must be a .cbz file.", file=sys.stderr)
        exit(1)
    if input_path.is_dir() and output_path.exists() and not output_path.is_dir():
        print("If input is a directory, output must be a directory.", file=sys.stderr)
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
