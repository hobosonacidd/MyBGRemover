import sys
from pathlib import Path
import traceback

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


class TeeStream:
    def __init__(self, original_stream, file_path: Path):
        self.original_stream = original_stream
        self.file_path = file_path

    def write(self, data):
        try:
            self.original_stream.write(data)
        except Exception:
            pass

        try:
            with self.file_path.open("a", encoding="utf-8") as f:
                f.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            self.original_stream.flush()
        except Exception:
            pass


def main():
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    terminal_log_path = logs_dir / "terminal_log.txt"

    sys.stdout = TeeStream(sys.stdout, terminal_log_path)
    sys.stderr = TeeStream(sys.stderr, terminal_log_path)

    def handle_exception(exc_type, exc_value, exc_traceback):
        traceback.print_exception(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception

    app = QApplication(sys.argv)
    app.setApplicationName("MyBGRemover")
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
