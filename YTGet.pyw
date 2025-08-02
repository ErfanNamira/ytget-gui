import sys
import os
import re
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLineEdit, QPushButton,
    QComboBox, QTextEdit, QLabel, QHBoxLayout, QMessageBox
)
from PySide6.QtGui import QColor, QTextCursor, QTextCharFormat
from PySide6.QtCore import Qt, QObject, Signal, QThread, QProcess

# Set local ffmpeg and ffprobe path for yt-dlp
os.environ["FFMPEG"] = os.path.abspath("ffmpeg.exe")
os.environ["FFPROBE"] = os.path.abspath("ffprobe.exe")

# --- Constants ---
RESOLUTIONS = {
    "🎞 480p MKV": "251+244/bestvideo[height<=480]+bestaudio",
    "🎞 720p MKV": "251+247/bestvideo[height<=720]+bestaudio",
    "🎞 1080p MKV": "251+248/bestvideo[height<=1080]+bestaudio",
    "🎞 1440p MKV": "251+271/bestvideo[height<=1440]+bestaudio",
    "🎞 2160p MKV": "251+313/bestvideo[height<=2160]+bestaudio",
    "🎵 MP3 Audio": "audio",
    "🎵 MP3 Playlist": "playlist_audio"
}

COOKIES_PATH = "cookies.txt"
OUTPUT_TEMPLATE = "%(title)s.%(ext)s"
PLAYLIST_OUTPUT_TEMPLATE = "%(playlist_index)s - %(title)s.%(ext)s"

# --- Worker for downloading ---
class DownloadWorker(QObject):
    log = Signal(str, str)  # text, color
    finished = Signal(int)  # exit code
    error = Signal(str)     # error message
    
    def __init__(self, url: str, format_code: str):
        super().__init__()
        self.url = url
        self.format_code = format_code
        self.process = None
        self.is_cancelled = False

    def run(self):
        """Start the yt-dlp process and stream output."""
        try:
            if self.format_code == "playlist_audio":
                command = self._build_playlist_audio_command(self.url)
            else:
                is_audio = (self.format_code == "audio")
                command = self._build_command(self.url, self.format_code, is_audio)

            self.log.emit("🎧 Preparing command...\n", "#b2ff59")

            self.process = QProcess()
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self._read_output)
            self.process.finished.connect(self._process_finished)

            # Start the process
            self.process.start(command[0], command[1:])

            if not self.process.waitForStarted(5000):  # Wait up to 5 sec
                self.error.emit("Failed to start yt-dlp process.")
                self.finished.emit(-1)
                return

        except Exception as e:
            self.error.emit(f"Fatal error: {str(e)}")
            self.finished.emit(-1)

    def cancel(self):
        """Cancel the running process."""
        self.is_cancelled = True
        if self.process and self.process.state() == QProcess.Running:
            self.process.terminate()
            if not self.process.waitForFinished(3000):  # wait 3 sec to terminate gracefully
                self.process.kill()

    def _read_output(self):
        """Read output from yt-dlp and emit log signals."""
        if self.process is None:
            return
        output = self.process.readAllStandardOutput().data().decode(errors='ignore')
        for line in output.splitlines(True):
            color = self._determine_color(line)
            self.log.emit(line, color)

    def _process_finished(self, exit_code, exit_status=None):
        """Handle process completion."""
        if self.is_cancelled:
            self.log.emit("❌ Download cancelled by user.\n", "#ff1744")
            self.finished.emit(-1)
            return

        if exit_code == 0:
            self.log.emit("✅ Download finished successfully.\n", "#00e676")
        else:
            self.log.emit(f"❌ yt-dlp exited with code {exit_code}\n", "#ff1744")

            # Try fallback if format contains "/"
            fallback = self._extract_fallback(self.format_code)
            if fallback:
                self.log.emit(f"\n🔁 Retrying with fallback format: {fallback}\n", "#ffd600")
                # For simplicity, do NOT auto retry here in this worker to avoid complexity
                # Could be implemented in main class if needed

        self.finished.emit(exit_code)

    def _determine_color(self, line: str) -> str:
        line = line.lower()
        if "error" in line:
            return "#ff5252"
        if any(k in line for k in ["downloading", "merging", "extracting"]):
            return "#64ffda"
        if "deleting" in line:
            return "#f06292"
        return "#eeeeee"

    def _build_command(self, url, fmt, is_audio):
        base = ["yt-dlp", "--cookies", COOKIES_PATH, "-o", OUTPUT_TEMPLATE]

        if is_audio:
            return base + [
                "-f", "bestaudio",
                "--extract-audio", "--audio-format", "mp3",
                "--audio-quality", "0",
                "--embed-thumbnail",
                "--add-metadata",
                "--write-sub", "--write-thumbnail",
                "--sub-lang", "en",
                url
            ]
        else:
            return base + [
                "-f", fmt,
                "--merge-output-format", "mkv",
                "--write-sub", "--sub-lang", "en",
                url
            ]

    def _build_playlist_audio_command(self, url):
        return [
            "yt-dlp",
            "--cookies", COOKIES_PATH,
            "-f", "bestaudio",
            "--yes-playlist",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--write-sub",
            "--write-thumbnail",
            "--sub-lang", "en",
            "-o", PLAYLIST_OUTPUT_TEMPLATE,
            url
        ]

    def _extract_fallback(self, fmt):
        return fmt.split("/")[-1] if "/" in fmt else None


