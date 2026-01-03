# CBZ Convertor

Python tool to regroup CBZ chapters into volumes or rename images inside each CBZ for better compatibility with e-readers (e.g., Kobo).

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management and execution. You can also use Python directly.

```sh
uv pip install -e .
```

## Usage

### 1. Rename images inside each CBZ

```sh
uv run cbz-convertor --input path/to/input --output path/to/output
```

- `--input`: folder containing the CBZ files to process
- `--output`: folder where the processed CBZ files will be saved

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

Run the command:

```sh
uv run cbz-convertor --input path/to/input --output path/to/output --series "Boruto - Naruto Next Generations" --tomes path/to/tomes.json
```

- `--series`: series name (used for naming volumes)
- `--tomes`: path to the JSON file describing the volume structure

If both `--series` and `--tomes` are provided, the tool will regroup chapters into volumes. Otherwise, it will only rename images inside each CBZ.

## How it works

- Files are processed in a temporary directory and cleaned up after processing.
- Images are renamed as `001.jpg`, `002.jpg`, etc.
- In regroup mode, chapters are merged into volumes according to the provided structure.

## Create an executable (optional)

To create a Windows executable with [PyInstaller](https://pyinstaller.org/):

```sh
pip install pyinstaller
pyinstaller --onefile main.py --name cbz-convertor
```

The executable will be available in the `dist/` folder.

## License

MIT
