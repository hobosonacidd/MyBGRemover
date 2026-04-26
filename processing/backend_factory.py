from __future__ import annotations

from processing.rembg_engine import RembgEngine
from processing.inspyrenet_engine import InSPyReNetEngine
from processing.modnet_engine import ModNetEngine


def create_background_engine(backend_name: str, backend_options: dict | None = None):
    normalized = (backend_name or "").strip()
    backend_options = backend_options or {}

    if not normalized or normalized == "rembg":
        return RembgEngine(
            alpha_matting=bool(backend_options.get("alpha_matting", False)),
            alpha_matting_foreground_threshold=int(backend_options.get("alpha_matting_foreground_threshold", 240)),
            alpha_matting_background_threshold=int(backend_options.get("alpha_matting_background_threshold", 10)),
            alpha_matting_erode_size=int(backend_options.get("alpha_matting_erode_size", 10)),
            post_process_mask=bool(backend_options.get("post_process_mask", False)),
        )

    if normalized == "InSPyReNet":
        return InSPyReNetEngine(
            mode=str(backend_options.get("mode", "fast")).strip() or "fast",
            resize=str(backend_options.get("resize", "static")).strip() or "static",
            threshold=float(backend_options.get("threshold", 0.5)),
        )

    if normalized == "MODNet":
        return ModNetEngine(
            matte_threshold=float(backend_options.get("matte_threshold", 0.10)),
            edge_feather=float(backend_options.get("edge_feather", 0.0)),
        )

    raise ValueError(f"Unsupported backend '{backend_name}'")
