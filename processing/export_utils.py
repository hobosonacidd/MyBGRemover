from pathlib import Path
from PIL import Image
import zipfile


FORMAT_MAP = {
    "PNG": ".png",
    "JPG": ".jpg",
    "WEBP": ".webp",
}


BACKGROUND_COLOR_MAP = {
    "White": (255, 255, 255),
    "Black": (0, 0, 0),
}


MAX_FILENAME_LENGTH = 180


def sanitize_output_stem(stem: str) -> str:
    bad_chars = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad_chars else ch for ch in stem)

    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip().rstrip(".")
    cleaned = cleaned.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    return cleaned or "export"


def _truncate_base_name(base_name: str, extension: str, counter_suffix: str = "") -> str:
    max_base_length = MAX_FILENAME_LENGTH - len(extension) - len(counter_suffix)

    if max_base_length < 1:
        max_base_length = 1

    if len(base_name) <= max_base_length:
        return base_name

    trimmed = base_name[:max_base_length].rstrip(" ._-")
    return trimmed or "export"


def build_output_path(
    source_path: Path,
    output_dir: Path,
    suffix: str,
    output_format: str,
    overwrite_existing: bool = False,
) -> Path:
    extension = FORMAT_MAP.get(output_format.upper(), ".png")
    safe_stem = sanitize_output_stem(source_path.stem)
    safe_suffix = sanitize_output_stem(suffix).replace(" ", "_")

    if safe_suffix and not safe_suffix.startswith("_"):
        safe_suffix = f"_{safe_suffix}"

    base_name = f"{safe_stem}{safe_suffix}"
    base_name = _truncate_base_name(base_name, extension)

    candidate = output_dir / f"{base_name}{extension}"

    if overwrite_existing:
        return candidate

    counter = 1
    while candidate.exists():
        counter_suffix = f"_{counter}"
        numbered_base_name = _truncate_base_name(base_name, extension, counter_suffix=counter_suffix)
        candidate = output_dir / f"{numbered_base_name}{counter_suffix}{extension}"
        counter += 1

    return candidate


def prepare_base_export_image(
    source_path: Path,
    destination_path: Path,
) -> tuple[bool, str | None]:
    try:
        source_path = Path(source_path)
        destination_path = Path(destination_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source_path) as img:
            img = img.convert("RGBA")
            img.save(destination_path, format="PNG")

        if not destination_path.exists():
            return False, f"Base export image was not created: {destination_path}"

        return True, None

    except Exception as e:
        return False, str(e)


def export_processed_image(
    processed_image_path: Path,
    output_path: Path,
    output_format: str,
    background_mode: str,
    background_color_name: str,
) -> tuple[bool, str | None]:
    try:
        processed_image_path = Path(processed_image_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(processed_image_path) as img:
            img = img.convert("RGBA")

            fmt = output_format.upper()

            if fmt == "PNG":
                if background_mode == "Transparent":
                    img.save(output_path, format="PNG")
                else:
                    bg_color = BACKGROUND_COLOR_MAP.get(background_color_name, (255, 255, 255))
                    background = Image.new("RGBA", img.size, bg_color + (255,))
                    composited = Image.alpha_composite(background, img).convert("RGB")
                    composited.save(output_path, format="PNG")

            elif fmt == "JPG":
                bg_color = BACKGROUND_COLOR_MAP.get(background_color_name, (255, 255, 255))
                background = Image.new("RGBA", img.size, bg_color + (255,))
                composited = Image.alpha_composite(background, img).convert("RGB")
                composited.save(output_path, format="JPEG", quality=95)

            elif fmt == "WEBP":
                if background_mode == "Transparent":
                    img.save(output_path, format="WEBP", quality=95)
                else:
                    bg_color = BACKGROUND_COLOR_MAP.get(background_color_name, (255, 255, 255))
                    background = Image.new("RGBA", img.size, bg_color + (255,))
                    composited = Image.alpha_composite(background, img).convert("RGB")
                    composited.save(output_path, format="WEBP", quality=95)

            else:
                return False, f"Unsupported output format: {output_format}"

        if not output_path.exists():
            return False, f"Output file was not created: {output_path}"

        return True, None

    except Exception as e:
        return False, str(e)


def create_batch_zip(
    output_paths: list[str],
    output_dir: Path,
) -> tuple[bool, str | None, str | None]:
    try:
        if not output_paths:
            return False, None, "No files available for ZIP export."

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        zip_path = output_dir / "batch_export.zip"
        counter = 1

        while zip_path.exists():
            zip_path = output_dir / f"batch_export_{counter}.zip"
            counter += 1

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            for file_path in output_paths:
                p = Path(file_path)
                if p.exists() and p.is_file():
                    zipf.write(p, arcname=p.name)

        if not zip_path.exists():
            return False, None, "ZIP file was not created."

        return True, str(zip_path), None

    except Exception as e:
        return False, None, str(e)
