from pathlib import Path
from PIL import Image


THUMBNAIL_SIZE = (160, 160)
PREVIEW_MAX_SIZE = (900, 700)


def get_image_metadata(path):
    try:
        with Image.open(path) as img:
            width, height = img.size
            dpi = img.info.get("dpi", None)

            if dpi and isinstance(dpi, tuple):
                dpi_text = f"{int(dpi[0])}x{int(dpi[1])}"
            else:
                dpi_text = "Unknown"

            return {
                "dimensions": f"{width}x{height}",
                "dpi": dpi_text,
            }
    except Exception:
        return {
            "dimensions": "Unknown",
            "dpi": "Unknown",
        }


def create_thumbnail(source_path: Path, thumb_path: Path, size=THUMBNAIL_SIZE) -> bool:
    try:
        thumb_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source_path) as img:
            img = img.convert("RGBA")
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumb_path, format="PNG")

        return True
    except Exception:
        return False


def create_preview_image(source_path: Path, preview_path: Path, max_size=PREVIEW_MAX_SIZE) -> bool:
    try:
        preview_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source_path) as img:
            img = img.convert("RGBA")
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(preview_path, format="PNG")

        return True
    except Exception:
        return False
