from collections import deque
from pathlib import Path

from PIL import Image
import numpy as np


def _normalize_target_color(target_color) -> tuple[int, int, int]:
    if isinstance(target_color, str):
        clean = target_color.strip().upper()
        if clean.startswith("#"):
            clean = clean[1:]

        if len(clean) == 3:
            clean = "".join(ch * 2 for ch in clean)

        if len(clean) != 6:
            raise ValueError("Target color must be a hex color like #FFFFFF.")

        return (
            int(clean[0:2], 16),
            int(clean[2:4], 16),
            int(clean[4:6], 16),
        )

    if isinstance(target_color, (tuple, list)) and len(target_color) >= 3:
        return (
            max(0, min(255, int(target_color[0]))),
            max(0, min(255, int(target_color[1]))),
            max(0, min(255, int(target_color[2]))),
        )

    raise ValueError("Target color must be an RGB tuple or hex color.")


def _connected_to_edges(mask: np.ndarray) -> np.ndarray:
    mask = mask.astype(bool)
    h, w = mask.shape
    connected = np.zeros_like(mask, dtype=bool)
    visited = np.zeros_like(mask, dtype=bool)
    q = deque()

    for x in range(w):
        if mask[0, x] and not visited[0, x]:
            q.append((x, 0))
            visited[0, x] = True
        if mask[h - 1, x] and not visited[h - 1, x]:
            q.append((x, h - 1))
            visited[h - 1, x] = True

    for y in range(h):
        if mask[y, 0] and not visited[y, 0]:
            q.append((0, y))
            visited[y, 0] = True
        if mask[y, w - 1] and not visited[y, w - 1]:
            q.append((w - 1, y))
            visited[y, w - 1] = True

    while q:
        x, y = q.popleft()
        connected[y, x] = True
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue
            if visited[ny, nx] or not mask[ny, nx]:
                continue
            visited[ny, nx] = True
            q.append((nx, ny))

    return connected


def _dilate_mask(mask: np.ndarray, pixels: int) -> np.ndarray:
    if pixels <= 0:
        return mask.astype(bool).copy()

    result = mask.astype(bool).copy()
    for _ in range(int(pixels)):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        grown = np.zeros_like(result, dtype=bool)
        for dy in range(3):
            for dx in range(3):
                grown |= padded[dy:dy + result.shape[0], dx:dx + result.shape[1]]
        result = grown
    return result


def _erode_mask(mask: np.ndarray, pixels: int) -> np.ndarray:
    if pixels <= 0:
        return mask.astype(bool).copy()

    result = mask.astype(bool).copy()
    for _ in range(int(pixels)):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        shrunk = np.ones_like(result, dtype=bool)
        for dy in range(3):
            for dx in range(3):
                shrunk &= padded[dy:dy + result.shape[0], dx:dx + result.shape[1]]
        result = shrunk
    return result


def _feather_remove_mask(remove_mask: np.ndarray, feather: int) -> np.ndarray:
    remove_mask = remove_mask.astype(bool)
    feather = max(0, int(feather))

    if feather <= 0:
        return remove_mask.astype(np.float32)

    weights = remove_mask.astype(np.float32)
    grown = remove_mask.copy()

    for step in range(1, feather + 1):
        next_grown = _dilate_mask(grown, 1)
        ring = next_grown & (~grown)
        ring_strength = max(0.0, 1.0 - (step / float(feather + 1)))
        weights[ring] = np.maximum(weights[ring], ring_strength)
        grown = next_grown

    return np.clip(weights, 0.0, 1.0)


def _reduce_color_spill(rgba: np.ndarray, target_rgb: tuple[int, int, int], remove_weight: np.ndarray) -> np.ndarray:
    result = rgba.copy().astype(np.float32)
    rgb = result[:, :, :3]
    alpha = result[:, :, 3]

    edge_mask = (remove_weight > 0.0) & (remove_weight < 1.0) & (alpha > 0.0)
    solid_mask = alpha > 245.0

    if not np.any(edge_mask) or not np.any(solid_mask):
        return rgba

    h, w = alpha.shape
    padded_rgb = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
    padded_solid = np.pad(solid_mask, 1, mode="constant", constant_values=False)

    rgb_sum = np.zeros_like(rgb, dtype=np.float32)
    count = np.zeros((h, w), dtype=np.float32)

    for dy in range(3):
        for dx in range(3):
            neighbor_rgb = padded_rgb[dy:dy + h, dx:dx + w]
            neighbor_mask = padded_solid[dy:dy + h, dx:dx + w]
            rgb_sum += neighbor_rgb * neighbor_mask[..., np.newaxis]
            count += neighbor_mask.astype(np.float32)

    valid = edge_mask & (count > 0.0)
    if not np.any(valid):
        return rgba

    average_rgb = rgb_sum / np.maximum(count[..., np.newaxis], 1.0)
    target = np.array(target_rgb, dtype=np.float32)
    distance_to_target = np.sqrt(np.sum((rgb - target) ** 2, axis=2))
    spill_strength = np.clip((90.0 - distance_to_target) / 90.0, 0.0, 1.0)
    spill_strength *= np.clip(remove_weight, 0.0, 1.0)
    spill_strength = (spill_strength * 0.65)[..., np.newaxis]

    rgb[valid] = rgb[valid] * (1.0 - spill_strength[valid]) + average_rgb[valid] * spill_strength[valid]
    result[:, :, :3] = np.clip(rgb, 0, 255)
    return np.clip(result, 0, 255).astype(np.uint8)


def remove_color_from_pil(
    image: Image.Image,
    target_color=(255, 255, 255),
    threshold: int = 30,
    match_mode: str = "Connected Edges",
    feather: int = 0,
    reduce_spill: bool = False,
) -> Image.Image:
    target_rgb = _normalize_target_color(target_color)
    threshold = max(0, min(255, int(threshold)))
    feather = max(0, min(20, int(feather)))

    rgba_image = image.convert("RGBA")
    pixels = np.array(rgba_image).astype(np.uint8)

    rgb = pixels[:, :, :3].astype(np.int16)
    alpha = pixels[:, :, 3].astype(np.float32)

    target = np.array(target_rgb, dtype=np.int16)
    diff = rgb - target
    distance_squared = np.sum(diff * diff, axis=2)
    threshold_squared = threshold * threshold

    base_remove_mask = distance_squared <= threshold_squared
    base_remove_mask &= alpha > 0.0

    if str(match_mode).strip() == "Global Match":
        remove_mask = base_remove_mask
    else:
        remove_mask = _connected_to_edges(base_remove_mask)

    remove_weight = _feather_remove_mask(remove_mask, feather)

    new_alpha = alpha * (1.0 - remove_weight)
    pixels[:, :, 3] = np.clip(new_alpha, 0, 255).astype(np.uint8)

    if reduce_spill:
        pixels = _reduce_color_spill(pixels, target_rgb, remove_weight)

    return Image.fromarray(pixels, mode="RGBA")


def remove_color_from_file(
    input_path: Path,
    output_path: Path,
    target_color=(255, 255, 255),
    threshold: int = 30,
    match_mode: str = "Connected Edges",
    feather: int = 0,
    reduce_spill: bool = False,
) -> tuple[bool, str | None]:
    try:
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(input_path) as img:
            result = remove_color_from_pil(
                image=img,
                target_color=target_color,
                threshold=threshold,
                match_mode=match_mode,
                feather=feather,
                reduce_spill=reduce_spill,
            )
            result.save(output_path, format="PNG")

        if not output_path.exists():
            return False, f"Color Removal output was not created: {output_path}"

        return True, None

    except Exception as e:
        return False, str(e)
