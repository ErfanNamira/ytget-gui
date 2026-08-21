# File: ytget_gui/workers/cover_crop_worker.py
"""Crop embedded album art to a 1:1 square.

Handles MP3 (ID3 APIC), FLAC (PICTURE), Ogg Opus/Vorbis
(metadata_block_picture) and MP4/M4A (covr).
"""

from __future__ import annotations

import base64
import io
import logging
import threading
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from ytget_gui.styles import AppStyles

log = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = frozenset({".mp3", ".flac", ".opus", ".ogg", ".m4a", ".mp4"})

_JPEG_QUALITY = 95


class CoverCropWorker(QObject):
    log = Signal(str, str)
    progress = Signal(int, int)  # processed, total
    finished = Signal()

    def __init__(self, downloads_dir: Path, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.downloads_dir = Path(downloads_dir)
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Stop after the current file.

        The previous revision had no cancellation at all, so closing the app
        during a crop pass over a large library blocked shutdown until every
        file had been rewritten.
        """
        self._cancel.set()

    # ------------------------------------------------------------------

    @staticmethod
    def _is_temp_artifact(path: Path) -> bool:
        """Detect leftover ffmpeg intermediates like "Title.temp.opus".

        These are incomplete files from an interrupted postprocess; opening them
        fails, so they are skipped rather than reported as errors.
        """
        suffixes = [s.lower() for s in path.suffixes]
        return len(suffixes) >= 2 and suffixes[-2] == ".temp"

    def _collect(self) -> List[Path]:
        if not self.downloads_dir.is_dir():
            return []
        return sorted(
            p
            for p in self.downloads_dir.rglob("*")
            if p.is_file()
            and p.suffix.lower() in SUPPORTED_SUFFIXES
            and not self._is_temp_artifact(p)
        )

    def run(self) -> None:
        try:
            files = self._collect()
        except OSError as exc:
            self.log.emit(f"\u26a0\ufe0f Could not scan downloads: {exc}\n", AppStyles.WARNING_COLOR)
            self.finished.emit()
            return

        if not files:
            self.log.emit(
                "\u2139\ufe0f No audio files found for cover cropping.\n",
                AppStyles.INFO_COLOR,
            )
            self.finished.emit()
            return

        total = len(files)
        processed = 0
        changed = 0

        for path in files:
            if self._cancel.is_set():
                self.log.emit(
                    "\u23f9\ufe0f Cover cropping cancelled.\n", AppStyles.WARNING_COLOR
                )
                break
            try:
                if self._process(path):
                    changed += 1
                    self.log.emit(
                        f"\U0001f5bc\ufe0f Cropped cover to 1:1: {path.name}\n",
                        AppStyles.SUCCESS_COLOR,
                    )
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the pass
                log.debug("Cover crop failed for %s: %s", path, exc)
                self.log.emit(
                    f"\u26a0\ufe0f Skipped {path.name}: {exc}\n", AppStyles.WARNING_COLOR
                )
            processed += 1
            self.progress.emit(processed, total)

        self.log.emit(
            f"\u2705 Cover cropping complete. Processed {processed}, updated {changed}.\n",
            AppStyles.SUCCESS_COLOR,
        )
        self.finished.emit()

    # ------------------------------------------------------------------

    def _process(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            return self._crop_id3(path)
        if suffix == ".flac":
            return self._crop_flac(path)
        if suffix in (".opus", ".ogg"):
            return self._crop_ogg(path)
        if suffix in (".m4a", ".mp4"):
            return self._crop_mp4(path)
        return False

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _to_square_jpeg(data: bytes) -> Optional[bytes]:
        """Centre-crop image bytes to a square JPEG, or None if already square."""
        from PIL import Image

        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width == image.height:
                    return None
                side = min(image.width, image.height)
                left = (image.width - side) // 2
                top = (image.height - side) // 2
                cropped = image.crop((left, top, left + side, top + side))
                if cropped.mode not in ("RGB", "L"):
                    cropped = cropped.convert("RGB")
                buffer = io.BytesIO()
                cropped.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
                return buffer.getvalue()
        except Exception as exc:  # noqa: BLE001 - not every APIC holds a valid image
            log.debug("Not a croppable image: %s", exc)
            return None

    @staticmethod
    def _square_size(data: bytes) -> tuple[int, int]:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            return image.size

    # -- format handlers ----------------------------------------------

    def _crop_id3(self, path: Path) -> bool:
        from mutagen.id3 import ID3, ID3NoHeaderError

        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            return False

        frames = tags.getall("APIC")
        if not frames:
            return False

        updated = False
        for frame in frames:
            cropped = self._to_square_jpeg(frame.data)
            if cropped is None:
                continue
            frame.data = cropped
            frame.mime = "image/jpeg"
            updated = True

        if updated:
            tags.save(path)
        return updated

    def _crop_flac(self, path: Path) -> bool:
        from mutagen.flac import FLAC, Picture

        audio = FLAC(path)
        if not audio.pictures:
            return False

        rebuilt: List[Picture] = []
        updated = False

        # Every picture is processed, not just pictures[0]: a file can carry a
        # front cover plus a back cover or artist image, and the previous
        # revision cropped the first and silently discarded the rest by calling
        # clear_pictures() and adding only one back.
        for picture in audio.pictures:
            cropped = self._to_square_jpeg(picture.data)
            if cropped is None:
                rebuilt.append(picture)
                continue
            replacement = Picture()
            replacement.data = cropped
            replacement.type = picture.type
            replacement.mime = "image/jpeg"
            replacement.desc = picture.desc or "Cover"
            replacement.width, replacement.height = self._square_size(cropped)
            replacement.depth = 24
            rebuilt.append(replacement)
            updated = True

        if not updated:
            return False

        audio.clear_pictures()
        for picture in rebuilt:
            audio.add_picture(picture)
        audio.save()
        return True

    def _crop_ogg(self, path: Path) -> bool:
        """Ogg stores art as a base64 FLAC Picture block in a Vorbis comment."""
        from mutagen.flac import Picture
        from mutagen.oggopus import OggOpus
        from mutagen.oggvorbis import OggVorbis

        opener = OggOpus if path.suffix.lower() == ".opus" else OggVorbis
        audio = opener(path)
        encoded = audio.get("metadata_block_picture", [])
        if not encoded:
            return False

        rebuilt: List[str] = []
        updated = False

        for blob in encoded:
            try:
                picture = Picture(base64.b64decode(blob))
            except Exception as exc:  # noqa: BLE001
                log.debug("Unreadable picture block in %s: %s", path, exc)
                rebuilt.append(blob)
                continue

            cropped = self._to_square_jpeg(picture.data)
            if cropped is None:
                rebuilt.append(blob)
                continue

            replacement = Picture()
            replacement.data = cropped
            replacement.type = picture.type
            replacement.mime = "image/jpeg"
            replacement.desc = picture.desc or "Cover"
            replacement.width, replacement.height = self._square_size(cropped)
            replacement.depth = 24
            rebuilt.append(base64.b64encode(replacement.write()).decode("ascii"))
            updated = True

        if not updated:
            return False

        audio["metadata_block_picture"] = rebuilt
        audio.save()
        return True

    def _crop_mp4(self, path: Path) -> bool:
        """MP4/M4A support is new: yt-dlp produces .m4a for several audio
        selections, and those files were skipped entirely before."""
        from mutagen.mp4 import MP4, MP4Cover

        audio = MP4(path)
        covers = audio.tags.get("covr") if audio.tags else None
        if not covers:
            return False

        rebuilt: List[MP4Cover] = []
        updated = False

        for cover in covers:
            cropped = self._to_square_jpeg(bytes(cover))
            if cropped is None:
                rebuilt.append(cover)
                continue
            rebuilt.append(MP4Cover(cropped, imageformat=MP4Cover.FORMAT_JPEG))
            updated = True

        if not updated:
            return False

        audio.tags["covr"] = rebuilt
        audio.save()
        return True
