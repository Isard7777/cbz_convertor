"""
Manga chapter scraper: downloads pages from a URL template and packages them as CBZ files.

URL template placeholders:
  {manga}   -> manga slug (optional)
  {chapter} -> chapter number (supports format spec, e.g. {chapter:03d})
  {page}    -> page number  (supports format spec, e.g. {page:02d})
"""

from __future__ import annotations

import re
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from .exceptions import ScraperError

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'requests' package is required for scraping. "
        "Install it with: pip install requests"
    ) from exc

from PIL import Image

from .core import sorted_files

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
}

FALLBACK_EXTENSIONS = ("webp", "jpg", "jpeg", "png", "avif")

CONTENT_TYPE_TO_EXTENSION: dict[str, str] = {
    "image/webp": "webp",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/avif": "avif",
}

CONVERTIBLE_TO_JPG = {"webp", "bmp", "gif", "tiff", "tif", "avif"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TomeConfig:
    """Definition of a single tome (volume) in tomes mode."""

    number: int
    chapter_start: int
    chapter_end: int
    cover: Optional[str] = None   # URL or local path; None = no cover

    @classmethod
    def from_dict(cls, number: int, data: dict) -> "TomeConfig":
        chapters = data.get("chapters")
        if not isinstance(chapters, (list, tuple)) or len(chapters) != 2:
            raise ScraperError(
                f"Tome {number}: 'chapters' must be a [start, end] array, got {chapters!r}"
            )
        return cls(
            number=number,
            chapter_start=int(chapters[0]),
            chapter_end=int(chapters[1]),
            cover=data.get("cover"),
        )


@dataclass
class ScraperConfig:
    """Full configuration for a scraping job (may come from JSON or CLI)."""

    template: str
    start: Optional[int] = None   # required when no tomes
    manga: Optional[str] = None
    end: Optional[int] = None
    max_chapters: Optional[int] = None
    output: Path = field(default_factory=lambda: Path("."))
    convert_to: Optional[str] = None          # "jpg" | "png" | None (keep original)
    series_name: Optional[str] = None
    author: Optional[str] = None
    max_pages: int = 60
    delay: float = 0.2
    workers: int = 1
    stop_after_empty_chapters: int = 2
    dry_run: bool = False
    verbose: bool = False
    tomes: Optional[list["TomeConfig"]] = None   # set by from_dict when JSON has "tomes"

    def __post_init__(self):
        self.output = Path(self.output)
        if self.convert_to is not None:
            self.convert_to = self.convert_to.lower().lstrip(".")

    @classmethod
    def from_dict(cls, data: dict) -> "ScraperConfig":
        """Build a ScraperConfig from a plain dict (e.g. loaded from JSON)."""
        # Parse tomes separately before filtering fields
        tomes_raw = data.get("tomes")
        tomes: Optional[list[TomeConfig]] = None
        if tomes_raw:
            if not isinstance(tomes_raw, dict):
                raise ScraperError("'tomes' must be a JSON object keyed by tome number")
            tomes = []
            for key, tome_data in tomes_raw.items():
                try:
                    num = int(key)
                except ValueError:
                    raise ScraperError(f"Tome key '{key}' must be an integer")
                tomes.append(TomeConfig.from_dict(num, tome_data))
            tomes.sort(key=lambda t: t.number)

        allowed = {f for f in cls.__dataclass_fields__ if f != "tomes"}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in allowed}
        obj = cls(**filtered)
        obj.tomes = tomes
        return obj


@dataclass
class ChapterResult:
    chapter: int
    pages: int
    output_cbz: Optional[Path] = None
    lines: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _build_url(template: str, chapter: int, page: int, manga: Optional[str]) -> str:
    kwargs: dict[str, int | str] = {"chapter": chapter, "page": page}
    if manga is not None:
        kwargs["manga"] = manga
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ScraperError(f"Missing placeholder in template: {e}")


def _guess_extension(url: str) -> str:
    match = re.search(r"\.([a-zA-Z0-9]+)(?=$|[?#])", url)
    return match.group(1) if match else "webp"


