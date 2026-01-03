# CBZ Convertor

A Python utility to process CBZ (comic book archive) files for e-readers. Renames images sequentially with zero-padded filenames and can regroup multiple chapter files into volume files based on JSON configuration.

## Features

- ✨ Sequential image renaming with automatic zero-padding
- 📚 Chapter-to-volume regrouping with JSON structure definition
- 🔍 Automatic chapter number extraction from various filename formats
- 📊 Progress tracking with tqdm
- 🧹 Automatic temporary file cleanup

## Version

Check the current version:

```sh
cbz-convertor --version
```

This project uses [Versioneer](https://github.com/python-versioneer/python-versioneer) for automatic version management from Git tags. See [VERSIONING.md](VERSIONING.md) for details on how to create new releases.

## Installation

Dependencies are defined in `pyproject.toml`. You can install this project with any Python package manager.

### With uv (recommended - global installation)

```sh
uv tool install .
```

This installs `cbz-convertor` as a global command and manages its dependencies automatically.

### With uv (development mode)

```sh
uv sync
```

Then run with:

```sh
uv run cbz-convertor
```

### With pip

```sh
pip install -e .
```

## Usage

### 1. Rename images inside each CBZ

If installed globally with `uv tool install`:

```sh
cbz-convertor --input path/to/input --output path/to/output
```

If using development mode (`uv sync`):

```sh
uv run cbz-convertor --input path/to/input --output path/to/output
```


**Arguments:**
- `--input`: File or folder containing the CBZ files to process
- `--output`: File or folder where the processed CBZ files will be saved

### 2. Regroup chapters into volumes

Prepare a JSON file describing the series and volume structure, for example:

```json
{
  "tomes": {
    "1": {
      "cover": "/path/to/cover.jpg",
      "chapters": [1, 4]
    },
    "2": {
      "chapters": [5, 8]
    },
    "3": {
      "cover": "/path/to/cover2.jpg",
      "chapters": [9, 12]
    }
  }
}
```

If installed globally with `uv tool install`:

```sh
cbz-convertor --input path/to/input --output path/to/output --series "Series Name" --infos path/to/infos.json
```

If using development mode (`uv sync`):

```sh
uv run cbz-convertor --input path/to/input --output path/to/output --series "Series Name" --infos path/to/infos.json
```


**Arguments:**
- `--series`: Series name (used for naming volumes)
- `--infos`: Path to the JSON file describing series information and volume structure
- `--postfix`: (Optional) Suffix to add to output filenames
- `--verbose`: (Optional) Enable detailed output with chapter ranges for each tome

**JSON Structure:**
- `series`: (Object) Optional metadata about the series
- `tomes`: (Object) Volume definitions where:
  - Each key is the volume number (e.g., "1", "2", "3")
  - `chapters`: [start, end] - Chapter range to include in this volume (required)
  - `cover`: Path to cover image file (optional)
  - `title`, `summary`, `year`: Metadata fields (optional)

If both `--series` and `--infos` are provided, the tool will regroup chapters into volumes. Otherwise, it will only rename images inside each CBZ.

## Supported Chapter Filename Formats

The tool automatically extracts chapter numbers from these formats:

- `Series - 19.cbz`
- `Series chapitre 1.cbz`
- `Series chapter 1.cbz`
- `Series ch. 1.cbz` or `Series ch 1.cbz`
- `Series-1.cbz` or `Series 1.cbz`

## How it works

### Image Processing
- Files are processed in a temporary directory and cleaned up after processing
- Images are renamed as `001.jpg`, `002.jpg`, etc. with automatic zero-padding
- Padding is dynamically calculated based on total image count
- Images are sorted numerically first (by filename stem), then alphabetically

### Volume Regrouping
- Multiple chapters are merged into volumes according to the JSON structure
- Chapters within a volume are processed in sequential order
- If a cover image is specified, it's added as the first page of the volume
- Missing chapters are reported as warnings but don't stop processing
- Volume numbers are zero-padded to match the maximum tome count (e.g., "01", "001")

### Output
- Processed CBZ files are created with proper compression
- In rename mode: original filenames are preserved (or postfix is added)
- In regroup mode: volumes are named as "{Series Name} - Tome {XX}{postfix}.cbz"

## Build

### Create an executable (optional)

#### With PyInstaller

```sh
pip install pyinstaller
pyinstaller --onefile main.py --name cbz-convertor
```

The executable will be available in the `dist/` folder.

#### With Python build tools

```sh
python -m build
```

This creates a wheel package in the `dist/` folder.

## License

MIT
