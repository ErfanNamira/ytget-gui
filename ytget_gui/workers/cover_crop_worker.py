# File: ytget_gui/workers/cover_crop_worker.py
from __future__ import annotations

import io
from pathlib import Path
from typing import Union
from PIL import Image
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from PySide6.QtCore import QObject, Signal

from ytget_gui.styles import AppStyles

class CoverCropWorker(QObject):
    """Scans MP3 and FLAC files and crops embedded covers to 1:1 centered."""
    log = Signal(str, str)
    finished = Signal()

    def __init__(self, downloads_dir: Path):
        super().__init__()
        self.downloads_dir = downloads_dir

    def run(self):
        audio_files = list(self.downloads_dir.rglob("*.mp3")) + list(self.downloads_dir.rglob("*.flac"))
        if not audio_files:
            self.log.emit("ℹ️ No MP3 or FLAC files found for cover cropping.\n", AppStyles.INFO_COLOR)
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
                    self.log.emit(f"🖼️ Cropped cover to 1:1: {file_path.name}\n", AppStyles.SUCCESS_COLOR)
            except Exception as e:
                self.log.emit(f"⚠️ Skipped {file_path.name}: {e}\n", AppStyles.WARNING_COLOR)

        self.log.emit(f"✅ Cover cropping complete. Processed {processed}, updated {changed} files.\n", AppStyles.SUCCESS_COLOR)
        self.finished.emit()

    def _process_audio(self, file: Path) -> bool:
        if file.suffix.lower() == ".mp3":
            return self._crop_mp3_cover(file)
        elif file.suffix.lower() == ".flac":
            return self._crop_flac_cover(file)
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

    def _crop_image_to_square(self, img: Image.Image) -> Image.Image:
        side = min(img.width, img.height)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
        return img.crop((left, top, left + side, top + side))

    def _ensure_rgb(self, img: Image.Image) -> Image.Image:
        return img.convert("RGB") if img.mode not in ("RGB", "L") else img