def _replace_url_extension(url: str, extension: str) -> str:
    split = urlsplit(url)
    path = split.path
    if re.search(r"\.[a-zA-Z0-9]+$", path):
        path = re.sub(r"\.[a-zA-Z0-9]+$", f".{extension}", path)
    else:
        path = f"{path}.{extension}"
    return urlunsplit((split.scheme, split.netloc, path, split.query, split.fragment))


def _build_candidate_urls(url: str) -> list[str]:
    current_ext = _guess_extension(url).lower()
    ordered = [current_ext, *[e for e in FALLBACK_EXTENSIONS if e != current_ext]]
    seen: set[str] = set()
    candidates: list[str] = []
    for ext in ordered:
        candidate = _replace_url_extension(url, ext)
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _extension_from_content_type(content_type: str) -> Optional[str]:
    mime = content_type.split(";", 1)[0].strip().lower()
    return CONTENT_TYPE_TO_EXTENSION.get(mime)


# ---------------------------------------------------------------------------
# Image conversion helper (mirrors core._convert_to_jpg but format-agnostic)
# ---------------------------------------------------------------------------

def _convert_image(source: Path, dest: Path, target_format: str) -> None:
    """Convert *source* image to *target_format* and write to *dest*."""
    fmt = target_format.upper()
    if fmt in ("JPG", "JPEG"):
        fmt = "JPEG"
    try:
        with Image.open(source) as img:
            if fmt == "JPEG":
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    alpha = img.convert("RGBA")
                    bg = Image.new("RGB", alpha.size, (255, 255, 255))
                    bg.paste(alpha, mask=alpha.split()[-1])
                    bg.save(dest, format="JPEG", quality=95)
                else:
                    img.convert("RGB").save(dest, format="JPEG", quality=95)
            else:
                img.save(dest, format=fmt)
    except Exception as e:
        raise ScraperError(f"Failed to convert image ({source.name}): {e}")


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def _probe_page(url: str, session: "requests.Session", timeout: int = 15) -> Optional[str]:
    """Return the image extension if *url* serves a valid image, else None."""
    try:
        r = session.get(url, headers=HEADERS, timeout=timeout, stream=True)
        if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
            return (
                _extension_from_content_type(r.headers.get("Content-Type", ""))
                or _guess_extension(url)
            ).lower()
        return None
    except requests.RequestException:
        return None


def _download_page(
    url: str,
    dest_stem: Path,
    session: "requests.Session",
    convert_to: Optional[str],
    timeout: int = 15,
) -> Optional[str]:
    """
    Download an image to *dest_stem* (no suffix).  Handles format conversion.
    Returns the final extension on success, None on failure.
    """
    try:
        r = session.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return None
        ct = r.headers.get("Content-Type", "")
        if not ct.startswith("image"):
            return None

        src_ext = (_extension_from_content_type(ct) or _guess_extension(url)).lower()

        # Decide target extension
        if convert_to and src_ext != convert_to:
            target_ext = convert_to
        else:
            target_ext = src_ext

        final_path = dest_stem.with_suffix(f".{target_ext}")

        if convert_to and src_ext != convert_to:
            # Write original to a temp file then convert
            tmp_src = dest_stem.with_suffix(f".{src_ext}")
            tmp_src.write_bytes(r.content)
            _convert_image(tmp_src, final_path, convert_to)
            tmp_src.unlink(missing_ok=True)
        else:
            final_path.write_bytes(r.content)

        return target_ext

    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# Cover image download
# ---------------------------------------------------------------------------

