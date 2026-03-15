from collections import deque
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QSizePolicy,
    QScrollArea,
    QHBoxLayout,
    QPushButton,
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


class PreviewCanvas(QFrame):

    image_edited = Signal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("previewCanvas")
        self.setFrameShape(QFrame.StyledPanel)

        self._current_pixmap = None
        self._zoom_factor = 1.0

        self._before_image_pil = None
        self._editable_after_image_pil = None
        self._editable_rgba = None

        self._interaction_mode = "preview"
        self._current_mode = "before"

        self._tool_name = "Erase"
        self._apply_mode = "Brush"

        self._brush_size = 40
        self._tolerance = 35

        self._magic_mode = "Connected Region"

        self._mouse_down = False
        self._last_image_point = None

        self._undo_stack = []
        self._redo_stack = []

        layout = QVBoxLayout(self)

        self.title_label = QLabel("Preview")

        toolbar = QHBoxLayout()

        self.preview_mode_btn = QPushButton("Preview Mode ✓")
        self.edit_mode_btn = QPushButton("Edit Mode")

        self.before_btn = QPushButton("Before")
        self.after_btn = QPushButton("After")

        self.undo_btn = QPushButton("Undo")
        self.redo_btn = QPushButton("Redo")

        self.zoom_in_btn = QPushButton("Zoom +")
        self.zoom_out_btn = QPushButton("Zoom -")

        toolbar.addWidget(self.preview_mode_btn)
        toolbar.addWidget(self.edit_mode_btn)
        toolbar.addWidget(self.before_btn)
        toolbar.addWidget(self.after_btn)
        toolbar.addWidget(self.undo_btn)
        toolbar.addWidget(self.redo_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.zoom_in_btn)
        toolbar.addWidget(self.zoom_out_btn)

        self.image_label = _CanvasLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setMinimumSize(200, 200)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(False)

        layout.addWidget(self.title_label)
        layout.addLayout(toolbar)
        layout.addWidget(self.scroll_area)

        self.preview_mode_btn.clicked.connect(self.set_preview_mode)
        self.edit_mode_btn.clicked.connect(self.set_edit_mode)
        self.before_btn.clicked.connect(self.show_before)
        self.after_btn.clicked.connect(self.show_after)
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn.clicked.connect(self.redo)

    def set_magic_mode(self, mode: str):
        self._magic_mode = mode

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
        self._tolerance = tolerance

    def set_preview_images(self, before_image_path, after_image_path=None, **_):

        if before_image_path and Path(before_image_path).exists():
            with Image.open(before_image_path) as img:
                self._before_image_pil = img.convert("RGBA")

        if after_image_path and Path(after_image_path).exists():
            with Image.open(after_image_path) as img:
                self._editable_after_image_pil = img.convert("RGBA")

        if self._editable_after_image_pil is not None:
            self._editable_rgba = np.array(self._editable_after_image_pil)

        self._load_current_mode_pixmap()

    def set_preview_mode(self):
        self._interaction_mode = "preview"

    def set_edit_mode(self):
        self._interaction_mode = "edit"
        self._current_mode = "after"

    def show_before(self):
        self._current_mode = "before"
        self._load_current_mode_pixmap()

    def show_after(self):
        self._current_mode = "after"
        self._load_current_mode_pixmap()

    def _load_current_mode_pixmap(self):

        image = None

        if self._current_mode == "after":
            image = self._editable_after_image_pil
        else:
            image = self._before_image_pil

        if image is None:
            return

        buffer = BytesIO()
        image.save(buffer, format="PNG")

        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue())

        self._current_pixmap = pixmap
        self.image_label.setPixmap(pixmap)

    def handle_mouse_press(self, event):

        if event.button() != Qt.LeftButton:
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

        if self._tool_name == "Magic Erase":
            self._magic_erase(x, y)

        elif self._tool_name == "Background Erase":
            self._background_erase(x, y)

        self._sync_pil_from_rgba()
        self._load_current_mode_pixmap()

    def handle_mouse_move(self, event):
        pass

    def handle_mouse_release(self, event):
        pass

    def _widget_pos_to_image_pos(self, pos: QPoint):

        pixmap = self.image_label.pixmap()

        if pixmap is None:
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

        return img_x, img_y

    def _magic_erase(self, x: int, y: int):

        rgb = self._editable_rgba[:, :, :3].astype(np.int16)
        alpha = self._editable_rgba[:, :, 3].astype(np.float32)

        seed_color = rgb[y, x]

        diff = np.sqrt(np.sum((rgb - seed_color) ** 2, axis=2))
        mask = diff <= self._tolerance

        if self._magic_mode == "Connected Region":

            height, width = mask.shape
            visited = np.zeros_like(mask, dtype=bool)

            stack = [(x, y)]

            while stack:

                px, py = stack.pop()

                if px < 0 or py < 0 or px >= width or py >= height:
                    continue

                if visited[py, px]:
                    continue

                visited[py, px] = True

                if not mask[py, px]:
                    continue

                alpha[py, px] = 0

                stack.append((px + 1, py))
                stack.append((px - 1, py))
                stack.append((px, py + 1))
                stack.append((px, py - 1))

        else:
            alpha[mask] = 0

        self._editable_rgba[:, :, 3] = alpha.astype(np.uint8)

    def _background_erase(self, x: int, y: int):

        rgb = self._editable_rgba[:, :, :3].astype(np.int16)
        alpha = self._editable_rgba[:, :, 3]

        seed_color = rgb[y, x]

        diff = np.sqrt(np.sum((rgb - seed_color) ** 2, axis=2))
        mask = diff <= self._tolerance

        alpha[mask] = 0

        self._editable_rgba[:, :, 3] = alpha

    def _sync_pil_from_rgba(self):
        self._editable_after_image_pil = Image.fromarray(self._editable_rgba, "RGBA")

    def undo(self):

        if not self._undo_stack:
            return

        self._redo_stack.append(self._editable_rgba.copy())
        self._editable_rgba = self._undo_stack.pop()

        self._sync_pil_from_rgba()
        self._load_current_mode_pixmap()

    def redo(self):

        if not self._redo_stack:
            return

        self._undo_stack.append(self._editable_rgba.copy())
        self._editable_rgba = self._redo_stack.pop()

        self._sync_pil_from_rgba()
        self._load_current_mode_pixmap()
