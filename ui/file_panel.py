from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QCheckBox,
    QAbstractItemView,
)


class FilePanel(QFrame):
    item_selected = Signal(int)
    sort_changed = Signal(str)
    status_filter_changed = Signal(str)
    type_filter_changed = Signal(str)
    view_mode_changed = Signal(str)
    checked_items_changed = Signal()

    process_checked_requested = Signal()
    remove_checked_requested = Signal()
    uncheck_completed_requested = Signal()

    def __init__(self):
        super().__init__()

        self.setObjectName("filePanel")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(320)

        self.current_view_mode = "thumbnail"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Files")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.include_subfolders_check = QCheckBox("Include subfolders on drag/drop")
        layout.addWidget(self.include_subfolders_check)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(6)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Sort by", "Date Added", "Name", "Type", "Status"])
        self.sort_combo.setCurrentText("Sort by")

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems(
            ["Filter status", "All", "pending", "processing", "done", "error", "edited"]
        )
        self.status_filter_combo.setCurrentText("Filter status")

        self.type_filter_combo = QComboBox()
        self.type_filter_combo.addItems(["Filter type", "All Types"])
        self.type_filter_combo.setCurrentText("Filter type")

        controls_row.addWidget(self.sort_combo, 1)
        controls_row.addWidget(self.status_filter_combo, 1)
        controls_row.addWidget(self.type_filter_combo, 1)
        layout.addLayout(controls_row)

        top_actions = QHBoxLayout()
        top_actions.setSpacing(6)

        self.check_all_box = QCheckBox("Check All Visible")

        self.thumbnail_view_btn = QPushButton("▦")
        self.thumbnail_view_btn.setCheckable(True)
        self.thumbnail_view_btn.setFixedSize(32, 32)
        self.thumbnail_view_btn.setToolTip("Thumbnail View")

        self.list_view_btn = QPushButton("☰")
        self.list_view_btn.setCheckable(True)
        self.list_view_btn.setFixedSize(32, 32)
        self.list_view_btn.setToolTip("List View")

        top_actions.addWidget(self.check_all_box)
        top_actions.addStretch()
        top_actions.addWidget(self.thumbnail_view_btn)
        top_actions.addWidget(self.list_view_btn)
        layout.addLayout(top_actions)

        counts_row = QHBoxLayout()
        counts_row.setSpacing(12)

        self.visible_count_label = QLabel("Visible: 0")
        self.checked_count_label = QLabel("Checked: 0")

        counts_row.addWidget(self.visible_count_label)
        counts_row.addWidget(self.checked_count_label)
        counts_row.addStretch()
        layout.addLayout(counts_row)

        self.file_view = QListWidget()
        self.file_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_view.setAlternatingRowColors(False)
        self.file_view.setSpacing(10)
        self.file_view.setUniformItemSizes(False)
        self.file_view.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.file_view.setMovement(QListWidget.Movement.Static)
        self.file_view.setWordWrap(True)
        self.file_view.setMinimumHeight(420)
        layout.addWidget(self.file_view, 1)

        checked_row = QHBoxLayout()
        checked_row.setSpacing(6)

        self.process_checked_btn = QPushButton("Process Checked")
        self.remove_checked_btn = QPushButton("Remove Checked")
        self.uncheck_completed_btn = QPushButton("Uncheck Completed")

        checked_row.addWidget(self.process_checked_btn)
        checked_row.addWidget(self.remove_checked_btn)
        checked_row.addWidget(self.uncheck_completed_btn)
        layout.addLayout(checked_row)

        action_row_1 = QHBoxLayout()
        self.remove_selected_btn = QPushButton("Remove Selected")
        self.clear_completed_btn = QPushButton("Clear Completed")
        action_row_1.addWidget(self.remove_selected_btn)
        action_row_1.addWidget(self.clear_completed_btn)
        layout.addLayout(action_row_1)

        action_row_2 = QHBoxLayout()
        self.clear_all_btn = QPushButton("Clear All")
        self.retry_failed_btn = QPushButton("Retry Failed")
        action_row_2.addWidget(self.clear_all_btn)
        action_row_2.addWidget(self.retry_failed_btn)
        layout.addLayout(action_row_2)

        self.open_output_btn = QPushButton("Open Output Folder")
        layout.addWidget(self.open_output_btn)

        self.file_view.currentRowChanged.connect(self._emit_selected_item)
        self.file_view.itemChanged.connect(self._on_item_changed)

        self.sort_combo.currentTextChanged.connect(self._emit_sort_changed)
        self.status_filter_combo.currentTextChanged.connect(self._emit_status_filter_changed)
        self.type_filter_combo.currentTextChanged.connect(self._emit_type_filter_changed)

        self.thumbnail_view_btn.clicked.connect(lambda: self.set_view_mode("thumbnail"))
        self.list_view_btn.clicked.connect(lambda: self.set_view_mode("list"))
        self.check_all_box.toggled.connect(self._toggle_all_visible)

        self.process_checked_btn.clicked.connect(self.process_checked_requested)
        self.remove_checked_btn.clicked.connect(self.remove_checked_requested)
        self.uncheck_completed_btn.clicked.connect(self.uncheck_completed_requested)

        self._update_view_buttons()
        self._apply_view_mode()
        self._update_counts()

    def set_type_filter_options(self, file_types: list[str]):
        current = self.type_filter_combo.currentText()

        self.type_filter_combo.blockSignals(True)
        self.type_filter_combo.clear()
        self.type_filter_combo.addItem("Filter type")
        self.type_filter_combo.addItem("All Types")
        self.type_filter_combo.addItems(file_types)

        if current in ["Filter type", "All Types", *file_types]:
            self.type_filter_combo.setCurrentText(current)
        else:
            self.type_filter_combo.setCurrentText("Filter type")

        self.type_filter_combo.blockSignals(False)

    def set_view_mode(self, mode: str):
        mode = "thumbnail" if mode == "thumbnail" else "list"
        if self.current_view_mode == mode:
            return

        self.current_view_mode = mode
        self._update_view_buttons()
        self._apply_view_mode()
        self.view_mode_changed.emit(mode)

    def _update_view_buttons(self):
        is_thumbnail = self.current_view_mode == "thumbnail"
        self.thumbnail_view_btn.setChecked(is_thumbnail)
        self.list_view_btn.setChecked(not is_thumbnail)

    def _apply_view_mode(self):
        if self.current_view_mode == "thumbnail":
            self.file_view.setViewMode(QListWidget.ViewMode.IconMode)
            self.file_view.setFlow(QListWidget.Flow.LeftToRight)
            self.file_view.setWrapping(True)
            self.file_view.setGridSize(QSize(170, 200))
            self.file_view.setIconSize(QSize(132, 132))
        else:
            self.file_view.setViewMode(QListWidget.ViewMode.ListMode)
            self.file_view.setFlow(QListWidget.Flow.TopToBottom)
            self.file_view.setWrapping(False)
            self.file_view.setGridSize(QSize())
            self.file_view.setIconSize(QSize(56, 56))

    def clear_items(self):
        self.file_view.clear()
        self._sync_master_checkbox()
        self._update_counts()

    def add_item(self, text: str, thumbnail_path: str | None, user_index: int, checked: bool = False):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, user_index)
        item.setFlags(
            item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
        )
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

        if self.current_view_mode == "thumbnail":
            display_text = text.split("\n")[0].strip()
            item.setText(display_text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            item.setSizeHint(QSize(158, 190))
        else:
            item.setText(text)
            item.setSizeHint(QSize(0, 76))

        if thumbnail_path:
            thumb = QPixmap(thumbnail_path)
            if not thumb.isNull():
                if self.current_view_mode == "thumbnail":
                    scaled = thumb.scaled(
                        132,
                        132,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    item.setIcon(QIcon(scaled))
                else:
                    scaled = thumb.scaled(
                        56,
                        56,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    item.setIcon(QIcon(scaled))

        self.file_view.addItem(item)
        self._sync_master_checkbox()
        self._update_counts()

    def set_current_visible_row(self, row: int):
        if 0 <= row < self.file_view.count():
            self.file_view.setCurrentRow(row)

    def get_selected_user_index(self) -> int:
        item = self.file_view.currentItem()
        if item is None:
            return -1

        data = item.data(Qt.ItemDataRole.UserRole)
        return int(data) if data is not None else -1

    def get_checked_user_indices(self) -> list[int]:
        checked = []
        for row in range(self.file_view.count()):
            item = self.file_view.item(row)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data is not None:
                    checked.append(int(data))
        return checked

    def set_checked_user_indices(self, indices: set[int]):
        self.file_view.blockSignals(True)
        for row in range(self.file_view.count()):
            item = self.file_view.item(row)
            if item is None:
                continue
            user_index = item.data(Qt.ItemDataRole.UserRole)
            item.setCheckState(
                Qt.CheckState.Checked if user_index in indices else Qt.CheckState.Unchecked
            )
        self.file_view.blockSignals(False)
        self._sync_master_checkbox()
        self._update_counts()
        self.checked_items_changed.emit()

    def _toggle_all_visible(self, checked: bool):
        self.file_view.blockSignals(True)
        for row in range(self.file_view.count()):
            item = self.file_view.item(row)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.file_view.blockSignals(False)
        self._update_counts()
        self.checked_items_changed.emit()

    def _sync_master_checkbox(self):
        total = self.file_view.count()
        checked_count = 0

        for row in range(total):
            item = self.file_view.item(row)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                checked_count += 1

        self.check_all_box.blockSignals(True)
        if total == 0 or checked_count == 0:
            self.check_all_box.setCheckState(Qt.CheckState.Unchecked)
        elif checked_count == total:
            self.check_all_box.setCheckState(Qt.CheckState.Checked)
        else:
            self.check_all_box.setCheckState(Qt.CheckState.PartiallyChecked)
        self.check_all_box.blockSignals(False)

    def _update_counts(self):
        visible_count = self.file_view.count()
        checked_count = len(self.get_checked_user_indices())
        self.visible_count_label.setText(f"Visible: {visible_count}")
        self.checked_count_label.setText(f"Checked: {checked_count}")

    def _emit_selected_item(self, row: int):
        if row < 0:
            return
        self.item_selected.emit(row)

    def _on_item_changed(self, _item: QListWidgetItem):
        self._sync_master_checkbox()
        self._update_counts()
        self.checked_items_changed.emit()

    def _emit_sort_changed(self, text: str):
        if text == "Sort by":
            return
        self.sort_changed.emit(text)

    def _emit_status_filter_changed(self, text: str):
        if text == "Filter status":
            self.status_filter_changed.emit("All")
            return
        self.status_filter_changed.emit(text)

    def _emit_type_filter_changed(self, text: str):
        if text == "Filter type":
            self.type_filter_changed.emit("All Types")
            return
        self.type_filter_changed.emit(text)
