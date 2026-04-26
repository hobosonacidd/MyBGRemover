from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError


class InSPyReNetEngine:
    """
    Background remover wrapper around the transparent-background package
    (InSPyReNet backend).

    This is intentionally separate from rembg so the app can support
    multiple backends cleanly.
    """

    def __init__(
        self,
        mode: str = "fast",
        resize: str = "static",
        threshold: float = 0.5,
    ):
        self.mode = mode
        self.resize = resize
        self.threshold = threshold
        self._remover = None

    def _get_remover(self):
        if self._remover is not None:
            return self._remover

        try:
            from transparent_background import Remover
        except ImportError as e:
            raise RuntimeError(
                "The InSPyReNet backend requires the Python package "
                "'transparent-background', but it is not installed in this environment."
            ) from e

        self._remover = Remover(
            mode=self.mode,
            resize=self.resize,
            device="cpu",
        )
        return self._remover

    def _read_input_image(self, input_path: Path, max_size=None) -> Image.Image:
        with Image.open(input_path) as img:
            img = img.convert("RGB")

            if max_size is not None:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

        return Image.open(buffer).convert("RGB")

    def _save_result_image(self, result_image: Image.Image, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_image = result_image.convert("RGBA")
        result_image.save(output_path, format="PNG")

    def _run_remove(
        self,
        input_path: Path,
        output_path: Path,
        max_size=None,
    ):
        try:
            input_path = Path(input_path)
            output_path = Path(output_path)

            if not input_path.exists():
                return False, f"Input file not found: {input_path}"

            remover = self._get_remover()
            img = self._read_input_image(input_path, max_size=max_size)

            result = remover.process(
                img,
                type="rgba",
                threshold=float(self.threshold),
            )
            self._save_result_image(result, output_path)

            if not output_path.exists():
                return False, f"Processed file was not created: {output_path}"

            return True, None

        except FileNotFoundError:
            return False, f"Input file not found: {input_path}"

        except UnidentifiedImageError:
            return False, f"Could not read image file: {input_path}"

        except Exception as e:
            return False, str(e)

    def remove_background_preview(
        self,
        input_path: Path,
        output_path: Path,
        model_name: str = "",
        max_size=(1200, 1200),
    ):
        return self._run_remove(
            input_path=input_path,
            output_path=output_path,
            max_size=max_size,
        )

    def remove_background_fullres(
        self,
        input_path: Path,
        output_path: Path,
        model_name: str = "",
    ):
        return self._run_remove(
            input_path=input_path,
            output_path=output_path,
            max_size=None,
        )
