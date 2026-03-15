from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from processing.rembg_engine import RembgEngine


class ProcessWorker(QObject):
    finished = Signal(int, str)
    error = Signal(int, str)
    status = Signal(str)

    def __init__(self, item_index: int, input_path: Path, output_path: Path, model_name: str):
        super().__init__()
        self.item_index = item_index
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.model_name = model_name

    @Slot()
    def run(self):
        try:
            self.status.emit(f"Worker started for item index {self.item_index}")
            self.status.emit(f"Loading model: {self.model_name}")

            engine = RembgEngine()

            ok, error_message = engine.remove_background_preview(
                input_path=self.input_path,
                output_path=self.output_path,
                model_name=self.model_name,
            )

            if ok:
                self.status.emit(f"Worker finished successfully: {self.output_path}")
                self.finished.emit(self.item_index, str(self.output_path))
            else:
                self.error.emit(
                    self.item_index,
                    error_message or "Unknown processing error.",
                )

        except Exception as e:
            self.error.emit(self.item_index, str(e))
