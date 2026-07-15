from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from processing.backend_factory import create_background_engine
from processing.color_removal import remove_color_from_file


class ProcessWorker(QObject):
    finished = Signal(int, str)
    error = Signal(int, str)
    status = Signal(str)

    def __init__(
        self,
        item_index: int,
        input_path: Path,
        output_path: Path,
        model_name: str,
        backend_name: str = "rembg",
        backend_options: dict | None = None,
        removal_mode: str = "AI Removal",
    ):
        super().__init__()
        self.item_index = item_index
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.model_name = model_name
        self.backend_name = backend_name
        self.backend_options = backend_options or {}
        self.removal_mode = removal_mode

    @Slot()
    def run(self):
        try:
            self.status.emit(f"Worker started for item index {self.item_index}")
            self.status.emit(f"Removal mode: {self.removal_mode}")
            self.status.emit(f"Backend: {self.backend_name}")
            self.status.emit(f"Model: {self.model_name}")
            self.status.emit(f"Backend options: {self.backend_options}")

            if self.removal_mode == "Color Removal":
                ok, error_message = remove_color_from_file(
                    input_path=self.input_path,
                    output_path=self.output_path,
                    target_color=self.backend_options.get("target_color", (255, 255, 255)),
                    threshold=self.backend_options.get("threshold", 30),
                    match_mode=self.backend_options.get("match_mode", "Connected Edges"),
                    feather=self.backend_options.get("feather", 0),
                    reduce_spill=self.backend_options.get("reduce_spill", False),
                    spill_reduction=self.backend_options.get("spill_reduction", 20 if self.backend_options.get("reduce_spill", False) else 0),
                    protect_dark_colors=self.backend_options.get("protect_dark_colors", True),
                )
            else:
                engine = create_background_engine(self.backend_name, self.backend_options)

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