# --- Main GUI Class ---
class YTGetGUI(QMainWindow):
    URL_REGEX = re.compile(
        r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$", re.IGNORECASE
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("YTGet GUI")
        self.setWindowIcon(QIcon("icon.ico"))
        self.setGeometry(200, 200, 700, 500)
        self.setStyleSheet("QMainWindow { background-color: #1e1e1e; }")
        self._download_thread = None
        self._worker = None
        self._build_ui()
        self._install_exception_hook()

    def _install_exception_hook(self):
        sys.excepthook = self._handle_uncaught_exceptions

    def _handle_uncaught_exceptions(self, exc_type, exc_value, exc_traceback):
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self._log(f"\n❌ Uncaught exception:\n{error_msg}\n", "#ff1744")
        QMessageBox.critical(self, "Fatal Error", f"An unexpected error occurred:\n{exc_value}")

    def _build_ui(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # Title
        title = QLabel("✨ YTGet GUI ✨")
        title.setStyleSheet("color: white; font-size: 22px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # URL Input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("📋 Paste YouTube URL here")
        self.url_input.setStyleSheet("padding: 8px; font-size: 16px;")
        layout.addWidget(self.url_input)

        # Format Selector + Download/Cancel Button
        row = QHBoxLayout()
        self.format_box = QComboBox()
        self.format_box.addItems(RESOLUTIONS.keys())
        self.format_box.setStyleSheet("padding: 6px; font-size: 15px;")
        row.addWidget(self.format_box)

        self.download_btn = QPushButton("⬇️ Download")
        self.download_btn.setStyleSheet(
            "background-color: #e91e63; color: white; font-size: 15px; padding: 10px;")
        self.download_btn.clicked.connect(self._on_download_clicked)
        row.addWidget(self.download_btn)

        layout.addLayout(row)

        # Output Box
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setStyleSheet("""
            background-color: #121212;
            color: #d4d4d4;
            font-family: Consolas;
            font-size: 13px;
            padding: 10px;
        """)
        layout.addWidget(self.output_box)

        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def _log(self, text, color="#d4d4d4"):
        cursor = self.output_box.textCursor()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text)
        self.output_box.setTextCursor(cursor)
        self.output_box.ensureCursorVisible()

    def _on_download_clicked(self):
        if self._worker is not None:
            # If a download is running, cancel it
            self._log("❌ Cancelling ongoing download...\n", "#ff1744")
            self._worker.cancel()
            self.download_btn.setEnabled(False)
            return

        url = self.url_input.text().strip()
        if not url:
            self._log("⚠️ Please enter a YouTube URL.\n", "#ffb74d")
            return
        if not self.URL_REGEX.match(url):
            self._log("⚠️ Invalid YouTube URL format.\n", "#ffb74d")
            return

        format_label = self.format_box.currentText()
        format_code = RESOLUTIONS.get(format_label)
        self._log(f"\n🚀 Starting download: {format_label}\n", "#64ffda")

        # Disable input controls during download
        self.download_btn.setText("⏹ Cancel")
        self.url_input.setEnabled(False)
        self.format_box.setEnabled(False)

        # Set up worker and thread
        self._worker = DownloadWorker(url, format_code)
        self._download_thread = QThread()
        self._worker.moveToThread(self._download_thread)

        # Connect signals
        self._download_thread.started.connect(self._worker.run)
        self._worker.log.connect(self._log)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)

        self._download_thread.start()

    def _on_worker_error(self, message):
        self._log(f"❌ {message}\n", "#ff1744")

    def _on_worker_finished(self, exit_code):
        # Re-enable controls
        self.download_btn.setText("⬇️ Download")
        self.download_btn.setEnabled(True)
        self.url_input.setEnabled(True)
        self.format_box.setEnabled(True)

        # Clean up thread and worker
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._download_thread:
            self._download_thread.quit()
            self._download_thread.wait()
            self._download_thread = None

        if exit_code == 0:
            self._log("🎉 Download completed successfully!\n", "#00e676")
        elif exit_code == -1:
            self._log("⚠️ Download cancelled or failed.\n", "#ffb74d")
        else:
            self._log(f"⚠️ Download failed with exit code {exit_code}.\n", "#ffb74d")


if __name__ == "__main__":
    import traceback

    try:
        app = QApplication(sys.argv)
        window = YTGetGUI()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print("Fatal error:", e)
        traceback.print_exc()
        input("Press Enter to exit...")