def _download_cover(
    source: str,
    dest_stem: Path,
    session: "requests.Session",
    convert_to: Optional[str],
    timeout: int = 20,
) -> Optional[str]:
    """
    Download or copy a cover image to *dest_stem* (no suffix).

    *source* can be an HTTP(S) URL or a local file path.
    Returns the final extension on success, None on failure.
    """
    source_path = Path(source)
    if not source.startswith(("http://", "https://")) and source_path.exists():
        # Local file
        src_ext = source_path.suffix.lstrip(".").lower() or "jpg"
        target_ext = convert_to if convert_to else src_ext
        dest = dest_stem.with_suffix(f".{target_ext}")
        if convert_to and src_ext != convert_to:
            _convert_image(source_path, dest, convert_to)
        else:
            import shutil
            shutil.copy2(source_path, dest)
        return target_ext

    # Remote URL
    try:
        r = session.get(source, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return None
        ct = r.headers.get("Content-Type", "")
        if not ct.startswith("image"):
            return None
        src_ext = (_extension_from_content_type(ct) or _guess_extension(source)).lower()
        target_ext = convert_to if convert_to else src_ext
        dest = dest_stem.with_suffix(f".{target_ext}")
        if convert_to and src_ext != convert_to:
            tmp = dest_stem.with_suffix(f".{src_ext}")
            tmp.write_bytes(r.content)
            _convert_image(tmp, dest, convert_to)
            tmp.unlink(missing_ok=True)
        else:
            dest.write_bytes(r.content)
        return target_ext
    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# ComicInfo.xml helper
# ---------------------------------------------------------------------------

def _make_comicinfo_xml(
    series: Optional[str],
    chapter: int,
    author: Optional[str],
    page_count: int,
) -> str:
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom

    root = Element("ComicInfo")
    root.attrib["xmlns:xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
    root.attrib["xmlns:xsd"] = "http://www.w3.org/2001/XMLSchema"

    if series:
        SubElement(root, "Series").text = series
        SubElement(root, "Title").text = f"{series} #{chapter}"
    SubElement(root, "Number").text = str(chapter)
    if author:
        SubElement(root, "Writer").text = author
    SubElement(root, "PageCount").text = str(page_count)
    SubElement(root, "Manga").text = "Yes"

    xml_str = tostring(root, encoding="unicode")
    return minidom.parseString(xml_str).toprettyxml(indent="  ", encoding=None)


# ---------------------------------------------------------------------------
# Core chapter downloader
# ---------------------------------------------------------------------------

def download_chapter(
    cfg: ScraperConfig,
    chapter: int,
) -> ChapterResult:
    """
    Download one chapter and package it as a CBZ (or dry-run).

    Returns a ChapterResult with the path to the generated CBZ (or None for dry-run).
    """
    lines: list[str] = []

    with requests.Session() as session:
        if cfg.dry_run:
            return _dry_run_chapter(cfg, chapter, session)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            page = 1
            downloaded = 0
            checked = 0
            consecutive_fails = 0

            while page <= cfg.max_pages and consecutive_fails < 2:
                base_url = _build_url(cfg.template, chapter, page, cfg.manga)
                dest_stem = tmp_path / f"{page:03d}"
                ext = None

                for candidate in _build_candidate_urls(base_url):
                    ext = _download_page(candidate, dest_stem, session, cfg.convert_to)
                    if ext is not None:
                        break

                if ext is not None:
                    if cfg.verbose:
                        lines.append(f"  Page {page:03d} OK ({ext})")
                    downloaded += 1
                    consecutive_fails = 0
                else:
                    if cfg.verbose:
                        lines.append(f"  Page {page:03d} not found")
                    consecutive_fails += 1

                page += 1
                checked += 1
                time.sleep(cfg.delay)

            if downloaded == 0:
                lines.append(f"[Chapter {chapter}] No pages found, skipped")
                return ChapterResult(chapter=chapter, pages=0, lines=lines)

            # Build CBZ
            cbz_path = _pack_cbz(cfg, chapter, tmp_path, downloaded)
            lines.append(
                f"[Chapter {chapter}] Done: {downloaded} page(s) "
                f"(checked {checked}) -> {cbz_path.name}"
            )
            return ChapterResult(chapter=chapter, pages=downloaded, output_cbz=cbz_path, lines=lines)


def _dry_run_chapter(
    cfg: ScraperConfig,
    chapter: int,
    session: "requests.Session",
) -> ChapterResult:
    lines: list[str] = []
    page = 1
    found = 0
    checked = 0
    consecutive_fails = 0

    while page <= cfg.max_pages and consecutive_fails < 2:
        base_url = _build_url(cfg.template, chapter, page, cfg.manga)
        if cfg.verbose:
            lines.append(f"  Page {page:03d}")

        ext = None
        for attempt, candidate in enumerate(_build_candidate_urls(base_url), 1):
            if cfg.verbose:
                lines.append(f"    Try {attempt}: {candidate}")
            ext = _probe_page(candidate, session)
            if ext is not None:
                break

        if ext is not None:
            if cfg.verbose:
                lines.append(f"    Found image ({ext})")
            found += 1
            consecutive_fails = 0
        else:
            if cfg.verbose:
                lines.append("    No image found")
            consecutive_fails += 1

        page += 1
        checked += 1
        time.sleep(cfg.delay)

    if found == 0:
        lines.append(f"[Chapter {chapter}] No pages found")
    else:
        lines.append(f"[Chapter {chapter}] Found {found} page(s) (checked {checked})")

    return ChapterResult(chapter=chapter, pages=found, lines=lines)


def _pack_cbz(cfg: ScraperConfig, chapter: int, tmp_path: Path, page_count: int) -> Path:
    """Package images from *tmp_path* into a CBZ file and return its path."""
    cfg.output.mkdir(parents=True, exist_ok=True)

    series_slug = cfg.series_name or cfg.manga or "chapter"
    cbz_name = f"{series_slug} - {chapter}.cbz"
    cbz_path = cfg.output / cbz_name

    comicinfo = _make_comicinfo_xml(cfg.series_name, chapter, cfg.author, page_count)

    images = sorted_files(tmp_path.glob("*"))
    with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ComicInfo.xml", comicinfo)
        for img in images:
            zf.write(img, img.name)

    return cbz_path


# ---------------------------------------------------------------------------
# Tome downloader
# ---------------------------------------------------------------------------

@dataclass
class TomeResult:
    tome: TomeConfig
    pages: int
    output_cbz: Optional[Path] = None
    lines: list[str] = field(default_factory=list)


def _make_tome_comicinfo_xml(
    series: Optional[str],
    tome: TomeConfig,
    author: Optional[str],
    page_count: int,
) -> str:
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom

    root = Element("ComicInfo")
    root.attrib["xmlns:xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
    root.attrib["xmlns:xsd"] = "http://www.w3.org/2001/XMLSchema"
    if series:
        SubElement(root, "Series").text = series
        SubElement(root, "Title").text = f"{series} - Tome {tome.number}"
    SubElement(root, "Number").text = str(tome.number)
    SubElement(root, "Volume").text = str(tome.number)
    if author:
        SubElement(root, "Writer").text = author
    SubElement(root, "PageCount").text = str(page_count)
    SubElement(root, "Manga").text = "Yes"

    xml_str = tostring(root, encoding="unicode")
    return minidom.parseString(xml_str).toprettyxml(indent="  ", encoding=None)


def download_tome(cfg: ScraperConfig, tome: TomeConfig, tome_padding: int = 3) -> TomeResult:
    """
    Download all chapters of *tome* and package them into a single CBZ.

    Missing chapters are silently skipped (preview/incomplete tome support).
    Returns a TomeResult with the CBZ path (or None for dry-run).
    """
    lines: list[str] = []
    chapter_range = list(range(tome.chapter_start, tome.chapter_end + 1))
    label = f"Tome {tome.number} (ch. {tome.chapter_start}-{tome.chapter_end})"

    with requests.Session() as session:
        if cfg.dry_run:
            return _dry_run_tome(cfg, tome, session, chapter_range, label)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            global_page = 1  # pages are numbered globally across all chapters

            # --- Cover ---
            cover_ok = False
            if tome.cover:
                cover_ext = _download_cover(tome.cover, tmp_path / "000", session, cfg.convert_to)
                if cover_ext:
                    cover_ok = True
                    if cfg.verbose:
                        lines.append(f"  Cover OK ({cover_ext})")
                else:
                    lines.append(f"  [WARNING] Cover could not be downloaded: {tome.cover}")

            # --- Chapters ---
            chapters_found = 0
            for chapter in chapter_range:
                if cfg.verbose:
                    lines.append(f"  [Chapter {chapter}]")
                page = 1
                ch_pages = 0
                consecutive_fails = 0

                while page <= cfg.max_pages and consecutive_fails < 2:
                    base_url = _build_url(cfg.template, chapter, page, cfg.manga)
                    dest_stem = tmp_path / f"{global_page:04d}"
                    ext = None

                    for candidate in _build_candidate_urls(base_url):
                        ext = _download_page(candidate, dest_stem, session, cfg.convert_to)
                        if ext is not None:
                            break

                    if ext is not None:
                        if cfg.verbose:
                            lines.append(f"    Page {page:03d} OK ({ext}) -> {global_page:04d}")
                        ch_pages += 1
                        global_page += 1
                        consecutive_fails = 0
                    else:
                        if cfg.verbose:
                            lines.append(f"    Page {page:03d} not found")
                        consecutive_fails += 1

                    page += 1
                    time.sleep(cfg.delay)

                if ch_pages > 0:
                    chapters_found += 1
                    if cfg.verbose:
                        lines.append(f"    -> {ch_pages} page(s)")
                else:
                    lines.append(f"  [Chapter {chapter}] Not found (skipped)")

            total_pages = global_page - 1
            if cover_ok:
                total_pages += 1  # cover is 000, not counted in global_page

            if total_pages == 0:
                lines.append(f"[{label}] No pages found, skipped")
                return TomeResult(tome=tome, pages=0, lines=lines)

            cbz_path = _pack_tome_cbz(cfg, tome, tmp_path, total_pages, tome_padding)
            lines.append(
                f"[{label}] Done: {total_pages} page(s) across "
                f"{chapters_found}/{len(chapter_range)} chapter(s) -> {cbz_path.name}"
            )
            return TomeResult(tome=tome, pages=total_pages, output_cbz=cbz_path, lines=lines)


def _dry_run_tome(
    cfg: ScraperConfig,
    tome: TomeConfig,
    session: "requests.Session",
    chapter_range: list[int],
    label: str,
) -> TomeResult:
    lines: list[str] = []
    total_found = 0
    chapters_found = 0

    if tome.cover:
        ext = _probe_page(tome.cover, session) if tome.cover.startswith(("http://", "https://")) else None
        cover_status = f"OK ({ext})" if ext else "unreachable"
        lines.append(f"  Cover: {cover_status}")

    for chapter in chapter_range:
        page = 1
        ch_pages = 0
        consecutive_fails = 0
        while page <= cfg.max_pages and consecutive_fails < 2:
            base_url = _build_url(cfg.template, chapter, page, cfg.manga)
            ext = None
            for candidate in _build_candidate_urls(base_url):
                ext = _probe_page(candidate, session)
                if ext is not None:
                    break
            if ext is not None:
                ch_pages += 1
                consecutive_fails = 0
            else:
                consecutive_fails += 1
            page += 1
            time.sleep(cfg.delay)

        if ch_pages > 0:
            chapters_found += 1
            total_found += ch_pages
            if cfg.verbose:
                lines.append(f"  [Chapter {chapter}] {ch_pages} page(s)")
        else:
            lines.append(f"  [Chapter {chapter}] Not found")

    lines.append(
        f"[{label}] Found {total_found} page(s) across "
        f"{chapters_found}/{len(chapter_range)} chapter(s)"
    )
    return TomeResult(tome=tome, pages=total_found, lines=lines)


def _pack_tome_cbz(
    cfg: ScraperConfig,
    tome: TomeConfig,
    tmp_path: Path,
    page_count: int,
    tome_padding: int,
) -> Path:
    """Package images from *tmp_path* into a tome CBZ file and return its path."""
    cfg.output.mkdir(parents=True, exist_ok=True)

    series_slug = cfg.series_name or cfg.manga or "tome"
    cbz_name = f"{series_slug} - Tome {tome.number:0{tome_padding}d}.cbz"
    cbz_path = cfg.output / cbz_name

    comicinfo = _make_tome_comicinfo_xml(cfg.series_name, tome, cfg.author, page_count)

    images = sorted_files(tmp_path.glob("*"))
    with zipfile.ZipFile(cbz_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ComicInfo.xml", comicinfo)
        for img in images:
            zf.write(img, img.name)

    return cbz_path


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------

def run_scraper(cfg: ScraperConfig) -> int:
    """
    Execute the full scraping job described by *cfg*.
    Returns the total number of pages downloaded (or found in dry-run).
    """
    cfg.output.mkdir(parents=True, exist_ok=True)

    # --- Tomes mode ---
    if cfg.tomes:
        return _run_tomes_mode(cfg)

    # --- Chapter mode ---
    if cfg.start is None:
        raise ScraperError(
            "A start chapter is required in chapter mode. "
            "Use --start or set 'start' in the config file."
        )

    if cfg.end is not None:
        chapters = list(range(cfg.start, cfg.end + 1))
        if cfg.max_chapters is not None:
            chapters = chapters[: cfg.max_chapters]
        return _run_finite(cfg, chapters)

    if cfg.max_chapters is not None and cfg.workers > 1:
        chapters = list(range(cfg.start, cfg.start + cfg.max_chapters))
        return _run_finite(cfg, chapters)

    return _run_open_ended(cfg)


def _run_tomes_mode(cfg: ScraperConfig) -> int:
    """Download and package all tomes defined in cfg.tomes."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    assert cfg.tomes is not None
    max_num = max(t.number for t in cfg.tomes)
    padding = max(3, len(str(max_num)))

    label = "found" if cfg.dry_run else "downloaded"
    total = 0

    print(f"Tomes mode: {len(cfg.tomes)} tome(s) to process.\n")

    if cfg.workers > 1:
        print(f"Using {cfg.workers} parallel workers.\n")
        with ThreadPoolExecutor(max_workers=cfg.workers) as executor:
            futures = {
                executor.submit(download_tome, cfg, t, padding): t
                for t in cfg.tomes
            }
            results: dict[int, TomeResult] = {}
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                results[result.tome.number] = result
                total += result.pages
                completed += 1
                print(
                    f"[{completed}/{len(cfg.tomes)}] Tome {result.tome.number}: "
                    f"{result.pages} page(s) {label}"
                )
        if cfg.verbose:
            for num in sorted(results):
                _emit_tome(results[num])
    else:
        for tome in cfg.tomes:
            result = download_tome(cfg, tome, padding)
            _emit_tome(result)
            total += result.pages

    return total


def _emit(result: ChapterResult) -> None:
    for line in result.lines:
        print(line)
    print()


def _emit_tome(result: TomeResult) -> None:
    for line in result.lines:
        print(line)
    print()


def _run_finite(cfg: ScraperConfig, chapters: list[int]) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    total = 0
    label = "found" if cfg.dry_run else "downloaded"

    if cfg.workers > 1:
        print(f"Using {cfg.workers} parallel workers.\n")
        with ThreadPoolExecutor(max_workers=cfg.workers) as executor:
            futures = {executor.submit(download_chapter, cfg, ch): ch for ch in chapters}
            results: dict[int, ChapterResult] = {}
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                results[result.chapter] = result
                total += result.pages
                completed += 1
                print(
                    f"[{completed}/{len(chapters)}] Chapter {result.chapter}: "
                    f"{result.pages} page(s) {label}"
                )
        if cfg.verbose:
            for ch in sorted(results):
                _emit(results[ch])
    else:
        for ch in chapters:
            result = download_chapter(cfg, ch)
            _emit(result)
            total += result.pages

    return total


def _run_open_ended(cfg: ScraperConfig) -> int:
    total = 0
    chapter = cfg.start
    processed = 0
    empty_streak = 0

    while empty_streak < cfg.stop_after_empty_chapters:
        if cfg.max_chapters is not None and processed >= cfg.max_chapters:
            print(
                f"Stopped after reaching max-chapters ({cfg.max_chapters}). "
                f"Last chapter checked: {chapter - 1}."
            )
            break
        result = download_chapter(cfg, chapter)
        _emit(result)
        total += result.pages
        processed += 1
        empty_streak = 0 if result.pages > 0 else empty_streak + 1
        chapter += 1

    if empty_streak >= cfg.stop_after_empty_chapters:
        print(
            f"Stopped after {empty_streak} consecutive empty chapters. "
            f"Last chapter checked: {chapter - 1}."
        )

    return total


