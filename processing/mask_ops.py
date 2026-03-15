from pathlib import Path

import numpy as np
from PIL import Image


def apply_preview_edit_delta_to_fullres(
    fullres_image_path: Path,
    base_preview_mask_image_path: Path,
    edited_preview_mask_image_path: Path,
) -> tuple[bool, str | None]:
    try:
        fullres_image_path = Path(fullres_image_path)
        base_preview_mask_image_path = Path(base_preview_mask_image_path)
        edited_preview_mask_image_path = Path(edited_preview_mask_image_path)

        if not fullres_image_path.exists():
            return False, f"Full-resolution image not found: {fullres_image_path}"

        if not base_preview_mask_image_path.exists():
            return False, f"Base preview image not found: {base_preview_mask_image_path}"

        if not edited_preview_mask_image_path.exists():
            return False, f"Edited preview image not found: {edited_preview_mask_image_path}"

        with (
            Image.open(fullres_image_path) as full_img,
            Image.open(base_preview_mask_image_path) as base_preview_img,
            Image.open(edited_preview_mask_image_path) as edited_preview_img,
        ):
            full_img = full_img.convert("RGBA")
            base_preview_img = base_preview_img.convert("RGBA")
            edited_preview_img = edited_preview_img.convert("RGBA")

            full_rgba = np.array(full_img, dtype=np.uint8)
            full_alpha = full_rgba[:, :, 3].astype(np.float32) / 255.0

            base_preview_alpha = np.array(base_preview_img, dtype=np.uint8)[:, :, 3]
            edited_preview_alpha = np.array(edited_preview_img, dtype=np.uint8)[:, :, 3]

            base_resized = Image.fromarray(base_preview_alpha, mode="L").resize(
                full_img.size,
                Image.Resampling.LANCZOS,
            )
            edited_resized = Image.fromarray(edited_preview_alpha, mode="L").resize(
                full_img.size,
                Image.Resampling.LANCZOS,
            )

            base_alpha = np.array(base_resized, dtype=np.float32) / 255.0
            edited_alpha = np.array(edited_resized, dtype=np.float32) / 255.0

            result_alpha = full_alpha.copy()
            eps = 1e-6

            erase_mask = edited_alpha <= base_alpha
            restore_mask = edited_alpha > base_alpha

            if np.any(erase_mask):
                erase_ratio = edited_alpha[erase_mask] / np.maximum(base_alpha[erase_mask], eps)
                result_alpha[erase_mask] = full_alpha[erase_mask] * erase_ratio

            if np.any(restore_mask):
                restore_fraction = (
                    (edited_alpha[restore_mask] - base_alpha[restore_mask])
                    / np.maximum(1.0 - base_alpha[restore_mask], eps)
                )
                restore_fraction = np.clip(restore_fraction, 0.0, 1.0)
                result_alpha[restore_mask] = (
                    full_alpha[restore_mask]
                    + (1.0 - full_alpha[restore_mask]) * restore_fraction
                )

            result_alpha = np.clip(result_alpha * 255.0, 0, 255).astype(np.uint8)
            full_rgba[:, :, 3] = result_alpha

            result = Image.fromarray(full_rgba, mode="RGBA")
            result.save(fullres_image_path, format="PNG")

        return True, None

    except Exception as e:
        return False, str(e)
