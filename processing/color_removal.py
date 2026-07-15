from __future__ import annotations

from collections import deque
from configparser import ConfigParser
from pathlib import Path
from typing import Any
import traceback

import numpy as np
from PIL import Image, ImageFilter


DEBUG_LOG = Path.home() / "MyBGRemover" / "color_removal_debug.log"
SETTINGS_INI = Path.home() / ".config" / "MyBGRemover" / "MyBGRemover.ini"


def _write_debug(message: str):
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\\n")
    except Exception:
        pass


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except Exception:
        return default
    return max(minimum, min(maximum, number))


def _clamp_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "checked"}
    if value is None:
        return default
    return bool(value)


def _normalize_hex(value: str) -> str | None:
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6:
        return None
    try:
        int(text, 16)
    except ValueError:
        return None
    return "#" + text.upper()


def _read_saved_color_hex() -> str | None:
    if not SETTINGS_INI.exists():
        return None

    try:
        parser = ConfigParser()
        parser.read(SETTINGS_INI)

        if parser.has_option("prefs", "color_removal_hex"):
            value = parser.get("prefs", "color_removal_hex")
            return _normalize_hex(value)

        for section in parser.sections():
            for option in parser.options(section):
                if option.lower() in {"color_removal_hex", "prefs/color_removal_hex"}:
                    value = parser.get(section, option)
                    return _normalize_hex(value)
    except Exception:
        return None

    return None


def _normalize_target_color(target_color: Any) -> tuple[int, int, int]:
    if isinstance(target_color, str):
        hex_value = _normalize_hex(target_color)
        if hex_value is not None:
            value = hex_value[1:]
            return (
                int(value[0:2], 16),
                int(value[2:4], 16),
                int(value[4:6], 16),
            )
        return (255, 255, 255)

    if isinstance(target_color, (tuple, list)) and len(target_color) >= 3:
        return (
            _clamp_int(target_color[0], 0, 255, 255),
            _clamp_int(target_color[1], 0, 255, 255),
            _clamp_int(target_color[2], 0, 255, 255),
        )

    return (255, 255, 255)


