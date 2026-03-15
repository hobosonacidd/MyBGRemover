from pathlib import Path
import time

from PySide6.QtCore import QObject, Signal, Slot

from utils.file_utils import scan_paths


class WatchFolderWorker(QObject):
    new_files_detected = Signal(list)
    status = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        folder_path: str,
        include_subfolders: bool = False,
        poll_interval_seconds: float = 2.0,
    ):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.include_subfolders = include_subfolders
        self.poll_interval_seconds = max(0.5, float(poll_interval_seconds))
        self._running = True
        self._known_files = set()

    def stop(self):
        self._running = False

    def _scan_once(self) -> set[str]:
        files, _skipped = scan_paths(
            [str(self.folder_path)],
            include_subfolders=self.include_subfolders,
        )
        return {str(Path(f).resolve()) for f in files}

    @Slot()
    def run(self):
        try:
            if not self.folder_path.exists() or not self.folder_path.is_dir():
                self.error.emit(f"Watch folder does not exist or is not a directory: {self.folder_path}")
                self.finished.emit()
                return

            self.status.emit(f"Watching folder: {self.folder_path}")
            self.status.emit(
                f"Include subfolders: {'yes' if self.include_subfolders else 'no'} | "
                f"Poll interval: {self.poll_interval_seconds:.1f}s"
            )

            self._known_files = self._scan_once()

            while self._running:
                current_files = self._scan_once()
                new_files = sorted(current_files - self._known_files)

                if new_files:
                    self.status.emit(f"Detected {len(new_files)} new file(s) in watch folder.")
                    self.new_files_detected.emit(new_files)

                self._known_files = current_files
                time.sleep(self.poll_interval_seconds)

            self.status.emit("Watch folder worker stopped.")
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit()
