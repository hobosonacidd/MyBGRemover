from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"
}


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def scan_paths(paths, include_subfolders=False):
    found_files = []
    skipped_files = []

    for raw_path in paths:
        path = Path(raw_path)

        if path.is_file():
            if is_supported_image(path):
                found_files.append(path)
            else:
                skipped_files.append(path)

        elif path.is_dir():
            iterator = path.rglob("*") if include_subfolders else path.iterdir()
            for item in iterator:
                if item.is_file():
                    if is_supported_image(item):
                        found_files.append(item)
                    else:
                        skipped_files.append(item)

    return found_files, skipped_files
