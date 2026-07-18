# CBZ Convertor

A Python toolkit to process, scrape and package manga/comic files for e-readers.

## Features

- ✨ Sequential image renaming with automatic zero-padding
- 🖼️ Automatic image conversion for e-readers (WebP, AVIF, BMP → JPG/PNG)
- 📚 Chapter-to-volume regrouping with JSON structure definition
- 🌐 **Manga chapter scraper** — download pages from any URL template and package them as CBZ
- 📦 **Tome mode** — group chapters into volumes with cover images and `ComicInfo.xml`
- ⚡ Parallel processing for independent CBZ files and tomes
- 🔍 Automatic chapter number extraction from various filename formats
- 📊 Progress tracking with tqdm
- 🧹 Automatic temporary file cleanup

## Version

```sh
cbz-convertor --version
cbz-scraper --version
```

This project uses [Versioneer](https://github.com/python-versioneer/python-versioneer) for automatic version management from Git tags, and [Towncrier](https://towncrier.readthedocs.io/) for changelog management.

See [VERSIONING.md](VERSIONING.md) for details on how to create new releases and [CHANGELOG.md](CHANGELOG.md) for the release history.

## Installation

Dependencies are defined in `pyproject.toml`. You can install this project with any Python package manager.

### With uv (recommended — global installation)

```sh
uv tool install .
```

This installs both `cbz-convertor` and `cbz-scraper` as global commands.

### With uv (development mode)

```sh
uv sync
```

Then prefix commands with `uv run`:

```sh
uv run cbz-convertor ...
uv run cbz-scraper ...
```

### With pip

```sh
pip install -e .
```

---

## `cbz-convertor` — Process existing CBZ files

### 1. Rename images inside each CBZ

```sh
cbz-convertor --input path/to/input --output path/to/output \
  --comic-series "One Piece" --comic-author "Eiichiro Oda"
```

**Arguments:**
- `--input` — File or folder containing the CBZ files to process
- `--output` — File or folder where the processed CBZ files will be saved
- `--workers` — Number of parallel workers (default: `8`)
- `--comic-series` — Series name written to `ComicInfo.xml`
- `--comic-author` — Writer name written to `ComicInfo.xml`

### 2. Regroup chapters into volumes

Prepare a JSON file describing the volume structure:

```json
{
  "tomes": {
    "1": { "cover": "/path/to/cover1.jpg", "chapters": [1, 4] },
    "2": { "chapters": [5, 8] },
    "3": { "cover": "/path/to/cover3.jpg", "chapters": [9, 12] }
  }
}
```

```sh
cbz-convertor --input chapters/ --output tomes/ \
  --series "One Piece" --infos config.json
```

**Arguments:**
- `--series` / `--filenames` — Series name (used for output tome filenames)
- `--infos` — Path to the JSON configuration file
- `--postfix` — Suffix to add to output filenames (optional)
- `--workers` — Parallel workers for independent tomes (default: `8`)

**JSON structure:**
| Key | Description |
|---|---|
| `tomes` | Object where each key is the tome number |
| `chapters` | `[start, end]` chapter range (inclusive, required) |
| `cover` | Local path to cover image (optional) |
| `title`, `summary`, `year` | Extra metadata fields (optional) |

---

## `cbz-scraper` — Scrape & package manga chapters

Downloads pages from a URL template and packages them as `.cbz` files with `ComicInfo.xml`.

### Quick start

```sh
# Download chapters 1167–1188 individually, convert to JPG
cbz-scraper --manga one_piece --start 1167 --end 1188 \
  --series-name "One Piece" --author "Eiichiro Oda" \
  --convert-to jpg --output ./scans

# Open-ended mode (stops when chapters are missing)
cbz-scraper --manga one_piece --start 1167 --output ./scans

# From a JSON config file
cbz-scraper --config one_piece.json

# Dry-run — probe URLs without writing files
cbz-scraper --config one_piece.json --dry-run --verbose
```

### Arguments

| Argument | Description |
|---|---|
| `--config`, `-c` | JSON config file (see below); CLI args override it |
| `--template`, `-t` | URL template with `{manga}`, `{chapter}`, `{page}` placeholders |
| `--manga`, `-m` | Manga slug inserted into the template |
| `--start`, `-s` | First chapter to download |
| `--end`, `-e` | Last chapter (inclusive); omit for open-ended mode |
| `--max-chapters` | Cap on the number of chapters to process |
| `--output`, `-o` | Output directory (default: current directory) |
| `--convert-to` | Convert all pages to `jpg`, `png` or `webp` |
| `--series-name` | Series name for `ComicInfo.xml` and CBZ filenames |
| `--author` | Author/writer name for `ComicInfo.xml` |
| `--max-pages` | Maximum pages per chapter (default: `60`) |
| `--delay` | Delay between requests in seconds (default: `0.2`) |
| `--workers` | Parallel chapter workers for finite ranges (default: `1`) |
| `--stop-after-empty-chapters` | Stop open-ended mode after N empty chapters (default: `2`) |
| `--dry-run` | Probe URLs without writing any files |
| `--verbose` | Show detailed per-page logs |

### Chapter mode — JSON config

All keys are optional except `start` (and `template` if `--manga` is not provided).

```json
{
  "manga": "one_piece",
  "start": 1167,
  "end": 1188,
  "series_name": "One Piece",
  "author": "Eiichiro Oda",
  "convert_to": "jpg",
  "output": "./scans",
  "workers": 4
}
```

Default template (scan-vf.net) is used automatically when `manga` is set:
```
https://www.scan-vf.net/uploads/manga/{manga}/chapters/chapter-{chapter}/{page:02d}.webp
```

---

### Tome mode — group chapters into volumes

When the JSON config contains a `tomes` key, the scraper switches to **tome mode**:
all chapters of each tome are downloaded and merged into a **single CBZ per volume**,
with an optional cover image stored as `000.jpg`.

**This supports preview/incomplete tomes**: if a chapter is not yet published, it is
silently skipped — the CBZ is created with whatever chapters are available.

#### JSON config example

```json
{
  "manga": "one_piece",
  "series_name": "One Piece",
  "author": "Eiichiro Oda",
  "convert_to": "jpg",
  "output": "./tomes",
  "workers": 2,
  "tomes": {
    "115": {
      "chapters": [1167, 1179],
      "cover": "https://example.com/covers/one_piece_115.jpg"
    },
    "116": {
      "chapters": [1180, 1188]
    }
  }
}
```

```sh
cbz-scraper --config one_piece_tomes.json
```

**Output:**
```
tomes/
  One Piece - Tome 115.cbz   ← 13 chapters, cover as 000.jpg + pages 0001–NNNN
  One Piece - Tome 116.cbz   ← preview: only available chapters included
```

#### Tome JSON keys

| Key | Description |
|---|---|
| `chapters` | `[start, end]` chapter range (inclusive, **required**) |
| `cover` | URL **or** local path to the cover image → stored as `000.{ext}` (optional) |

#### How tome mode works

1. For each tome, pages are downloaded from all chapters sequentially with a **global page counter** (`0001`, `0002`, …)
2. If a `cover` is provided, it is downloaded/copied and saved as `000.jpg` (or converted to `--convert-to` format)
3. Missing chapters are logged as warnings but **do not stop** processing (preview support)
4. The CBZ is named `{series_name} - Tome {NNN}.cbz`
5. A `ComicInfo.xml` is embedded with series, volume number, author and page count
6. Multiple tomes can be processed in parallel with `--workers`

---

## URL template format

Templates support Python format specs:

| Placeholder | Example | Result |
|---|---|---|
| `{manga}` | `one_piece` | literal slug |
| `{chapter}` | `{chapter}` | `1167` |
| `{chapter:04d}` | — | `1167` (no effect here) |
| `{page:02d}` | — | `01`, `02`, … |
| `{page:03d}` | — | `001`, `002`, … |

**Extension fallback**: the scraper automatically tries `webp → jpg → jpeg → png → avif`
if the primary URL returns a 404, so the template extension is just a hint.

---

## Supported CBZ filename formats (rename mode)

- `Series - 19.cbz`
- `Series chapitre 1.cbz`
- `Series chapter 1.cbz`
- `Series ch. 1.cbz` / `Series ch 1.cbz`
- `Series-1.cbz` / `Series 1.cbz`

---

## How it works

### Image processing
- Images are renamed as `001.jpg`, `002.jpg`, … with automatic zero-padding
- Non e-reader formats (WebP, AVIF, BMP, GIF…) are converted to JPG via Pillow
- JPG/JPEG stays JPG, PNG stays PNG
- Alpha-channel images are composited on a white background before JPEG conversion

### Volume regrouping (`cbz-convertor`)
- Chapters are merged into volumes per the JSON structure
- Cover image (if specified) is inserted as the first page (`000`)
- Missing chapters are reported as warnings but do not stop processing
- Volume filenames: `{Series Name} - Tome {XX}{postfix}.cbz`

### Scraper output (`cbz-scraper`)
- **Chapter mode**: one CBZ per chapter — `{Series Name} - {chapter}.cbz`
- **Tome mode**: one CBZ per tome — `{Series Name} - Tome {NNN}.cbz`
- All CBZ files embed a `ComicInfo.xml` with series metadata

---

## Build

```sh
# Executable with PyInstaller
pip install pyinstaller
pyinstaller --onefile main.py --name cbz-convertor

# Wheel package
python -m build
```

## License

MIT
