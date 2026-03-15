from io import BytesIO
from pathlib import Path

from PIL import Image
from rembg import remove, new_session


class RembgEngine:
    def __init__(self):
        self._sessions = {}

    def get_session(self, model_name: str):
        if model_name not in self._sessions:
            self._sessions[model_name] = new_session(model_name)
        return self._sessions[model_name]

    def _run_remove(
        self,
        input_path: Path,
        output_path: Path,
        model_name: str,
        max_size=None,
    ):
        try:
            input_path = Path(input_path)
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            session = self.get_session(model_name)

            with Image.open(input_path) as img:
                img = img.convert("RGBA")

                if max_size is not None:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)

                input_buffer = BytesIO()
                img.save(input_buffer, format="PNG")
                input_bytes = input_buffer.getvalue()

            output_bytes = remove(input_bytes, session=session)

            result = Image.open(BytesIO(output_bytes)).convert("RGBA")
            result.save(output_path, format="PNG")

            if not output_path.exists():
                return False, f"Processed file was not created: {output_path}"

            return True, None

        except Exception as e:
            return False, str(e)

    def remove_background_preview(
        self,
        input_path: Path,
        output_path: Path,
        model_name: str = "u2netp",
        max_size=(1200, 1200),
    ):
        return self._run_remove(
            input_path=input_path,
            output_path=output_path,
            model_name=model_name,
            max_size=max_size,
        )

    def remove_background_fullres(
        self,
        input_path: Path,
        output_path: Path,
        model_name: str = "u2netp",
    ):
        return self._run_remove(
            input_path=input_path,
            output_path=output_path,
            model_name=model_name,
            max_size=None,
        )
