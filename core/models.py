from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageItem:
    source_path: Path
    filename: str
    file_type: str
    dimensions: str
    dpi: str
    thumb_path: Path | None = None
    preview_path: Path | None = None
    processed_preview_path: Path | None = None
    edited_preview_path: Path | None = None
    output_path: str = ""
    status: str = "pending"
    date_added: int = 0
    extra: dict = field(default_factory=dict)
