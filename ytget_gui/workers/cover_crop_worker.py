# File: ytget_gui/workers/cover_crop_worker.py
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Union
from PIL import Image
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from mutagen.oggopus import OggOpus
from PySide6.QtCore import QObject, Signal

from ytget_gui.styles import AppStyles

class CoverCropWorker(QObject):
    """Scans MP3 and FLAC files and crops embedded covers to 1:1 centered."""
    log = Signal(str, str)
    finished = Signal()

    def __init__(self, downloads_dir: Path):
        super().__init__()
        self.downloads_dir = downloads_dir

    @staticmethod
    def _is_temp_artifact(p: Path) -> bool:
        """Detect leftover ffmpeg/yt-dlp intermediate files like
        'Title.temp.opus'. These are produced (and normally cleaned up) as
        part of atomic postprocessing writes; if a previous run was
        interrupted or errored before cleanup, stale '.temp.<ext>' files can
        remain on disk. They aren't valid, complete audio files, so cropping
        should skip them instead of trying (and failing) to open them."""
        suffixes = [s.lower() for s in p.suffixes]
        return len(suffixes) >= 2 and suffixes[-2] == ".temp"

    def run(self):
        # collect .mp3 and .flac files regardless of case
        audio_files = [
            p for p in self.downloads_dir.rglob("*")
            if p.is_file()
            and p.suffix.lower() in (".mp3", ".flac", ".opus")
            and not self._is_temp_artifact(p)
        ]
        if not audio_files:
            self.log.emit("ℹ️ No MP3, FLAC, or Opus files found for cover cropping.\n", AppStyles.INFO_COLOR)
            self.finished.emit()
            return

        processed = 0
        changed = 0
        for file_path in audio_files:
            try:
                did_change = self._process_audio(file_path)
                processed += 1
                if did_change:
                    changed += 1
                    self.log.emit(f"🖼️ Cropped Cover to 1:1: {file_path.name}\n", AppStyles.SUCCESS_COLOR)
            except Exception as e:
                self.log.emit(f"⚠️ Skipped {file_path.name}: {e}\n", AppStyles.WARNING_COLOR)

        self.log.emit(f"✅ Cover Cropping Complete. Processed {processed}, Updated {changed} Files.\n", AppStyles.SUCCESS_COLOR)
        self.finished.emit()

    def _process_audio(self, file: Path) -> bool:
        if file.suffix.lower() == ".mp3":
            return self._crop_mp3_cover(file)
        elif file.suffix.lower() == ".flac":
            return self._crop_flac_cover(file)
        elif file.suffix.lower() == ".opus":
            return self._crop_opus_cover(file)
        return False

    def _crop_mp3_cover(self, file: Path) -> bool:
        try:
            tags = ID3(file)
        except ID3NoHeaderError:
            return False

        apics = tags.getall("APIC")
        if not apics:
            return False

        updated = False
        for apic in apics:
            try:
                img = Image.open(io.BytesIO(apic.data))
            except Exception:
                continue  # Not a valid image

            if img.width == img.height:
                continue
            img = self._ensure_rgb(img)
            cropped = self._crop_image_to_square(img)
            buf = io.BytesIO()
            cropped.save(buf, format="JPEG", quality=95, optimize=True)

            apic.mime = "image/jpeg"
            apic.data = buf.getvalue()
            updated = True

        if updated:
            tags.save(file)
        return updated

    def _crop_flac_cover(self, file: Path) -> bool:
        audio = FLAC(file)
        if not audio.pictures:
            return False

        updated = False
        pic = audio.pictures[0]

        try:
            img = Image.open(io.BytesIO(pic.data))
        except Exception:
            return False

        if img.width == img.height:
            return False
        img = self._ensure_rgb(img)
        cropped = self._crop_image_to_square(img)

        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=95, optimize=True)

        new_pic = Picture()
        new_pic.data = buf.getvalue()
        new_pic.type = pic.type
        new_pic.mime = "image/jpeg"
        new_pic.desc = pic.desc or "Cover"
        new_pic.width, new_pic.height = cropped.size
        new_pic.depth = 24

        audio.clear_pictures()
        audio.add_picture(new_pic)
        audio.save()
        return True

    def _crop_opus_cover(self, file: Path) -> bool:
        """Ogg Opus stores cover art as a base64-encoded FLAC Picture block
        under the 'metadata_block_picture' Vorbis comment field (there is no
        raw APIC/PICTURE frame like in MP3/FLAC)."""
        audio = OggOpus(file)
        raw_pics = audio.get("metadata_block_picture", [])
        if not raw_pics:
            return False

        try:
            pic = Picture(base64.b64decode(raw_pics[0]))
            img = Image.open(io.BytesIO(pic.data))
        except Exception:
            return False

        if img.width == img.height:
            return False
        img = self._ensure_rgb(img)
        cropped = self._crop_image_to_square(img)

        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=95, optimize=True)

        new_pic = Picture()
        new_pic.data = buf.getvalue()
        new_pic.type = pic.type
        new_pic.mime = "image/jpeg"
        new_pic.desc = pic.desc or "Cover"
        new_pic.width, new_pic.height = cropped.size
        new_pic.depth = 24

        audio["metadata_block_picture"] = [
            base64.b64encode(new_pic.write()).decode("ascii")
        ]
        audio.save()
        return True

    def _crop_image_to_square(self, img: Image.Image) -> Image.Image:
        side = min(img.width, img.height)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
        return img.crop((left, top, left + side, top + side))

    def _ensure_rgb(self, img: Image.Image) -> Image.Image:
        return img.convert("RGB") if img.mode not in ("RGB", "L") else img
