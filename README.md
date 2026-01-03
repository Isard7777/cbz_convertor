# CBZ Convertor

A Python utility to process CBZ (comic book archive) files for e-readers. Renames images sequentially with zero-padded filenames and can regroup multiple chapter files into volume files based on JSON configuration.

## Features

- ✨ Sequential image renaming with automatic zero-padding
- 📚 Chapter-to-volume regrouping with JSON structure definition
- 🔍 Automatic chapter number extraction from various filename formats
- 📊 Progress tracking with tqdm
- 🧹 Automatic temporary file cleanup

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

Or with Python directly:

```sh
python main.py --input path/to/input --output path/to/output
```

**Arguments:**
- `--input`: File or folder containing the CBZ files to process
- `--output`: File or folder where the processed CBZ files will be saved

### 2. Regroup chapters into volumes

Prepare a JSON file describing the volume structure, for example:

```json
{
  "1": [1, 3],
  "2": [4, 7],
  "3": [8, 11],
  "4": [12, 15],
  "5": [16, 19],
  "6": [20, 23],
  "7": [24, 27],
  "8": [28, 31],
  "9": [32, 35],
  "10": [36, 39],
  "11": [40, 43],
  "12": [44, 47],
  "13": [48, 51],
  "14": [52, 55],
  "15": [60, 63],
  "16": [64, 67],
  "17": [68, 71],
  "18": [72, 75],
  "19": [76, 80]
}
```

If installed globally with `uv tool install`:

```sh
cbz-convertor --input path/to/input --output path/to/output --series "Boruto - Naruto Next Generations" --tomes path/to/tomes.json
```

If using development mode (`uv sync`):

```sh
uv run cbz-convertor --input path/to/input --output path/to/output --series "Boruto - Naruto Next Generations" --tomes path/to/tomes.json
```

Or with Python directly:

```sh
python main.py --input path/to/input --output path/to/output --series "Boruto - Naruto Next Generations" --tomes path/to/tomes.json
```

**Arguments:**
- `--series`: Series name (used for naming volumes)
- `--tomes`: Path to the JSON file describing the volume structure
- `--postfix`: (Optional) Suffix to add to output filenames

If both `--series` and `--tomes` are provided, the tool will regroup chapters into volumes. Otherwise, it will only rename images inside each CBZ.

## Supported Chapter Filename Formats

The tool automatically extracts chapter numbers from these formats:

- `Series - 19.cbz`
- `Series chapitre 1.cbz`
- `Series chapter 1.cbz`
- `Series ch. 1.cbz` or `Series ch 1.cbz`
- `Series-1.cbz` or `Series 1.cbz`

## How it works

- Files are processed in a temporary directory and cleaned up after processing.
- Images are renamed as `001.jpg`, `002.jpg`, etc. with automatic zero-padding
- In regroup mode, chapters are merged into volumes according to the provided structure.
- Images are sorted numerically first, then alphabetically

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