def _first_present(mapping: dict[str, Any], names: tuple[str, ...], default: Any = None) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def _settings_to_options(settings: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    options = dict(kwargs)

    if isinstance(settings, dict):
        options.update(settings)

    nested = options.get("color_removal")
    if isinstance(nested, dict):
        merged = dict(options)
        merged.update(nested)
        options = merged

    target_color = _first_present(
        options,
        (
            "target_color",
            "target_rgb",
            "selected_color",
            "selected_removal_color",
            "color_removal_color",
            "removal_color",
            "color",
            "rgb",
        ),
        None,
    )

    if target_color is None:
        target_color = _first_present(
            options,
            (
                "target_hex",
                "hex_color",
                "color_hex",
                "selected_hex",
                "selected_removal_hex",
                "color_removal_hex",
                "removal_hex",
            ),
            None,
        )

    if target_color is None:
        saved_hex = _read_saved_color_hex()
        if saved_hex is not None:
            target_color = saved_hex
            _write_debug(f"target color missing from worker options; using saved QSettings color {saved_hex}")
        else:
            target_color = "#FFFFFF"
            _write_debug("target color missing from worker options and QSettings fallback was unavailable; using #FFFFFF")

    threshold = _first_present(
        options,
        ("threshold", "color_threshold", "color_removal_threshold", "tolerance", "color_tolerance"),
        30,
    )

    match_mode = _first_present(
        options,
        ("match_mode", "color_match_mode", "color_removal_match_mode"),
        "Connected Edges",
    )

    feather = _first_present(
        options,
        ("feather", "color_feather", "color_edge_feather", "color_removal_feather"),
        0,
    )

    spill_reduction = _first_present(
        options,
        ("spill_reduction", "color_spill_reduction", "color_removal_spill_reduction"),
        None,
    )

    if spill_reduction is None:
        reduce_spill = _first_present(
            options,
            ("reduce_spill", "reduce_color_spill", "color_reduce_spill", "color_removal_reduce_spill"),
            False,
        )
        spill_reduction = 20 if _clamp_bool(reduce_spill, False) else 0

    protect_dark_colors = _first_present(
        options,
        ("protect_dark_colors", "protect_dark", "color_protect_dark", "color_removal_protect_dark"),
        True,
    )

    return {
        "target_color": target_color,
        "threshold": threshold,
        "match_mode": match_mode,
        "feather": feather,
        "spill_reduction": spill_reduction,
        "protect_dark_colors": protect_dark_colors,
    }


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return (
        rgb[:, :, 0] * 0.2126
        + rgb[:, :, 1] * 0.7152
        + rgb[:, :, 2] * 0.0722
    )


def _target_luminance(target_color: tuple[int, int, int]) -> float:
    r, g, b = target_color
    return (r * 0.2126) + (g * 0.7152) + (b * 0.0722)


def _rgb_distance_mask(
    rgba: np.ndarray,
    target_color: tuple[int, int, int],
    threshold: int,
    protect_dark_colors: bool = True,
) -> np.ndarray:
    rgb = rgba[:, :, :3].astype(np.float32)
    target = np.array(target_color, dtype=np.float32)
    diff = rgb - target
    distance = np.sqrt(np.sum(diff * diff, axis=2))
    alpha = rgba[:, :, 3].astype(np.float32)
    visible = alpha > 0.0
    mask = (distance <= float(threshold)) & visible

    # Protect black/dark linework when removing light backgrounds.
    # If the selected target itself is dark, allow dark removal.
    if protect_dark_colors and _target_luminance(target_color) > 45.0:
        dark_pixel_mask = _luminance(rgb) < 30.0
        mask &= ~dark_pixel_mask

    return mask


def _connected_to_edges(mask: np.ndarray) -> np.ndarray:
    mask = mask.astype(bool)
    height, width = mask.shape
    connected = np.zeros_like(mask, dtype=bool)
    visited = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    if height <= 0 or width <= 0:
        return connected

    for x in range(width):
        if mask[0, x]:
            queue.append((x, 0))
            visited[0, x] = True
        if mask[height - 1, x] and not visited[height - 1, x]:
            queue.append((x, height - 1))
            visited[height - 1, x] = True

    for y in range(height):
        if mask[y, 0] and not visited[y, 0]:
            queue.append((0, y))
            visited[y, 0] = True
        if mask[y, width - 1] and not visited[y, width - 1]:
            queue.append((width - 1, y))
            visited[y, width - 1] = True

    while queue:
        x, y = queue.popleft()
        connected[y, x] = True

        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            if visited[ny, nx]:
                continue
            visited[ny, nx] = True
            if mask[ny, nx]:
                queue.append((nx, ny))

    return connected


def _feather_mask(mask: np.ndarray, feather: int) -> np.ndarray:
    if feather <= 0:
        return mask.astype(np.float32)

    mask_image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    blurred = mask_image.filter(ImageFilter.GaussianBlur(radius=float(feather)))
    return np.asarray(blurred, dtype=np.float32) / 255.0


def _reduce_color_spill(
    rgba: np.ndarray,
    target_color: tuple[int, int, int],
    removal_strength: np.ndarray,
    spill_reduction: int,
) -> np.ndarray:
    spill_reduction = _clamp_int(spill_reduction, 0, 100, 0)
    if spill_reduction <= 0:
        return rgba

    result = rgba.copy()
    alpha = result[:, :, 3].astype(np.float32)
    rgb = result[:, :, :3].astype(np.float32)
    target = np.array(target_color, dtype=np.float32)

    edge = (alpha > 0.0) & (alpha < 255.0) & (removal_strength > 0.0)
    if not np.any(edge):
        return result

    max_strength = 0.70
    strength = np.clip(removal_strength, 0.0, 1.0) * (float(spill_reduction) / 100.0) * max_strength
    strength = strength[..., np.newaxis]
    corrected = rgb + ((rgb - target) * strength)
    result[:, :, :3] = np.clip(corrected, 0, 255).astype(np.uint8)
    return result


def remove_color_from_pil(
    image: Image.Image,
    target_color: Any = (255, 255, 255),
    threshold: int = 30,
    match_mode: str = "Connected Edges",
    feather: int = 0,
    reduce_spill: bool | None = None,
    spill_reduction: int | None = None,
    protect_dark_colors: bool = True,
    **_: Any,
) -> Image.Image:
    target = _normalize_target_color(target_color)
    threshold = _clamp_int(threshold, 0, 255, 30)
    feather = _clamp_int(feather, 0, 100, 0)
    if spill_reduction is None:
        spill_reduction = 20 if _clamp_bool(reduce_spill, False) else 0
    spill_reduction = _clamp_int(spill_reduction, 0, 100, 0)
    protect_dark_colors = _clamp_bool(protect_dark_colors, True)

    rgba_image = image.convert("RGBA")
    rgba = np.array(rgba_image, dtype=np.uint8)
    base_mask = _rgb_distance_mask(
        rgba,
        target,
        threshold,
        protect_dark_colors=protect_dark_colors,
    )

    if str(match_mode).strip().lower() == "global match":
        final_mask = base_mask
    else:
        final_mask = _connected_to_edges(base_mask)

    if not np.any(final_mask):
        return rgba_image

    removal_strength = _feather_mask(final_mask, feather)
    result = rgba.copy()
    alpha = result[:, :, 3].astype(np.float32)
    new_alpha = alpha * (1.0 - np.clip(removal_strength, 0.0, 1.0))
    result[:, :, 3] = np.clip(new_alpha, 0, 255).astype(np.uint8)

    result = _reduce_color_spill(
        result,
        target,
        removal_strength,
        spill_reduction=spill_reduction,
    )

    return Image.fromarray(result, mode="RGBA")


def remove_color_from_image(
    image_path: str | Path,
    target_color: Any = (255, 255, 255),
    threshold: int = 30,
    match_mode: str = "Connected Edges",
    feather: int = 0,
    reduce_spill: bool | None = None,
    spill_reduction: int | None = None,
    protect_dark_colors: bool = True,
    **kwargs: Any,
) -> Image.Image:
    with Image.open(image_path) as image:
        return remove_color_from_pil(
            image,
            target_color=target_color,
            threshold=threshold,
            match_mode=match_mode,
            feather=feather,
            reduce_spill=reduce_spill,
            spill_reduction=spill_reduction,
            protect_dark_colors=protect_dark_colors,
            **kwargs,
        )



def remove_color_from_file(
    input_path: str | Path,
    output_path: str | Path | dict[str, Any] | None = None,
    target_color: Any = None,
    threshold: int | None = None,
    match_mode: str | None = None,
    feather: int | None = None,
    reduce_spill: bool | None = None,
    spill_reduction: int | None = None,
    protect_dark_colors: bool | None = None,
    **kwargs: Any,
) -> tuple[bool, str | None]:
    try:
        settings = None

        if isinstance(output_path, dict) and target_color is None:
            settings = output_path
            output_path = None
        elif isinstance(target_color, dict):
            settings = target_color
            target_color = None

        options = _settings_to_options(settings, kwargs)

        if target_color is not None:
            options["target_color"] = target_color
        if threshold is not None:
            options["threshold"] = threshold
        if match_mode is not None:
            options["match_mode"] = match_mode
        if feather is not None:
            options["feather"] = feather
        if spill_reduction is not None:
            options["spill_reduction"] = spill_reduction
        elif reduce_spill is not None:
            options["spill_reduction"] = 20 if _clamp_bool(reduce_spill, False) else 0
        if protect_dark_colors is not None:
            options["protect_dark_colors"] = protect_dark_colors

        normalized_target = _normalize_target_color(options["target_color"])

        _write_debug(
            "remove_color_from_file: "
            f"input={input_path!r}, output={output_path!r}, "
            f"target={normalized_target!r}, raw_target={options['target_color']!r}, "
            f"threshold={options['threshold']!r}, match_mode={options['match_mode']!r}, "
            f"feather={options['feather']!r}, spill_reduction={options['spill_reduction']!r}, "
            f"protect_dark_colors={options['protect_dark_colors']!r}"
        )

        result = remove_color_from_image(
            input_path,
            target_color=normalized_target,
            threshold=options["threshold"],
            match_mode=options["match_mode"],
            feather=options["feather"],
            spill_reduction=options["spill_reduction"],
            protect_dark_colors=options["protect_dark_colors"],
        )

        if output_path is None:
            return False, "Color Removal output path was not provided."

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        result.save(output)

        if not output.exists():
            return False, "Color Removal finished but output file was not created."

        return True, None

    except Exception as exc:
        _write_debug("remove_color_from_file FAILED:")
        _write_debug(traceback.format_exc())
        return False, str(exc)


def apply_color_removal(
    image: Image.Image,
    target_color: Any = (255, 255, 255),
    threshold: int = 30,
    match_mode: str = "Connected Edges",
    feather: int = 0,
    reduce_spill: bool | None = None,
    spill_reduction: int | None = None,
    protect_dark_colors: bool = True,
    **kwargs: Any,
) -> Image.Image:
    return remove_color_from_pil(
        image,
        target_color=target_color,
        threshold=threshold,
        match_mode=match_mode,
        feather=feather,
        reduce_spill=reduce_spill,
        spill_reduction=spill_reduction,
        protect_dark_colors=protect_dark_colors,
        **kwargs,
    )


def remove_selected_color(
    image: Image.Image,
    target_color: Any = (255, 255, 255),
    threshold: int = 30,
    match_mode: str = "Connected Edges",
    feather: int = 0,
    reduce_spill: bool | None = None,
    spill_reduction: int | None = None,
    protect_dark_colors: bool = True,
    **kwargs: Any,
) -> Image.Image:
    return apply_color_removal(
        image,
        target_color=target_color,
        threshold=threshold,
        match_mode=match_mode,
        feather=feather,
        reduce_spill=reduce_spill,
        spill_reduction=spill_reduction,
        protect_dark_colors=protect_dark_colors,
        **kwargs,
    )
