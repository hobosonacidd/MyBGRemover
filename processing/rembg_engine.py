from __future__ import annotations

from io import BytesIO
from pathlib import Path
import gc

from PIL import Image, UnidentifiedImageError
from rembg import remove, new_session


class RembgEngine:
    """
    Background remover wrapper around rembg.

    This version is adjusted for stability on lower-memory hardware.
    """

    SUPPORTED_MODELS = {
        "u2net",
        "u2netp",
        "u2net_human_seg",
        "u2net_cloth_seg",
        "silueta",
        "isnet-general-use",
        "isnet-anime",
        "birefnet-dis",
        "birefnet-hrsod",
        "birefnet-cod",
    }

    DISABLED_MODELS = {
        "birefnet-cod",
    }

    MODEL_ALIASES = {
        "bria_rmbg": "bria-rmbg",
        "bria-rmbg-2.0": "bria-rmbg",
        "isnet_general_use": "isnet-general-use",
        "u2net-human-seg": "u2net_human_seg",
        "birefnet_general": "birefnet-general",
        "birefnet_general_lite": "birefnet-general-lite",
        "birefnet_portrait": "birefnet-portrait",
        "birefnet_dis": "birefnet-dis",
        "birefnet_hrsod": "birefnet-hrsod",
        "birefnet_cod": "birefnet-cod",
    }

    HEAVY_MODELS = {
        "birefnet-dis",
        "birefnet-hrsod",
        "birefnet-cod",
    }

    def __init__(
        self,
        alpha_matting: bool = False,
        alpha_matting_foreground_threshold: int = 240,
        alpha_matting_background_threshold: int = 10,
        alpha_matting_erode_size: int = 10,
        post_process_mask: bool = False,
    ):
        self._sessions: dict[str, object] = {}
        self.alpha_matting = bool(alpha_matting)
        self.alpha_matting_foreground_threshold = int(alpha_matting_foreground_threshold)
        self.alpha_matting_background_threshold = int(alpha_matting_background_threshold)
        self.alpha_matting_erode_size = int(alpha_matting_erode_size)
        self.post_process_mask = bool(post_process_mask)

    def available_models(self) -> list[str]:
        return sorted(self.SUPPORTED_MODELS)

    def _normalize_model_name(self, model_name: str) -> str:
        normalized = (model_name or "").strip()
        if not normalized:
            return "u2netp"

        return self.MODEL_ALIASES.get(normalized, normalized)

    def _validate_model_name(self, model_name: str) -> str:
        normalized = self._normalize_model_name(model_name)

        if normalized not in self.SUPPORTED_MODELS:
            supported = ", ".join(sorted(self.SUPPORTED_MODELS))
            raise ValueError(
                f"Unsupported model '{model_name}'. Supported models: {supported}"
            )

        if normalized in self.DISABLED_MODELS:
            raise ValueError(
                f"Model '{normalized}' is currently disabled on this machine because it is unstable and can crash the app."
            )

        return normalized

    def _is_heavy_model(self, model_name: str) -> bool:
        return model_name in self.HEAVY_MODELS

    def _clear_cached_sessions(self):
        self._sessions.clear()
        gc.collect()

    def _build_session(self, model_name: str):
        if self._is_heavy_model(model_name):
            self._clear_cached_sessions()
        return new_session(model_name)

    def get_session(self, model_name: str):
        model_name = self._validate_model_name(model_name)

        if self._is_heavy_model(model_name):
            return self._build_session(model_name)

        if model_name not in self._sessions:
            self._sessions[model_name] = self._build_session(model_name)

        return self._sessions[model_name]

    def _read_image_bytes(self, input_path: Path, max_size=None) -> bytes:
        with Image.open(input_path) as img:
            img = img.convert("RGBA")

            if max_size is not None:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

            input_buffer = BytesIO()
            img.save(input_buffer, format="PNG")
            return input_buffer.getvalue()

    def _save_result_bytes(self, output_bytes: bytes, output_path: Path):
        with Image.open(BytesIO(output_bytes)) as result:
            result = result.convert("RGBA")
            result.save(output_path, format="PNG")

    def _recommended_preview_size(self, model_name: str, max_size):
        if max_size is None:
            return None

        if self._is_heavy_model(model_name):
            return (768, 768)

        return max_size

    def _run_remove_once(
        self,
        input_path: Path,
        output_path: Path,
        model_name: str,
        max_size=None,
    ):
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model_name = self._validate_model_name(model_name)
        session = self.get_session(model_name)

        input_bytes = self._read_image_bytes(
            input_path=input_path,
            max_size=self._recommended_preview_size(model_name, max_size),
        )

        output_bytes = remove(
            input_bytes,
            session=session,
            alpha_matting=self.alpha_matting,
            alpha_matting_foreground_threshold=self.alpha_matting_foreground_threshold,
            alpha_matting_background_threshold=self.alpha_matting_background_threshold,
            alpha_matting_erode_size=self.alpha_matting_erode_size,
            post_process_mask=self.post_process_mask,
        )
        self._save_result_bytes(output_bytes, output_path)

        if not output_path.exists():
            return False, f"Processed file was not created: {output_path}"

        return True, None

    def _run_remove(
        self,
        input_path: Path,
        output_path: Path,
        model_name: str,
        max_size=None,
    ):
        normalized_model = self._normalize_model_name(model_name)

        try:
            return self._run_remove_once(
                input_path=input_path,
                output_path=output_path,
                model_name=normalized_model,
                max_size=max_size,
            )

        except FileNotFoundError:
            return False, f"Input file not found: {input_path}"

        except UnidentifiedImageError:
            return False, f"Could not read image file: {input_path}"

        except ValueError as e:
            return False, str(e)

        except Exception as first_error:
            if self._is_heavy_model(normalized_model):
                try:
                    self._clear_cached_sessions()
                    return self._run_remove_once(
                        input_path=input_path,
                        output_path=output_path,
                        model_name=normalized_model,
                        max_size=max_size,
                    )
                except Exception as retry_error:
                    return (
                        False,
                        f"Model '{normalized_model}' failed twice. "
                        f"First error: {first_error} | Retry error: {retry_error}"
                    )

            return False, str(first_error)

        finally:
            if self._is_heavy_model(normalized_model):
                self._clear_cached_sessions()

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
