from io import BytesIO
from pathlib import Path
import math
from collections import deque

import numpy as np
from PIL import Image

from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
    QScrollArea,
    QHBoxLayout,
    QPushButton,
    QWidget,
)


class _CanvasLabel(QLabel):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def mousePressEvent(self, event):
        self.owner.handle_mouse_press(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.owner.handle_mouse_move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.owner.handle_mouse_release(event)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.owner.handle_mouse_leave(event)
        super().leaveEvent(event)


class PreviewCanvas(QFrame):
    image_edited = Signal(str)
    edits_reset = Signal()

    def __init__(self):
        super().__init__()

        self.setObjectName("previewCanvas")
        self.setFrameShape(QFrame.StyledPanel)

        self._current_pixmap = None
        self._base_fit_scale = 1.0
        self._zoom_factor = 1.0

        self._before_image_pil = None
        self._editable_after_image_pil = None
        self._editable_rgba = None
        self._restore_source_rgba = None
        self._history_baseline_rgba = None
        self._edit_reset_baseline_rgba = None

        self._interaction_mode = "preview"
        self._current_mode = "after"

        self._tool_name = "Erase"
        self._apply_mode = "Brush"

        self._brush_size = 40
        self._softness = 35
        self._opacity = 100
        self._spacing = 20
        self._tolerance = 35

        self._magic_mode = "Connected Region"
        self._edge_protect_enabled = True
        self._max_undo_states = 60

        self._mouse_down = False
        self._last_image_point = None
        self._drag_edit_active = False
        self._hover_image_point = None

        self._undo_stack = []
        self._redo_stack = []

        self._pending_undo_state = None
        self._stroke_changed = False

        self._editable_save_path = None
        self._title_text = "Preview"

        self._history_store = {}

        layout = QVBoxLayout(self)

        self.title_label = QLabel("Preview")

        toolbar = QHBoxLayout()

        self.preview_mode_btn = QPushButton("Preview Mode ✓")
        self.edit_mode_btn = QPushButton("Edit Mode")

        self.before_btn = QPushButton("Before")
        self.after_btn = QPushButton("After ✓")

        self.undo_btn = QPushButton("Undo")
        self.redo_btn = QPushButton("Redo")
        self.reset_edits_btn = QPushButton("Reset Edits")

        self.zoom_in_btn = QPushButton("Zoom +")
        self.zoom_out_btn = QPushButton("Zoom -")

        toolbar.addWidget(self.preview_mode_btn)
        toolbar.addWidget(self.edit_mode_btn)
        toolbar.addWidget(self.before_btn)
        toolbar.addWidget(self.after_btn)
        toolbar.addWidget(self.undo_btn)
        toolbar.addWidget(self.redo_btn)
        toolbar.addWidget(self.reset_edits_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.zoom_in_btn)
        toolbar.addWidget(self.zoom_out_btn)

        self.image_label = _CanvasLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.image_label.setStyleSheet("background: transparent;")
        self.image_label.setMouseTracking(True)
        self.image_label.hide()

        self.image_container = QWidget()
        self.image_container.setStyleSheet("background: transparent;")
        self.image_container_layout = QVBoxLayout(self.image_container)
        self.image_container_layout.setContentsMargins(0, 0, 0, 0)
        self.image_container_layout.addStretch()
        self.image_container_layout.addWidget(
            self.image_label,
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        self.image_container_layout.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.image_container)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background: transparent; border: 0;")
        self.scroll_area.viewport().setStyleSheet("background: transparent;")

        layout.addWidget(self.title_label)
        layout.addLayout(toolbar)
        layout.addWidget(self.scroll_area)

        self.preview_mode_btn.clicked.connect(self.set_preview_mode)
        self.edit_mode_btn.clicked.connect(self.set_edit_mode)
        self.before_btn.clicked.connect(self.show_before)
        self.after_btn.clicked.connect(self.show_after)
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn.clicked.connect(self.redo)
        self.reset_edits_btn.clicked.connect(self.reset_edits)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self._update_mode_buttons()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_pixmap is not None:
            self._render_current_pixmap()

    def _history_key(self):
        if self._editable_save_path is None:
            return None
        return str(self._editable_save_path)

    def _save_history_snapshot(self):
        key = self._history_key()
        if key is None:
            return
        if self._editable_rgba is None:
            return

        self._history_store[key] = {
            "undo_stack": [state.copy() for state in self._undo_stack],
            "redo_stack": [state.copy() for state in self._redo_stack],
            "interaction_mode": self._interaction_mode,
            "current_mode": self._current_mode,
            "zoom_factor": self._zoom_factor,
        }

    def _restore_history_snapshot(self):
        key = self._history_key()
        if key is None:
            return False

        snapshot = self._history_store.get(key)
        if snapshot is None:
            return False

        self._undo_stack = [state.copy() for state in snapshot.get("undo_stack", [])]
        self._redo_stack = [state.copy() for state in snapshot.get("redo_stack", [])]
        self._interaction_mode = snapshot.get("interaction_mode", self._interaction_mode)
        self._current_mode = snapshot.get("current_mode", self._current_mode)
        self._zoom_factor = snapshot.get("zoom_factor", self._zoom_factor)

        self._pending_undo_state = None
        self._stroke_changed = False
        return True

    def clear_preview(self, reset_title: bool = True):
        self._save_history_snapshot()

        self._current_pixmap = None
        self._base_fit_scale = 1.0
        self._zoom_factor = 1.0

        self._before_image_pil = None
        self._editable_after_image_pil = None
        self._editable_rgba = None
        self._restore_source_rgba = None
        self._history_baseline_rgba = None
        self._edit_reset_baseline_rgba = None

        self._interaction_mode = "preview"
        self._current_mode = "after"

        self._mouse_down = False
        self._last_image_point = None
        self._drag_edit_active = False
        self._hover_image_point = None

        self._undo_stack = []
        self._redo_stack = []
        self._pending_undo_state = None
        self._stroke_changed = False

        self._editable_save_path = None

        if reset_title:
            self._title_text = "Preview"
            self.title_label.setText("Preview")

        self.image_label.clear()
        self.image_label.resize(0, 0)
        self.image_label.hide()
        self._update_mode_buttons()

    def set_magic_mode(self, mode: str):
        valid_modes = {"Connected Region", "Global Match"}
        self._magic_mode = mode if mode in valid_modes else "Connected Region"
        self._render_current_pixmap()

    def set_edge_protect_enabled(self, enabled: bool):
        self._edge_protect_enabled = bool(enabled)

    def set_tool_settings(
        self,
        tool_name,
        apply_mode,
        brush_size,
        softness,
        opacity,
        spacing,
        tolerance,
    ):
        self._tool_name = tool_name
        self._apply_mode = apply_mode
        self._brush_size = brush_size
        self._softness = softness
        self._opacity = opacity
        self._spacing = spacing
        self._tolerance = tolerance
        self._render_current_pixmap()

    def set_preview_images(
        self,
        before_image_path,
        after_image_path=None,
        title_text="Preview",
        default_mode="after",
        editable_save_path=None,
        preferred_interaction_mode="preview",
        preferred_view_mode="after",
        **_,
    ):
        self._save_history_snapshot()

        self._current_pixmap = None
        self._base_fit_scale = 1.0

        self._before_image_pil = None
        self._editable_after_image_pil = None
        self._editable_rgba = None
        self._restore_source_rgba = None
        self._history_baseline_rgba = None
        self._edit_reset_baseline_rgba = None

        self._mouse_down = False
        self._last_image_point = None
        self._drag_edit_active = False
        self._hover_image_point = None

        self._undo_stack = []
        self._redo_stack = []
        self._pending_undo_state = None
        self._stroke_changed = False

        self._title_text = title_text or "Preview"
        self.title_label.setText(self._title_text)

        self._editable_save_path = Path(editable_save_path) if editable_save_path else None
        if self._editable_save_path is not None:
            self._editable_save_path.parent.mkdir(parents=True, exist_ok=True)

        if before_image_path and Path(before_image_path).exists():
            with Image.open(before_image_path) as img:
                self._before_image_pil = img.convert("RGBA")

        loaded_after = None
        if after_image_path and Path(after_image_path).exists():
            with Image.open(after_image_path) as img:
                loaded_after = img.convert("RGBA")

        if loaded_after is not None:
            self._editable_after_image_pil = loaded_after
        elif self._before_image_pil is not None:
            self._editable_after_image_pil = self._before_image_pil.copy()
        else:
            self._editable_after_image_pil = None

        if self._editable_after_image_pil is not None:
            self._editable_rgba = np.array(self._editable_after_image_pil)
        else:
            self._editable_rgba = None

        if self._before_image_pil is not None:
            self._restore_source_rgba = np.array(self._before_image_pil)
        elif self._editable_after_image_pil is not None:
            self._restore_source_rgba = np.array(self._editable_after_image_pil)
        else:
            self._restore_source_rgba = None

        if self._editable_rgba is not None:
            self._history_baseline_rgba = self._editable_rgba.copy()

        if loaded_after is not None:
            self._edit_reset_baseline_rgba = np.array(loaded_after)
        elif self._editable_rgba is not None:
            self._edit_reset_baseline_rgba = self._editable_rgba.copy()

        valid_modes = {"before", "after"}
        chosen_view_mode = preferred_view_mode if preferred_view_mode in valid_modes else default_mode

        if chosen_view_mode == "before" and self._before_image_pil is not None:
            self._current_mode = "before"
        elif self._editable_after_image_pil is not None:
            self._current_mode = "after"
        else:
            self._current_mode = "before"

        if preferred_interaction_mode == "edit" and self._editable_after_image_pil is not None:
            self._interaction_mode = "edit"
            self._current_mode = "after"
        else:
            self._interaction_mode = "preview"

        self._zoom_factor = 1.0

        restored = self._restore_history_snapshot()

        if not restored:
            if self._current_mode == "after" and self._editable_after_image_pil is None:
                self._current_mode = "before"
            elif self._current_mode == "before" and self._before_image_pil is None:
                self._current_mode = "after"

        self._load_current_mode_pixmap()
        self._update_mode_buttons()

    def set_preview_mode(self):
        self._interaction_mode = "preview"
        self._hover_image_point = None
        if self._editable_after_image_pil is not None:
            self._current_mode = "after"
        else:
            self._current_mode = "before"
        self._load_current_mode_pixmap()
        self._update_mode_buttons()

    def set_edit_mode(self):
        if self._editable_after_image_pil is None:
            return
        self._interaction_mode = "edit"
        self._current_mode = "after"
        self._load_current_mode_pixmap()
        self._update_mode_buttons()

    def show_before(self):
        if self._before_image_pil is None:
            return
        self._current_mode = "before"
        self._load_current_mode_pixmap()
        self._update_mode_buttons()

    def show_after(self):
        if self._editable_after_image_pil is None:
            return
        self._current_mode = "after"
        self._load_current_mode_pixmap()
        self._update_mode_buttons()

    def zoom_in(self):
        if self._current_pixmap is None:
            return
        self._zoom_factor = min(self._zoom_factor * 1.25, 8.0)
        self._render_current_pixmap()
        self._save_history_snapshot()

    def zoom_out(self):
        if self._current_pixmap is None:
            return
        self._zoom_factor = max(self._zoom_factor / 1.25, 0.1)
        self._render_current_pixmap()
        self._save_history_snapshot()

    def _can_undo(self) -> bool:
        if self._undo_stack:
            return True

        if self._editable_rgba is None or self._history_baseline_rgba is None:
            return False

        return not np.array_equal(self._editable_rgba, self._history_baseline_rgba)

    def _push_undo_state(self, rgba_state):
        if rgba_state is None:
            return
        self._undo_stack.append(rgba_state.copy())
        if len(self._undo_stack) > self._max_undo_states:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._save_history_snapshot()

    def _update_mode_buttons(self):
        if self._interaction_mode == "preview":
            self.preview_mode_btn.setText("Preview Mode ✓")
            self.edit_mode_btn.setText("Edit Mode")
        else:
            self.preview_mode_btn.setText("Preview Mode")
            self.edit_mode_btn.setText("Edit Mode ✓")

        if self._current_mode == "before":
            self.before_btn.setText("Before ✓")
            self.after_btn.setText("After")
        else:
            self.before_btn.setText("Before")
            self.after_btn.setText("After ✓")

        has_edit_target = self._editable_after_image_pil is not None
        self.edit_mode_btn.setEnabled(has_edit_target)
        self.after_btn.setEnabled(has_edit_target)
        self.reset_edits_btn.setEnabled(has_edit_target and self._edit_reset_baseline_rgba is not None)

        self.undo_btn.setEnabled(self._can_undo())
        self.redo_btn.setEnabled(bool(self._redo_stack))

    def _get_current_image(self):
        if self._current_mode == "after":
            return self._editable_after_image_pil
        return self._before_image_pil

    def _load_current_mode_pixmap(self):
        image = self._get_current_image()

        if image is None:
            self.image_label.clear()
            self.image_label.resize(0, 0)
            self.image_label.hide()
            self._current_pixmap = None
            self._update_mode_buttons()
            return

        buffer = BytesIO()
        image.save(buffer, format="PNG")

        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())
        self._current_pixmap = pixmap

        self._render_current_pixmap()

    def _render_current_pixmap(self):
        if self._current_pixmap is None:
            return

        viewport_size = self.scroll_area.viewport().size()
        if not viewport_size.isValid():
            viewport_size = QSize(400, 400)

        available_width = max(1, viewport_size.width() - 20)
        available_height = max(1, viewport_size.height() - 20)

        pixmap_width = max(1, self._current_pixmap.width())
        pixmap_height = max(1, self._current_pixmap.height())

        fit_scale = min(
            available_width / pixmap_width,
            available_height / pixmap_height,
        )

        self._base_fit_scale = min(fit_scale, 1.0)
        final_scale = max(0.01, self._base_fit_scale * self._zoom_factor)

        scaled_width = max(1, int(pixmap_width * final_scale))
        scaled_height = max(1, int(pixmap_height * final_scale))

        scaled_pixmap = self._current_pixmap.scaled(
            scaled_width,
            scaled_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        if self._interaction_mode == "edit" and self._hover_image_point is not None:
            display_pixmap = QPixmap(scaled_pixmap)
            painter = QPainter(display_pixmap)

            if self._tool_name == "Restore":
                color = QColor(80, 210, 120, 220)
            elif self._tool_name == "Magic Erase":
                color = QColor(120, 180, 255, 220)
            elif self._tool_name == "Background Erase":
                color = QColor(255, 170, 80, 220)
            else:
                color = QColor(255, 80, 80, 220)

            pen = QPen(color)
            pen.setWidth(2)
            painter.setPen(pen)

            hx, hy = self._hover_image_point

            if self._editable_rgba is not None:
                img_h, img_w = self._editable_rgba.shape[:2]
                if img_w > 0 and img_h > 0:
                    px = int(round(hx * scaled_width / img_w))
                    py = int(round(hy * scaled_height / img_h))
                    radius = max(2, int(round((self._brush_size / 2.0) * final_scale)))

                    painter.drawEllipse(px - radius, py - radius, radius * 2, radius * 2)

                    if self._tool_name in ("Magic Erase", "Background Erase"):
                        small_pen = QPen(QColor(255, 255, 255, 200))
                        small_pen.setWidth(1)
                        painter.setPen(small_pen)
                        painter.drawLine(px - 6, py, px + 6, py)
                        painter.drawLine(px, py - 6, px, py + 6)

            painter.end()
            scaled_pixmap = display_pixmap

        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())
        self.image_label.show()
        self._update_mode_buttons()

    def handle_mouse_press(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._interaction_mode != "edit":
            return

        if self._editable_rgba is None:
            return

        pos = event.position().toPoint()
        image_pos = self._widget_pos_to_image_pos(pos)

        if image_pos is None:
            return

        x, y = image_pos
        self._hover_image_point = (x, y)

        self._mouse_down = True
        self._last_image_point = (x, y)
        self._drag_edit_active = False
        self._stroke_changed = False
        self._pending_undo_state = self._editable_rgba.copy()

        changed = self._apply_tool_at_point(x, y)

        if changed:
            self._stroke_changed = True
            self._drag_edit_active = True
            self._finish_edit_update()
        else:
            self._mouse_down = self._apply_mode == "Brush"
            self._render_current_pixmap()
            return

        if self._apply_mode == "Smart Selection":
            if self._stroke_changed and self._pending_undo_state is not None:
                self._push_undo_state(self._pending_undo_state)
            self._pending_undo_state = None
            self._stroke_changed = False
            self._mouse_down = False
            self._last_image_point = None
            self._drag_edit_active = False
            self._save_history_snapshot()

    def handle_mouse_move(self, event):
        pos = event.position().toPoint()
        image_pos = self._widget_pos_to_image_pos(pos)

        if image_pos is not None:
            self._hover_image_point = image_pos
        else:
            self._hover_image_point = None

        if self._interaction_mode == "edit":
            self._render_current_pixmap()

        if not self._mouse_down:
            return

        if self._interaction_mode != "edit":
            return

        if self._editable_rgba is None:
            return

        if self._apply_mode != "Brush":
            return

        if image_pos is None:
            return

        x, y = image_pos
        current_point = (x, y)

        if self._last_image_point is None:
            self._last_image_point = current_point

        changed = self._apply_stroke_between_points(self._last_image_point, current_point)

        if changed:
            self._stroke_changed = True
            self._drag_edit_active = True
            self._finish_edit_update()

        self._last_image_point = current_point

    def handle_mouse_release(self, event):
        if self._apply_mode == "Brush" and self._stroke_changed and self._pending_undo_state is not None:
            self._push_undo_state(self._pending_undo_state)

        self._pending_undo_state = None
        self._stroke_changed = False
        self._mouse_down = False
        self._last_image_point = None
        self._drag_edit_active = False
        self._save_history_snapshot()

    def handle_mouse_leave(self, event):
        self._hover_image_point = None
        if self._interaction_mode == "edit":
            self._render_current_pixmap()

    def _widget_pos_to_image_pos(self, pos: QPoint):
        pixmap = self.image_label.pixmap()

        if pixmap is None or self._editable_rgba is None:
            return None

        w = pixmap.width()
        h = pixmap.height()

        if w == 0 or h == 0:
            return None

        x = pos.x()
        y = pos.y()

        img_h, img_w = self._editable_rgba.shape[:2]

        img_x = int(x * img_w / w)
        img_y = int(y * img_h / h)

        if img_x < 0 or img_y < 0 or img_x >= img_w or img_y >= img_h:
            return None

        return img_x, img_y

    def _apply_tool_at_point(self, x: int, y: int) -> bool:
        if self._tool_name == "Erase":
            return self._brush_erase(x, y)
        if self._tool_name == "Restore":
            return self._brush_restore(x, y)
        if self._tool_name == "Magic Erase":
            return self._magic_erase(x, y)
        if self._tool_name == "Background Erase":
            return self._background_erase(x, y)
        return False

    def _apply_stroke_between_points(self, start_point: tuple[int, int], end_point: tuple[int, int]) -> bool:
        x1, y1 = start_point
        x2, y2 = end_point

        dx = x2 - x1
        dy = y2 - y1
        distance = math.hypot(dx, dy)

        radius = max(1.0, self._brush_size / 2.0)
        spacing_ratio = max(0.01, self._spacing / 100.0)

        if self._tool_name in ("Magic Erase", "Background Erase"):
            step_distance = max(0.5, radius * spacing_ratio * 0.35)
        else:
            step_distance = max(1.0, radius * spacing_ratio)

        if distance == 0:
            return self._apply_tool_at_point(x1, y1)

        steps = max(1, int(math.ceil(distance / step_distance)))
        changed = False

        for i in range(steps + 1):
            t = i / steps
            px = int(round(x1 + dx * t))
            py = int(round(y1 + dy * t))
            if self._apply_tool_at_point(px, py):
                changed = True

        return changed

    def _effective_softness_ratio(self) -> float:
        softness_ratio = max(0.0, min(1.0, self._softness / 100.0))

        if self._tool_name in ("Magic Erase", "Background Erase") and self._apply_mode == "Brush":
            return max(softness_ratio, 0.72)

        return softness_ratio

    def _brush_weight_mask(self, center_x: int, center_y: int):
        if self._editable_rgba is None:
            return None

        img_h, img_w = self._editable_rgba.shape[:2]
        radius = max(1.0, self._brush_size / 2.0)
        softness_ratio = self._effective_softness_ratio()
        inner_radius = radius * (1.0 - softness_ratio)

        y_grid, x_grid = np.ogrid[:img_h, :img_w]
        distance = np.sqrt((x_grid - center_x) ** 2 + (y_grid - center_y) ** 2)

        weights = np.zeros((img_h, img_w), dtype=np.float32)

        if softness_ratio <= 0.0:
            weights[distance <= radius] = 1.0
            return weights

        weights[distance <= inner_radius] = 1.0

        feather_mask = (distance > inner_radius) & (distance <= radius)
        feather_width = max(1e-6, radius - inner_radius)
        weights[feather_mask] = 1.0 - ((distance[feather_mask] - inner_radius) / feather_width)

        return np.clip(weights, 0.0, 1.0)

    def _get_brush_bounds(self, center_x: int, center_y: int):
        if self._editable_rgba is None:
            return None

        img_h, img_w = self._editable_rgba.shape[:2]
        radius = max(1.0, self._brush_size / 2.0)
        pad = int(math.ceil(radius)) + 3

        x0 = max(0, center_x - pad)
        x1 = min(img_w, center_x + pad + 1)
        y0 = max(0, center_y - pad)
        y1 = min(img_h, center_y + pad + 1)

        if x0 >= x1 or y0 >= y1:
            return None

        return x0, x1, y0, y1

    def _get_match_bounds(self, center_x: int, center_y: int):
        if self._editable_rgba is None:
            return None

        img_h, img_w = self._editable_rgba.shape[:2]
        brush_radius = max(1.0, self._brush_size / 2.0)

        if self._tool_name in ("Magic Erase", "Background Erase") and self._apply_mode == "Brush":
            match_radius = max(brush_radius * 3.0, 48.0)
        else:
            match_radius = brush_radius + 3.0

        pad = int(math.ceil(match_radius))

        x0 = max(0, center_x - pad)
        x1 = min(img_w, center_x + pad + 1)
        y0 = max(0, center_y - pad)
        y1 = min(img_h, center_y + pad + 1)

        if x0 >= x1 or y0 >= y1:
            return None

        return x0, x1, y0, y1

    def _local_brush_weight_mask(self, center_x: int, center_y: int, bounds):
        if self._editable_rgba is None or bounds is None:
            return None

        x0, x1, y0, y1 = bounds
        radius = max(1.0, self._brush_size / 2.0)
        softness_ratio = self._effective_softness_ratio()
        inner_radius = radius * (1.0 - softness_ratio)

        local_h = y1 - y0
        local_w = x1 - x0

        y_grid, x_grid = np.ogrid[y0:y1, x0:x1]
        distance = np.sqrt((x_grid - center_x) ** 2 + (y_grid - center_y) ** 2)

        weights = np.zeros((local_h, local_w), dtype=np.float32)

        if softness_ratio <= 0.0:
            weights[distance <= radius] = 1.0
            return weights

        weights[distance <= inner_radius] = 1.0

        feather_mask = (distance > inner_radius) & (distance <= radius)
        feather_width = max(1e-6, radius - inner_radius)
        weights[feather_mask] = 1.0 - ((distance[feather_mask] - inner_radius) / feather_width)

        return np.clip(weights, 0.0, 1.0)

    def _sample_seed_color(self, x: int, y: int, rgba_region: np.ndarray | None = None, origin=(0, 0)) -> np.ndarray:
        if rgba_region is None:
            rgba_region = self._editable_rgba
            origin_x, origin_y = 0, 0
        else:
            origin_x, origin_y = origin

        rgb = rgba_region[:, :, :3].astype(np.float32)
        alpha = rgba_region[:, :, 3].astype(np.float32)

        local_x = x - origin_x
        local_y = y - origin_y

        h, w = alpha.shape
        if local_x < 0 or local_y < 0 or local_x >= w or local_y >= h:
            return rgb[max(0, min(h - 1, local_y)), max(0, min(w - 1, local_x))]

        x0 = max(0, local_x - 1)
        x1 = min(w, local_x + 2)
        y0 = max(0, local_y - 1)
        y1 = min(h, local_y + 2)

        patch_rgb = rgb[y0:y1, x0:x1]
        patch_alpha = alpha[y0:y1, x0:x1] / 255.0

        weights = np.clip(patch_alpha, 0.05, 1.0)
        weight_sum = np.sum(weights)

        if weight_sum <= 1e-6:
            return rgb[local_y, local_x]

        weighted_rgb = patch_rgb * weights[..., np.newaxis]
        return np.sum(weighted_rgb, axis=(0, 1)) / weight_sum

    def _compute_color_distance(self, seed_color: np.ndarray, rgb_region: np.ndarray | None = None) -> np.ndarray:
        if rgb_region is None:
            rgb = self._editable_rgba[:, :, :3].astype(np.float32)
        else:
            rgb = rgb_region.astype(np.float32)

        diff = rgb - seed_color.astype(np.float32)
        return np.sqrt(np.sum(diff * diff, axis=2))

    def _adaptive_tolerance_mask(self, x: int, y: int) -> np.ndarray:
        rgb = self._editable_rgba[:, :, :3].astype(np.float32)
        alpha = self._editable_rgba[:, :, 3].astype(np.float32)

        seed_color = self._sample_seed_color(x, y)
        distance = self._compute_color_distance(seed_color)

        h, w = alpha.shape
        x0 = max(0, x - 2)
        x1 = min(w, x + 3)
        y0 = max(0, y - 2)
        y1 = min(h, y + 3)

        local_patch = rgb[y0:y1, x0:x1]
        local_seed_dist = np.sqrt(np.sum((local_patch - seed_color) ** 2, axis=2))

        local_mean = float(np.mean(local_seed_dist)) if local_seed_dist.size else 0.0
        local_std = float(np.std(local_seed_dist)) if local_seed_dist.size else 0.0

        adaptive_bonus = min(18.0, local_mean * 0.35 + local_std * 0.8)
        effective_tolerance = float(self._tolerance) + adaptive_bonus
        effective_tolerance = max(0.0, min(255.0, effective_tolerance))

        tolerance_mask = distance <= effective_tolerance

        visible_mask = alpha > 8.0
        tolerance_mask &= visible_mask

        return tolerance_mask

    def _adaptive_tolerance_mask_local(self, x: int, y: int, bounds):
        if self._editable_rgba is None or bounds is None:
            return None

        x0, x1, y0, y1 = bounds
        rgba_region = self._editable_rgba[y0:y1, x0:x1]
        rgb_region = rgba_region[:, :, :3].astype(np.float32)
        alpha_region = rgba_region[:, :, 3].astype(np.float32)

        seed_color = self._sample_seed_color(x, y, rgba_region=rgba_region, origin=(x0, y0))
        distance = self._compute_color_distance(seed_color, rgb_region=rgb_region)

        local_x = x - x0
        local_y = y - y0

        h, w = alpha_region.shape
        px0 = max(0, local_x - 2)
        px1 = min(w, local_x + 3)
        py0 = max(0, local_y - 2)
        py1 = min(h, local_y + 3)

        local_patch = rgb_region[py0:py1, px0:px1]
        local_seed_dist = np.sqrt(np.sum((local_patch - seed_color) ** 2, axis=2))

        local_mean = float(np.mean(local_seed_dist)) if local_seed_dist.size else 0.0
        local_std = float(np.std(local_seed_dist)) if local_seed_dist.size else 0.0

        adaptive_bonus = min(18.0, local_mean * 0.35 + local_std * 0.8)
        effective_tolerance = float(self._tolerance) + adaptive_bonus
        effective_tolerance = max(0.0, min(255.0, effective_tolerance))

        tolerance_mask = distance <= effective_tolerance
        visible_mask = alpha_region > 8.0
        tolerance_mask &= visible_mask

        return tolerance_mask

    def _edge_protect_mask(self, rgb_array: np.ndarray, alpha_array: np.ndarray | None = None) -> np.ndarray:
        rgb = rgb_array.astype(np.float32)

        if alpha_array is None:
            if self._editable_rgba is not None and self._editable_rgba.shape[:2] == rgb_array.shape[:2]:
                alpha = self._editable_rgba[:, :, 3].astype(np.float32)
            else:
                alpha = None
        else:
            alpha = alpha_array.astype(np.float32)

        diff_right = np.zeros(rgb.shape[:2], dtype=np.float32)
        diff_down = np.zeros(rgb.shape[:2], dtype=np.float32)

        diff_right[:, :-1] = np.sqrt(np.sum((rgb[:, 1:, :] - rgb[:, :-1, :]) ** 2, axis=2))
        diff_down[:-1, :] = np.sqrt(np.sum((rgb[1:, :, :] - rgb[:-1, :, :]) ** 2, axis=2))

        color_edge_strength = np.maximum(diff_right, diff_down)

        if alpha is None:
            protect = np.ones_like(color_edge_strength, dtype=np.float32)
            strong_edge = color_edge_strength >= 60.0
            medium_edge = (color_edge_strength >= 30.0) & (color_edge_strength < 60.0)
            protect[medium_edge] = 0.55
            protect[strong_edge] = 0.25
            return protect

        alpha_norm = alpha / 255.0

        alpha_diff_right = np.zeros(alpha.shape, dtype=np.float32)
        alpha_diff_down = np.zeros(alpha.shape, dtype=np.float32)

        alpha_diff_right[:, :-1] = np.abs(alpha_norm[:, 1:] - alpha_norm[:, :-1])
        alpha_diff_down[:-1, :] = np.abs(alpha_norm[1:, :] - alpha_norm[:-1, :])

        alpha_edge_strength = np.maximum(alpha_diff_right, alpha_diff_down)

        protect = np.ones_like(color_edge_strength, dtype=np.float32)

        medium_color_edge = color_edge_strength >= 24.0
        strong_color_edge = color_edge_strength >= 48.0
        alpha_subject = alpha_norm >= 0.35
        alpha_soft_edge = alpha_edge_strength >= 0.08
        alpha_hard_edge = alpha_edge_strength >= 0.18

        protect[medium_color_edge] = np.minimum(protect[medium_color_edge], 0.70)
        protect[strong_color_edge] = np.minimum(protect[strong_color_edge], 0.45)

        soft_subject_mask = alpha_subject & alpha_soft_edge
        strong_subject_mask = alpha_subject & alpha_hard_edge

        protect[soft_subject_mask] = np.minimum(protect[soft_subject_mask], 0.42)
        protect[strong_subject_mask] = np.minimum(protect[strong_subject_mask], 0.18)

        dense_subject_mask = alpha_norm >= 0.75
        protect[dense_subject_mask & medium_color_edge] = np.minimum(
            protect[dense_subject_mask & medium_color_edge],
            0.30,
        )

        return np.clip(protect, 0.0, 1.0)

    def _connected_region_mask(self, seed_x: int, seed_y: int, base_mask: np.ndarray) -> np.ndarray:
        height, width = base_mask.shape
        if seed_x < 0 or seed_y < 0 or seed_x >= width or seed_y >= height:
            return np.zeros_like(base_mask, dtype=bool)

        if not base_mask[seed_y, seed_x]:
            return np.zeros_like(base_mask, dtype=bool)

        visited = np.zeros_like(base_mask, dtype=bool)
        connected = np.zeros_like(base_mask, dtype=bool)

        queue = deque()
        queue.append((seed_x, seed_y))
        visited[seed_y, seed_x] = True

        while queue:
            px, py = queue.popleft()

            if not base_mask[py, px]:
                continue

            connected[py, px] = True

            neighbors = (
                (px + 1, py),
                (px - 1, py),
                (px, py + 1),
                (px, py - 1),
            )

            for nx, ny in neighbors:
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                if visited[ny, nx]:
                    continue
                visited[ny, nx] = True
                if base_mask[ny, nx]:
                    queue.append((nx, ny))

        return connected

    def _connected_region_mask_local(self, seed_x: int, seed_y: int, base_mask: np.ndarray, bounds):
        if bounds is None:
            return np.zeros_like(base_mask, dtype=bool)

        x0, x1, y0, y1 = bounds
        local_x = seed_x - x0
        local_y = seed_y - y0
        return self._connected_region_mask(local_x, local_y, base_mask)

    def _brush_erase(self, x: int, y: int) -> bool:
        if self._editable_rgba is None:
            return False

        weight_mask = self._brush_weight_mask(x, y)
        if weight_mask is None:
            return False

        strength = max(0.0, min(1.0, self._opacity / 100.0))
        if strength <= 0.0:
            return False

        before_alpha = self._editable_rgba[:, :, 3].astype(np.float32)
        effective_strength = weight_mask * strength

        new_alpha = before_alpha * (1.0 - effective_strength)
        self._editable_rgba[:, :, 3] = np.clip(new_alpha, 0, 255).astype(np.uint8)

        return not np.array_equal(before_alpha.astype(np.uint8), self._editable_rgba[:, :, 3])

    def _brush_restore(self, x: int, y: int) -> bool:
        if self._editable_rgba is None or self._restore_source_rgba is None:
            return False

        weight_mask = self._brush_weight_mask(x, y)
        if weight_mask is None:
            return False

        strength = max(0.0, min(1.0, self._opacity / 100.0))
        if strength <= 0.0:
            return False

        before_rgba = self._editable_rgba.copy().astype(np.float32)
        source_rgba = self._restore_source_rgba.astype(np.float32)

        effective_strength = (weight_mask * strength)[..., np.newaxis]
        blended = before_rgba + ((source_rgba - before_rgba) * effective_strength)

        self._editable_rgba = np.clip(blended, 0, 255).astype(np.uint8)
        return not np.array_equal(before_rgba.astype(np.uint8), self._editable_rgba)

    def _magic_erase(self, x: int, y: int) -> bool:
        if self._editable_rgba is None:
            return False

        before_alpha = self._editable_rgba[:, :, 3].astype(np.float32).copy()
        strength_scale = max(0.0, min(1.0, self._opacity / 100.0))

        if self._apply_mode == "Brush":
            brush_bounds = self._get_brush_bounds(x, y)
            match_bounds = self._get_match_bounds(x, y)

            if brush_bounds is None or match_bounds is None:
                return False

            bx0, bx1, by0, by1 = brush_bounds
            mx0, mx1, my0, my1 = match_bounds

            tolerance_mask = self._adaptive_tolerance_mask_local(x, y, match_bounds)
            if tolerance_mask is None:
                return False

            if self._magic_mode == "Connected Region":
                match_mask_large = self._connected_region_mask_local(x, y, tolerance_mask, match_bounds)
            else:
                match_mask_large = tolerance_mask

            if not np.any(match_mask_large):
                return False

            local_brush_weights = self._local_brush_weight_mask(x, y, brush_bounds)
            if local_brush_weights is None:
                return False

            match_slice_y0 = by0 - my0
            match_slice_y1 = by1 - my0
            match_slice_x0 = bx0 - mx0
            match_slice_x1 = bx1 - mx0

            local_match_mask = match_mask_large[match_slice_y0:match_slice_y1, match_slice_x0:match_slice_x1]
            final_strength = local_brush_weights * local_match_mask.astype(np.float32)

            if self._edge_protect_enabled:
                local_rgb = self._editable_rgba[by0:by1, bx0:bx1, :3]
                local_alpha = self._editable_rgba[by0:by1, bx0:bx1, 3]
                final_strength *= self._edge_protect_mask(local_rgb, local_alpha)

            final_strength *= strength_scale

            alpha_region = self._editable_rgba[by0:by1, bx0:bx1, 3].astype(np.float32)
            new_alpha_region = alpha_region * (1.0 - final_strength)
            self._editable_rgba[by0:by1, bx0:bx1, 3] = np.clip(new_alpha_region, 0, 255).astype(np.uint8)

            return not np.array_equal(before_alpha.astype(np.uint8), self._editable_rgba[:, :, 3])

        alpha = self._editable_rgba[:, :, 3].astype(np.float32)
        tolerance_mask = self._adaptive_tolerance_mask(x, y)

        if self._magic_mode == "Connected Region":
            match_mask = self._connected_region_mask(x, y, tolerance_mask)
        else:
            match_mask = tolerance_mask

        if not np.any(match_mask):
            return False

        final_strength = match_mask.astype(np.float32)

        if self._edge_protect_enabled:
            final_strength *= self._edge_protect_mask(self._editable_rgba[:, :, :3])

        final_strength *= strength_scale

        alpha = alpha * (1.0 - final_strength)
        self._editable_rgba[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
        return not np.array_equal(before_alpha.astype(np.uint8), self._editable_rgba[:, :, 3])

    def _background_erase(self, x: int, y: int) -> bool:
        if self._editable_rgba is None:
            return False

        before_alpha = self._editable_rgba[:, :, 3].astype(np.float32).copy()
        strength_scale = max(0.0, min(1.0, self._opacity / 100.0))

        if self._apply_mode == "Brush":
            brush_bounds = self._get_brush_bounds(x, y)
            match_bounds = self._get_match_bounds(x, y)

            if brush_bounds is None or match_bounds is None:
                return False

            bx0, bx1, by0, by1 = brush_bounds
            mx0, mx1, my0, my1 = match_bounds

            tolerance_mask = self._adaptive_tolerance_mask_local(x, y, match_bounds)
            if tolerance_mask is None:
                return False

            match_mask_large = self._connected_region_mask_local(x, y, tolerance_mask, match_bounds)
            if not np.any(match_mask_large):
                return False

            local_brush_weights = self._local_brush_weight_mask(x, y, brush_bounds)
            if local_brush_weights is None:
                return False

            match_slice_y0 = by0 - my0
            match_slice_y1 = by1 - my0
            match_slice_x0 = bx0 - mx0
            match_slice_x1 = bx1 - mx0

            local_match_mask = match_mask_large[match_slice_y0:match_slice_y1, match_slice_x0:match_slice_x1]
            final_strength = local_brush_weights * local_match_mask.astype(np.float32)

            if self._edge_protect_enabled:
                local_rgb = self._editable_rgba[by0:by1, bx0:bx1, :3]
                local_alpha = self._editable_rgba[by0:by1, bx0:bx1, 3]
                final_strength *= self._edge_protect_mask(local_rgb, local_alpha)

            final_strength *= strength_scale

            alpha_region = self._editable_rgba[by0:by1, bx0:bx1, 3].astype(np.float32)
            new_alpha_region = alpha_region * (1.0 - final_strength)
            self._editable_rgba[by0:by1, bx0:bx1, 3] = np.clip(new_alpha_region, 0, 255).astype(np.uint8)

            return not np.array_equal(before_alpha.astype(np.uint8), self._editable_rgba[:, :, 3])

        alpha = self._editable_rgba[:, :, 3].astype(np.float32)
        tolerance_mask = self._adaptive_tolerance_mask(x, y)
        match_mask = self._connected_region_mask(x, y, tolerance_mask)

        if not np.any(match_mask):
            return False

        final_strength = match_mask.astype(np.float32)

        if self._edge_protect_enabled:
            final_strength *= self._edge_protect_mask(self._editable_rgba[:, :, :3])

        final_strength *= strength_scale

        alpha = alpha * (1.0 - final_strength)
        self._editable_rgba[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
        return not np.array_equal(before_alpha.astype(np.uint8), self._editable_rgba[:, :, 3])

    def _sync_pil_from_rgba(self):
        self._editable_after_image_pil = Image.fromarray(self._editable_rgba, "RGBA")

    def _save_edited_preview(self):
        if self._editable_after_image_pil is None or self._editable_save_path is None:
            return

        self._editable_after_image_pil.save(self._editable_save_path, format="PNG")
        self.image_edited.emit(str(self._editable_save_path))
        self._save_history_snapshot()

    def _finish_edit_update(self):
        self._sync_pil_from_rgba()
        self._save_edited_preview()
        self._current_mode = "after"
        self._load_current_mode_pixmap()

    def reset_edits(self):
        if self._edit_reset_baseline_rgba is None:
            return

        self._editable_rgba = self._edit_reset_baseline_rgba.copy()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._pending_undo_state = None
        self._stroke_changed = False

        self._sync_pil_from_rgba()
        self._save_edited_preview()
        self._current_mode = "after"
        self._interaction_mode = "edit"
        self._load_current_mode_pixmap()
        self.edits_reset.emit()
        self._save_history_snapshot()

    def undo(self):
        if self._editable_rgba is None:
            return

        if self._undo_stack:
            self._redo_stack.append(self._editable_rgba.copy())
            self._editable_rgba = self._undo_stack.pop()
        elif self._history_baseline_rgba is not None and not np.array_equal(self._editable_rgba, self._history_baseline_rgba):
            self._redo_stack.append(self._editable_rgba.copy())
            self._editable_rgba = self._history_baseline_rgba.copy()
        else:
            return

        self._pending_undo_state = None
        self._stroke_changed = False

        self._sync_pil_from_rgba()
        self._save_edited_preview()
        self._current_mode = "after"
        self._interaction_mode = "edit"
        self._load_current_mode_pixmap()
        self._save_history_snapshot()

    def redo(self):
        if not self._redo_stack or self._editable_rgba is None:
            return

        self._undo_stack.append(self._editable_rgba.copy())
        self._editable_rgba = self._redo_stack.pop()

        self._pending_undo_state = None
        self._stroke_changed = False

        self._sync_pil_from_rgba()
        self._save_edited_preview()
        self._current_mode = "after"
        self._interaction_mode = "edit"
        self._load_current_mode_pixmap()
        self._save_history_snapshot()
