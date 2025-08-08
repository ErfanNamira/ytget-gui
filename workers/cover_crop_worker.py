# File: ytget/workers/cover_crop_worker.py
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from mutagen.id3 import ID3, ID3NoHeaderError
from PySide6.QtCore import QObject, Signal

from ytget.styles import AppStyles

class CoverCropWorker(QObject):
    """Scans MP3 files and crops embedded covers to 1:1 centered."""
    log = Signal(str, str)
    finished = Signal()

    def __init__(self, downloads_dir: Path):
        super().__init__()
        self.downloads_dir = downloads_dir

    def run(self):
        processed = 0
        changed = 0
        try:
            mp3_files = list(self.downloads_dir.rglob("*.mp3"))
            if not mp3_files:
                self.log.emit("ℹ️ No MP3 files found for cover cropping.\n", AppStyles.INFO_COLOR)
                self.finished.emit()
                return

            for file_path in mp3_files:
                try:
                    did_change = self._crop_mp3_cover(file_path)
                    processed += 1
                    if did_change:
                        changed += 1
                        self.log.emit(f"🖼️ Cropped cover to 1:1: {file_path.name}\n", AppStyles.SUCCESS_COLOR)
                except Exception as e:
                    self.log.emit(f"⚠️ Skipped {file_path.name}: {e}\n", AppStyles.WARNING_COLOR)

            self.log.emit(f"✅ Cover cropping complete. Processed {processed}, updated {changed} files.\n", AppStyles.SUCCESS_COLOR)
        finally:
            self.finished.emit()

    def _crop_mp3_cover(self, file: Path) -> bool:
        # Load ID3 tags; if no tags, or no covers, skip.
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

            # If already square, skip this APIC
            if img.width == img.height:
                continue

            # Ensure we can encode to JPEG correctly
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            side = min(img.width, img.height)
            left = (img.width - side) // 2
            top = (img.height - side) // 2
            cropped = img.crop((left, top, left + side, top + side))

            buf = io.BytesIO()
            cropped.save(buf, format="JPEG", quality=95, optimize=True)
            apic.mime = "image/jpeg"
            apic.data = buf.getvalue()
            updated = True

        if updated:
            tags.save(file)
        return updated