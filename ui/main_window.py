from pathlib import Path
import hashlib

from PySide6.QtCore import Qt, QThread, QUrl, QSettings
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QProgressBar,
    QMessageBox,
    QSplitter,
    QFrame,
    QLabel,
    QScrollArea,
    QTextEdit,
)

from ui.file_panel import FilePanel
from ui.preview_canvas import PreviewCanvas
from ui.settings_panel import SettingsPanel

from core.state_manager import StateManager
from core.models import ImageItem

from utils.file_utils import scan_paths
from utils.image_utils import get_image_metadata, create_thumbnail, create_preview_image
from workers.process_worker import ProcessWorker
from workers.full_export_worker import FullExportWorker
from workers.watch_folder_worker import WatchFolderWorker
from processing.export_utils import create_batch_zip


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyBGRemover")
        self.resize(1500, 900)
        self.setMinimumSize(1080, 700)

        self.settings_store = QSettings("MyBGRemover", "MyBGRemover")

        self.state = StateManager()

        self.preview_worker_thread = None
        self.preview_worker = None
        self.export_worker_thread = None
        self.export_worker = None

        self.watch_worker_thread = None
        self.watch_worker = None

        self.processing_active = False
        self.current_processing_index = None

        self.batch_queue = []
        self.batch_total = 0
        self.batch_processed_count = 0
        self.batch_mode = False
        self.cancel_requested = False
        self.batch_exported_files = []

        self.visible_indices = []
        self._next_date_added = 0

        self.cache_root = Path("cache")
        self.thumb_cache_dir = self.cache_root / "thumbs"
        self.preview_cache_dir = self.cache_root / "previews"
        self.processed_preview_cache_dir = self.cache_root / "processed"
        self.edited_preview_cache_dir = self.cache_root / "edited_previews"
        self.fullres_export_cache_dir = self.cache_root / "fullres_exports"

        self.thumb_cache_dir.mkdir(parents=True, exist_ok=True)
        self.preview_cache_dir.mkdir(parents=True, exist_ok=True)
        self.processed_preview_cache_dir.mkdir(parents=True, exist_ok=True)
        self.edited_preview_cache_dir.mkdir(parents=True, exist_ok=True)
        self.fullres_export_cache_dir.mkdir(parents=True, exist_ok=True)

        self.setAcceptDrops(True)

        central = QWidget()
        self.setCentralWidget(central)

        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(8)

        main_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.file_panel = FilePanel()
        self.file_panel.setMinimumWidth(360)
        self.file_panel.setMaximumWidth(520)

        self.preview_canvas = PreviewCanvas()
        self.preview_canvas.setMinimumWidth(300)

        self.settings_panel = SettingsPanel()
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidget(self.settings_panel)
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setMinimumWidth(320)
        self.settings_scroll.setMaximumWidth(380)
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)

        content_splitter.addWidget(self.file_panel)
        content_splitter.addWidget(self.preview_canvas)
        content_splitter.addWidget(self.settings_scroll)
        content_splitter.setSizes([430, 780, 340])
        content_splitter.setStretchFactor(0, 0)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setStretchFactor(2, 0)

        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(22)
        self.progress_bar.setMaximumHeight(24)

        content_layout.addWidget(content_splitter, 1)
        content_layout.addWidget(self.progress_bar, 0)

        self.log_frame = QFrame()
        self.log_frame.setObjectName("logFrame")
        self.log_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.log_frame.setMinimumHeight(100)

        log_layout = QVBoxLayout(self.log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)
        log_layout.setSpacing(8)

        self.log_title = QLabel("Log Panel")
        self.log_title.setObjectName("panelTitle")

        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setPlaceholderText("Status / log activity will appear here...")

        log_layout.addWidget(self.log_title)
        log_layout.addWidget(self.log_panel)

        main_vertical_splitter.addWidget(content_container)
        main_vertical_splitter.addWidget(self.log_frame)
        main_vertical_splitter.setSizes([680, 170])
        main_vertical_splitter.setStretchFactor(0, 1)
        main_vertical_splitter.setStretchFactor(1, 0)

        outer_layout.addWidget(main_vertical_splitter, 1)

        self._apply_basic_styles()
        self._connect_signals()
        self._restore_persistent_settings()
        self._sync_preview_tool_settings()
        self._update_watch_status_label(False, "")

        self.log("MyBGRemover started.")
        self.log("Drag and drop files or folders into the window.")
        self.log("Preview processing uses preview-size images for speed.")
        self.log("Final export uses the original full-resolution source image.")
        self.log("Checked files in the Files panel can be processed separately.")
        self.log("Output folder is preserved between sessions.")
        self.log("Filename suffix includes the selected model name automatically.")
        self.log("ZIP export is available for batch runs.")

    def _apply_basic_styles(self):
        self.setStyleSheet("""
            QWidget {
                background: #2b2b2b;
                color: #f0f0f0;
            }
            QFrame#filePanel, QFrame#previewCanvas, QFrame#settingsPanel, QFrame#logFrame {
                border: 2px solid #808080;
                border-radius: 6px;
                background: #353535;
            }
            QLabel#panelTitle {
                font-size: 16px;
                font-weight: bold;
                color: #ffffff;
                padding: 2px 0 6px 0;
            }
            QListWidget, QTextEdit, QLineEdit, QComboBox, QScrollArea {
                background: #1f1f1f;
                color: #f0f0f0;
                border: 1px solid #666;
            }
            QPushButton {
                background: #4a4a4a;
                color: #ffffff;
                border: 1px solid #777;
                padding: 6px;
            }
            QPushButton:hover {
                background: #5a5a5a;
            }
            QPushButton:disabled {
                background: #3a3a3a;
                color: #999999;
            }
            QCheckBox, QLabel {
                color: #f0f0f0;
            }
            QProgressBar {
                border: 1px solid #666;
                background: #1f1f1f;
                color: #ffffff;
                text-align: center;
            }
        """)

    def _connect_signals(self):
        self.file_panel.item_selected.connect(self.select_item_from_panel)
        self.file_panel.sort_changed.connect(self.rebuild_file_panel)
        self.file_panel.status_filter_changed.connect(self.rebuild_file_panel)
        self.file_panel.type_filter_changed.connect(self.rebuild_file_panel)
        self.file_panel.view_mode_changed.connect(self.rebuild_file_panel)

        self.file_panel.remove_selected_btn.clicked.connect(self.remove_selected_item)
        self.file_panel.clear_completed_btn.clicked.connect(self.clear_completed_items)
        self.file_panel.clear_all_btn.clicked.connect(self.clear_all_items)
        self.file_panel.retry_failed_btn.clicked.connect(self.retry_failed_items)
        self.file_panel.open_output_btn.clicked.connect(self.open_output_folder)

        self.file_panel.process_checked_requested.connect(self.process_checked_items)
        self.file_panel.remove_checked_requested.connect(self.remove_checked_items)
        self.file_panel.uncheck_completed_requested.connect(self.uncheck_completed_items)

        self.settings_panel.process_selected_btn.clicked.connect(self.process_selected_item)
        self.settings_panel.process_all_btn.clicked.connect(self.process_all_items)
        self.settings_panel.cancel_btn.clicked.connect(self.request_cancel)

        self.settings_panel.tool_combo.currentTextChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.apply_mode_combo.currentTextChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.brush_size_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.softness_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.opacity_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.spacing_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.tolerance_slider.valueChanged.connect(self._sync_preview_tool_settings)

        self.settings_panel.watch_enable_check.toggled.connect(self._on_watch_enable_toggled)
        self.settings_panel.output_dir_edit.textChanged.connect(self._persist_output_dir)
        self.settings_panel.naming_edit.textChanged.connect(self._persist_naming_suffix)

        self.preview_canvas.image_edited.connect(self._on_preview_image_edited)

    def _restore_persistent_settings(self):
        output_dir = self.settings_store.value("output_dir", "", type=str)
        naming_suffix = self.settings_store.value("naming_suffix", "_nobg", type=str)

        if output_dir:
            self.settings_panel.output_dir_edit.setText(output_dir)
        if naming_suffix:
            self.settings_panel.naming_edit.setText(naming_suffix)

    def _persist_output_dir(self, text: str):
        self.settings_store.setValue("output_dir", text)

    def _persist_naming_suffix(self, text: str):
        self.settings_store.setValue("naming_suffix", text)

    def _sync_preview_tool_settings(self):
        self.preview_canvas.set_tool_settings(
            tool_name=self.settings_panel.tool_combo.currentText(),
            apply_mode=self.settings_panel.apply_mode_combo.currentText(),
            brush_size=self.settings_panel.brush_size_slider.value(),
            softness=self.settings_panel.softness_slider.value(),
            opacity=self.settings_panel.opacity_slider.value(),
            spacing=self.settings_panel.spacing_slider.value(),
            tolerance=self.settings_panel.tolerance_slider.value(),
        )

    def _short_text(self, text: str, max_len: int = 48) -> str:
        return text if len(text) <= max_len else text[:max_len - 3] + "..."

    def _cache_token(self, path: Path) -> str:
        return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]

    def _get_output_dir(self) -> Path | None:
        output_dir_text = self.settings_panel.output_dir_edit.text().strip()
        if not output_dir_text:
            return None

        output_dir = Path(output_dir_text)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None

        return output_dir if output_dir.exists() and output_dir.is_dir() else None

    def _build_export_suffix(self) -> str:
        model_name = self.settings_panel.model_combo.currentText().strip()
        user_suffix = self.settings_panel.naming_edit.text().strip()

        if not user_suffix:
            user_suffix = "_nobg"

        if not user_suffix.startswith("_"):
            user_suffix = f"_{user_suffix}"

        if model_name:
            return f"_{model_name}{user_suffix}"

        return user_suffix

    def _get_checked_or_all_indices(self) -> list[int]:
        checked = self.file_panel.get_checked_user_indices()
        if checked:
            return checked
        return list(range(len(self.state.items)))

    def _has_processed_preview(self, item: ImageItem) -> bool:
        return (
            item.processed_preview_path is not None
            and Path(item.processed_preview_path).exists()
        )

    def _has_edited_preview(self, item: ImageItem) -> bool:
        return (
            item.edited_preview_path is not None
            and Path(item.edited_preview_path).exists()
        )

    def _update_watch_status_label(self, enabled: bool, folder_path: str):
        if enabled and folder_path:
            self.settings_panel.watch_status_label.setText(f"Watch status: On ({folder_path})")
        else:
            self.settings_panel.watch_status_label.setText("Watch status: Off")

    def _start_watch_folder(self):
        folder_path = self.settings_panel.watch_folder_edit.text().strip()
        include_subfolders = self.settings_panel.watch_include_subfolders_check.isChecked()

        if not folder_path:
            self.log("Watch folder could not start: no folder selected.")
            self.settings_panel.watch_enable_check.blockSignals(True)
            self.settings_panel.watch_enable_check.setChecked(False)
            self.settings_panel.watch_enable_check.blockSignals(False)
            self._update_watch_status_label(False, "")
            return

        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            self.log(f"Watch folder could not start: invalid directory: {folder_path}")
            self.settings_panel.watch_enable_check.blockSignals(True)
            self.settings_panel.watch_enable_check.setChecked(False)
            self.settings_panel.watch_enable_check.blockSignals(False)
            self._update_watch_status_label(False, "")
            return

        if self.watch_worker_thread is not None or self.watch_worker is not None:
            self._stop_watch_folder()

        self.watch_worker_thread = QThread(self)
        self.watch_worker = WatchFolderWorker(
            folder_path=folder_path,
            include_subfolders=include_subfolders,
            poll_interval_seconds=2.0,
        )
        self.watch_worker.moveToThread(self.watch_worker_thread)

        self.watch_worker_thread.started.connect(self.watch_worker.run)
        self.watch_worker.status.connect(self.log)
        self.watch_worker.new_files_detected.connect(self._on_watch_new_files_detected)
        self.watch_worker.error.connect(self._on_watch_error)
        self.watch_worker.finished.connect(self.watch_worker_thread.quit)
        self.watch_worker_thread.finished.connect(self._cleanup_watch_worker)

        self.watch_worker_thread.start()
        self._update_watch_status_label(True, folder_path)

    def _stop_watch_folder(self):
        if self.watch_worker is not None:
            self.watch_worker.stop()

        self._update_watch_status_label(False, "")

    def _cleanup_watch_worker(self):
        if self.watch_worker is not None:
            self.watch_worker.deleteLater()
            self.watch_worker = None

        if self.watch_worker_thread is not None:
            self.watch_worker_thread.deleteLater()
            self.watch_worker_thread = None

    def _on_watch_enable_toggled(self, checked: bool):
        if checked:
            self._start_watch_folder()
        else:
            self._stop_watch_folder()

    def _on_watch_error(self, message: str):
        self.log(f"Watch folder error: {message}")
        self.settings_panel.watch_enable_check.blockSignals(True)
        self.settings_panel.watch_enable_check.setChecked(False)
        self.settings_panel.watch_enable_check.blockSignals(False)
        self._update_watch_status_label(False, "")

    def _on_watch_new_files_detected(self, file_paths: list):
        if not file_paths:
            return

        existing_paths = {str(item.source_path.resolve()) for item in self.state.items}
        added_any = False

        for file_path_str in file_paths:
            path = Path(file_path_str)
            resolved = str(path.resolve())
            if resolved in existing_paths:
                continue

            self._add_image_item(path)
            existing_paths.add(resolved)
            added_any = True

        if added_any:
            self._refresh_type_filter_options()
            self.rebuild_file_panel()

            if self.state.selected_index is None and self.visible_indices:
                self.select_item(self.visible_indices[0])

    def log(self, message: str):
        self.log_panel.append(message)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        if self.processing_active:
            self.log("Drop ignored while processing is active.")
            event.ignore()
            return

        urls = event.mimeData().urls()
        dropped_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        include_subfolders = self.file_panel.include_subfolders_check.isChecked()
        files, skipped = scan_paths(dropped_paths, include_subfolders=include_subfolders)

        existing_paths = {str(item.source_path.resolve()) for item in self.state.items}
        duplicate_files = [f for f in files if str(f.resolve()) in existing_paths]
        new_files = [f for f in files if str(f.resolve()) not in existing_paths]

        if duplicate_files:
            reply = QMessageBox.question(
                self,
                "Duplicates Detected",
                f"{len(duplicate_files)} duplicate file(s) were found.\nAdd duplicates anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                new_files.extend(duplicate_files)

        for path in new_files:
            self._add_image_item(path)

        for path in skipped:
            self.log(f"Skipped unsupported file: {path}")

        self._refresh_type_filter_options()
        self.rebuild_file_panel()

        if new_files and self.state.selected_index is None and self.visible_indices:
            self.select_item(self.visible_indices[0])

        event.acceptProposedAction()

    def _add_image_item(self, path: Path):
        metadata = get_image_metadata(path)
        token = self._cache_token(path)
        thumb_path = self.thumb_cache_dir / f"{token}_thumb.png"
        preview_path = self.preview_cache_dir / f"{token}_preview.png"

        thumb_ok = create_thumbnail(path, thumb_path)
        preview_ok = create_preview_image(path, preview_path)

        item = ImageItem(
            source_path=path,
            filename=path.name,
            file_type=path.suffix.lower(),
            dimensions=metadata["dimensions"],
            dpi=metadata["dpi"],
            thumb_path=thumb_path if thumb_ok else None,
            preview_path=preview_path if preview_ok else None,
            date_added=self._next_date_added,
        )
        self._next_date_added += 1
        self.state.add_item(item)

        if not preview_ok:
            self.log(f"Could not create preview: {path}")
        if not thumb_ok:
            self.log(f"Could not create thumbnail: {path}")

        self.log(f"Loaded: {path}")

    def _refresh_type_filter_options(self):
        file_types = sorted({item.file_type for item in self.state.items})
        self.file_panel.set_type_filter_options(file_types)

    def _item_matches_filter(self, item: ImageItem, status_filter: str, type_filter: str) -> bool:
        effective_status = "All" if status_filter in ("Filter status", "") else status_filter
        effective_type = "All Types" if type_filter in ("Filter type", "") else type_filter

        status_ok = effective_status == "All" or item.status.lower() == effective_status.lower()
        type_ok = effective_type == "All Types" or item.file_type == effective_type
        return status_ok and type_ok

    def _sorted_indices(self) -> list[int]:
        sort_name = self.file_panel.sort_combo.currentText()
        effective_sort = "Date Added" if sort_name == "Sort by" else sort_name

        indices = list(range(len(self.state.items)))

        if effective_sort == "Date Added":
            indices.sort(key=lambda i: self.state.items[i].date_added)
        elif effective_sort == "Name":
            indices.sort(key=lambda i: self.state.items[i].filename.lower())
        elif effective_sort == "Type":
            indices.sort(
                key=lambda i: (
                    self.state.items[i].file_type.lower(),
                    self.state.items[i].filename.lower(),
                )
            )
        elif effective_sort == "Status":
            indices.sort(
                key=lambda i: (
                    self.state.items[i].status.lower(),
                    self.state.items[i].filename.lower(),
                )
            )

        return indices

    def _build_panel_text(self, item: ImageItem) -> str:
        if self.file_panel.current_view_mode == "thumbnail":
            return item.filename

        return (
            f"{self._short_text(item.filename, 42)}\n"
            f"{item.file_type} | {item.dimensions} | DPI: {item.dpi} | {item.status}"
        )

    def rebuild_file_panel(self, *_args):
        selected_index = self.state.selected_index
        checked_indices = set(self.file_panel.get_checked_user_indices())
        status_filter = self.file_panel.status_filter_combo.currentText()
        type_filter = self.file_panel.type_filter_combo.currentText()

        self.file_panel.file_view.blockSignals(True)
        self.file_panel.clear_items()
        self.visible_indices = []

        for item_index in self._sorted_indices():
            item = self.state.items[item_index]
            if not self._item_matches_filter(item, status_filter, type_filter):
                continue

            thumb_path = item.edited_preview_path or item.processed_preview_path or item.thumb_path
            self.file_panel.add_item(
                self._build_panel_text(item),
                str(thumb_path) if thumb_path else None,
                item_index,
                checked=item_index in checked_indices,
            )
            self.visible_indices.append(item_index)

        if selected_index is not None and selected_index in self.visible_indices:
            self.file_panel.set_current_visible_row(self.visible_indices.index(selected_index))
        elif self.visible_indices:
            self.state.set_selected_index(self.visible_indices[0])
            self.file_panel.set_current_visible_row(0)
        else:
            self.state.set_selected_index(None)

        self.file_panel.file_view.blockSignals(False)
        if hasattr(self.file_panel, "_update_counts"):
            self.file_panel._update_counts()

    def _refresh_item_display(self, _index: int):
        self.rebuild_file_panel()

    def select_item_from_panel(self, _visible_row: int):
        real_index = self.file_panel.get_selected_user_index()
        if real_index >= 0:
            self.select_item(real_index, source="panel")

    def select_item(self, index: int, source: str | None = None):
        item = self.state.get_item(index)
        if item is None:
            return

        self.state.set_selected_index(index)

        if source != "panel" and index in self.visible_indices:
            self.file_panel.file_view.blockSignals(True)
            self.file_panel.set_current_visible_row(self.visible_indices.index(index))
            self.file_panel.file_view.blockSignals(False)

        before_path = item.preview_path
        after_path = item.edited_preview_path or item.processed_preview_path
        editable_save_path = self.edited_preview_cache_dir / f"{self._cache_token(item.source_path)}_edited.png"

        if before_path and Path(before_path).exists():
            title_text = (
                f"{self._short_text(item.filename, 60)} | "
                f"{item.dimensions} | DPI: {item.dpi} | {item.status}"
            )

            default_mode = "after" if after_path else "before"

            self.preview_canvas.set_preview_images(
                before_image_path=str(before_path),
                after_image_path=str(after_path) if after_path and Path(after_path).exists() else None,
                title_text=title_text,
                default_mode=default_mode,
                editable_save_path=str(editable_save_path),
            )
        else:
            self.preview_canvas.clear_preview()
            self.log(f"Could not load preview: {item.source_path}")

    def _on_preview_image_edited(self, save_path_str: str):
        selected_index = self.state.selected_index
        if selected_index is None:
            return

        item = self.state.get_item(selected_index)
        if item is None:
            return

        item.edited_preview_path = Path(save_path_str)
        if item.status != "processing":
            item.status = "edited"

        self._refresh_item_display(selected_index)

    def remove_selected_item(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "Wait for processing to finish first.")
            return

        selected_index = self.state.selected_index
        if selected_index is None:
            QMessageBox.information(self, "No Selection", "Select an image first.")
            return

        item = self.state.get_item(selected_index)
        if item is None:
            return

        self.state.items.pop(selected_index)

        for idx, state_item in enumerate(self.state.items):
            state_item.date_added = idx
        self._next_date_added = len(self.state.items)

        self.state.set_selected_index(None)
        self._refresh_type_filter_options()
        self.rebuild_file_panel()
        self.preview_canvas.clear_preview()

        self.log(f"Removed: {item.source_path}")

    def remove_checked_items(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "Wait for processing to finish first.")
            return

        checked = set(self.file_panel.get_checked_user_indices())
        if not checked:
            QMessageBox.information(self, "Nothing Checked", "No checked files to remove.")
            return

        self.state.items = [
            item for idx, item in enumerate(self.state.items)
            if idx not in checked
        ]

        for idx, state_item in enumerate(self.state.items):
            state_item.date_added = idx
        self._next_date_added = len(self.state.items)

        self.state.set_selected_index(None)
        self._refresh_type_filter_options()
        self.rebuild_file_panel()
        self.preview_canvas.clear_preview()
        self.log(f"Removed {len(checked)} checked item(s).")

    def clear_completed_items(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "Wait for processing to finish first.")
            return

        before_count = len(self.state.items)
        self.state.items = [item for item in self.state.items if item.status != "done"]

        for idx, state_item in enumerate(self.state.items):
            state_item.date_added = idx
        self._next_date_added = len(self.state.items)

        removed_count = before_count - len(self.state.items)
        self.state.set_selected_index(None)
        self._refresh_type_filter_options()
        self.rebuild_file_panel()
        self.preview_canvas.clear_preview()

        self.log(f"Cleared completed items: {removed_count}")

    def uncheck_completed_items(self):
        if not hasattr(self.file_panel, "file_view"):
            return

        self.file_panel.file_view.blockSignals(True)
        for i in range(self.file_panel.file_view.count()):
            item = self.file_panel.file_view.item(i)
            if item is None:
                continue

            index = item.data(Qt.ItemDataRole.UserRole)
            if index is None:
                continue

            state_item = self.state.get_item(index)
            if state_item is not None and state_item.status == "done":
                item.setCheckState(Qt.CheckState.Unchecked)

        self.file_panel.file_view.blockSignals(False)

        if hasattr(self.file_panel, "_sync_master_checkbox"):
            self.file_panel._sync_master_checkbox()
        if hasattr(self.file_panel, "_update_counts"):
            self.file_panel._update_counts()

        self.log("Unchecked completed items.")

    def retry_failed_items(self):
        failed_indices = [idx for idx, item in enumerate(self.state.items) if item.status == "error"]
        if not failed_indices:
            self.log("No failed items to retry.")
            return

        for idx in failed_indices:
            item = self.state.items[idx]
            item.status = "pending"
            item.processed_preview_path = None
            item.edited_preview_path = None
            item.output_path = ""

        self.rebuild_file_panel()
        self.log(f"Reset failed items to pending: {len(failed_indices)}")

    def open_output_folder(self):
        output_dir = self._get_output_dir()
        if output_dir is not None and output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))
            self.log(f"Opened output folder: {output_dir}")
            return

        selected_index = self.state.selected_index
        if selected_index is not None:
            item = self.state.get_item(selected_index)
            if item is not None and item.source_path.parent.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.source_path.parent)))
                self.log(f"Opened source folder for selected image: {item.source_path.parent}")
                return

        QMessageBox.information(
            self,
            "Folder Not Available",
            "No valid output folder is set, and no selected image folder could be opened.",
        )

    def process_selected_item(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "An image is already being processed.")
            return

        selected_index = self.state.selected_index
        if selected_index is None:
            QMessageBox.information(self, "No Selection", "Select an image first.")
            return

        item = self.state.get_item(selected_index)
        if item is None:
            QMessageBox.information(self, "No Selection", "Select an image first.")
            return

        if self._get_output_dir() is None:
            QMessageBox.information(
                self,
                "Output Folder Required",
                "Choose a valid output folder before processing.",
            )
            return

        self.batch_mode = False
        self.batch_queue = []
        self.batch_total = 1
        self.batch_processed_count = 0
        self.cancel_requested = False
        self.batch_exported_files = []

        if self._has_processed_preview(item):
            self.log(f"Using existing processed preview for export: {item.filename}")
            self.current_processing_index = selected_index
            item.status = "processing"
            self._refresh_item_display(selected_index)
            self.select_item(selected_index)

            self.processing_active = True
            self._set_processing_controls_enabled(False)
            self.progress_bar.setRange(0, 0)

            self._start_full_export_item(selected_index, apply_preview_edits=self._has_edited_preview(item))
            return

        self._start_preview_processing_item(selected_index)

    def process_checked_items(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "A processing job is already active.")
            return

        if self._get_output_dir() is None:
            QMessageBox.information(
                self,
                "Output Folder Required",
                "Choose a valid output folder before processing.",
            )
            return

        if self.settings_panel.removal_mode_combo.currentText() != "AI Removal":
            QMessageBox.information(
                self,
                "Not Yet Available",
                "Color Removal will be added later. Use AI Removal for now.",
            )
            return

        checked = self.file_panel.get_checked_user_indices()
        if not checked:
            QMessageBox.information(self, "Nothing Checked", "No checked files to process.")
            return

        self.batch_queue = [
            index for index in checked
            if 0 <= index < len(self.state.items)
            and (
                (self.state.items[index].preview_path is not None and Path(self.state.items[index].preview_path).exists())
                or self._has_processed_preview(self.state.items[index])
            )
        ]

        if not self.batch_queue:
            QMessageBox.information(
                self,
                "No Valid Images",
                "The checked files do not have valid preview data to process.",
            )
            return

        self.batch_total = len(self.batch_queue)
        self.batch_processed_count = 0
        self.batch_mode = True
        self.cancel_requested = False
        self.batch_exported_files = []

        self.log(f"Processing {self.batch_total} checked image(s).")
        self._start_next_batch_item()

    def process_all_items(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "A processing job is already active.")
            return

        if not self.state.items:
            QMessageBox.information(self, "No Images", "Load images first.")
            return

        if self._get_output_dir() is None:
            QMessageBox.information(
                self,
                "Output Folder Required",
                "Choose a valid output folder before processing.",
            )
            return

        if self.settings_panel.removal_mode_combo.currentText() != "AI Removal":
            QMessageBox.information(
                self,
                "Not Yet Available",
                "Color Removal will be added later. Use AI Removal for now.",
            )
            return

        target_indices = self._get_checked_or_all_indices()

        self.batch_queue = [
            index
            for index in target_indices
            if 0 <= index < len(self.state.items)
            and (
                (self.state.items[index].preview_path is not None and Path(self.state.items[index].preview_path).exists())
                or self._has_processed_preview(self.state.items[index])
            )
        ]

        if not self.batch_queue:
            QMessageBox.information(
                self,
                "No Valid Images",
                "There are no valid checked images to process. If nothing is checked, Process All uses every loaded image.",
            )
            return

        self.batch_mode = True
        self.batch_total = len(self.batch_queue)
        self.batch_processed_count = 0
        self.cancel_requested = False
        self.batch_exported_files = []

        self.log(f"Starting batch processing for {self.batch_total} image(s).")
        self._start_next_batch_item()

    def request_cancel(self):
        if not self.processing_active:
            self.log("No active processing job to cancel.")
            return

        self.cancel_requested = True
        self.log("Cancel requested. The current image will finish, then the batch will stop.")

    def _start_next_batch_item(self):
        if self.cancel_requested:
            self.log("Batch canceled by user.")
            self._finish_processing_session()
            return

        if not self.batch_queue:
            self.log("Batch processing complete.")
            self._finish_processing_session(final_progress=100)
            return

        self._start_preview_processing_item(self.batch_queue.pop(0))

    def _set_processing_controls_enabled(self, enabled: bool):
        self.settings_panel.process_selected_btn.setEnabled(enabled)
        self.settings_panel.process_all_btn.setEnabled(enabled)
        if hasattr(self.file_panel, "process_checked_btn"):
            self.file_panel.process_checked_btn.setEnabled(enabled)

    def _update_batch_progress_busy(self):
        completed_percent = int((self.batch_processed_count / self.batch_total) * 100) if self.batch_total > 0 else 0
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(completed_percent)

    def _update_batch_progress(self):
        percent = int((self.batch_processed_count / self.batch_total) * 100) if self.batch_total > 0 else 0
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(percent)

    def _start_preview_processing_item(self, item_index: int):
        item = self.state.get_item(item_index)
        if item is None:
            if self.batch_mode:
                self._start_next_batch_item()
            return

        if self._has_processed_preview(item):
            self.log(f"Skipping preview reprocess and using existing processed preview: {item.filename}")

            self.current_processing_index = item_index
            item.status = "processing"
            self._refresh_item_display(item_index)
            self.select_item(item_index)

            self.processing_active = True
            self._set_processing_controls_enabled(False)

            if self.batch_mode:
                self._update_batch_progress_busy()
            else:
                self.progress_bar.setRange(0, 0)

            self._start_full_export_item(item_index, apply_preview_edits=self._has_edited_preview(item))
            return

        if item.preview_path is None or not Path(item.preview_path).exists():
            self.log(f"Cannot process preview for: {item.source_path}")
            item.status = "error"
            self._refresh_item_display(item_index)

            if self.batch_mode:
                self.batch_processed_count += 1
                self._update_batch_progress()
                self._start_next_batch_item()
            return

        if self.processing_active:
            self.log("Processing is already active; new start request ignored.")
            return

        model_name = self.settings_panel.model_combo.currentText()
        token = self._cache_token(item.source_path)
        processed_preview_path = self.processed_preview_cache_dir / f"{token}_processed.png"

        self.current_processing_index = item_index
        item.status = "processing"
        item.edited_preview_path = None
        self._refresh_item_display(item_index)
        self.select_item(item_index)

        self.processing_active = True
        self._set_processing_controls_enabled(False)

        if self.batch_mode:
            self._update_batch_progress_busy()
        else:
            self.progress_bar.setRange(0, 0)

        self.log(f"Preview processing item {item_index + 1}: {item.filename}")
        self.log(f"Model: {model_name}")
        self.log(f"Input preview path: {item.preview_path}")
        self.log(f"Output preview path: {processed_preview_path}")

        self.preview_worker_thread = QThread(self)
        self.preview_worker = ProcessWorker(
            item_index=item_index,
            input_path=Path(item.preview_path),
            output_path=processed_preview_path,
            model_name=model_name,
        )
        self.preview_worker.moveToThread(self.preview_worker_thread)

        self.preview_worker_thread.started.connect(self.preview_worker.run)
        self.preview_worker.status.connect(self.log)
        self.preview_worker.finished.connect(self._on_preview_process_finished)
        self.preview_worker.error.connect(self._on_preview_process_error)
        self.preview_worker.finished.connect(self.preview_worker_thread.quit)
        self.preview_worker.error.connect(self.preview_worker_thread.quit)
        self.preview_worker_thread.finished.connect(self._cleanup_preview_worker)

        self.preview_worker_thread.start()

    def _cleanup_preview_worker(self):
        if self.preview_worker is not None:
            self.preview_worker.deleteLater()
            self.preview_worker = None

        if self.preview_worker_thread is not None:
            self.preview_worker_thread.deleteLater()
            self.preview_worker_thread = None

    def _start_full_export_item(self, item_index: int, apply_preview_edits: bool = False):
        item = self.state.get_item(item_index)
        if item is None:
            self._handle_post_item_completion()
            return

        output_dir = self._get_output_dir()
        if output_dir is None:
            item.status = "error"
            self.log("Export failed: output directory is not available.")
            self._refresh_item_display(item_index)
            self._handle_post_item_completion(error=True)
            return

        model_name = self.settings_panel.model_combo.currentText()
        suffix = self._build_export_suffix()
        output_format = self.settings_panel.output_format_combo.currentText().upper()
        background_mode = self.settings_panel.background_mode_combo.currentText()
        background_color = self.settings_panel.background_color_combo.currentText()

        token = self._cache_token(item.source_path)
        fullres_cache_path = self.fullres_export_cache_dir / f"{token}_fullres.png"

        base_preview_mask_path = item.processed_preview_path if self._has_processed_preview(item) else None
        edited_preview_mask_path = item.edited_preview_path if self._has_edited_preview(item) else None

        self.log(f"Starting full-resolution export for: {item.filename}")
        self.log(f"Source image: {item.source_path}")
        self.log(f"Full-res temp path: {fullres_cache_path}")
        self.log(f"Filename suffix: {suffix}")
        self.log(f"Apply preview edits: {'yes' if apply_preview_edits and edited_preview_mask_path else 'no'}")

        self.export_worker_thread = QThread(self)
        self.export_worker = FullExportWorker(
            item_index=item_index,
            source_path=item.source_path,
            processed_cache_path=fullres_cache_path,
            output_dir=output_dir,
            output_format=output_format,
            suffix=suffix,
            model_name=model_name,
            background_mode=background_mode,
            background_color_name=background_color,
            base_preview_mask_path=base_preview_mask_path,
            edited_preview_mask_path=edited_preview_mask_path,
            apply_preview_edits=(
                apply_preview_edits
                and base_preview_mask_path is not None
                and edited_preview_mask_path is not None
            ),
        )
        self.export_worker.moveToThread(self.export_worker_thread)

        self.export_worker_thread.started.connect(self.export_worker.run)
        self.export_worker.status.connect(self.log)
        self.export_worker.finished.connect(self._on_full_export_finished)
        self.export_worker.error.connect(self._on_full_export_error)
        self.export_worker.finished.connect(self.export_worker_thread.quit)
        self.export_worker.error.connect(self.export_worker_thread.quit)
        self.export_worker_thread.finished.connect(self._cleanup_export_worker)

        self.export_worker_thread.start()

    def _cleanup_export_worker(self):
        if self.export_worker is not None:
            self.export_worker.deleteLater()
            self.export_worker = None

        if self.export_worker_thread is not None:
            self.export_worker_thread.deleteLater()
            self.export_worker_thread = None

    def _on_preview_process_finished(self, item_index: int, processed_preview_path_str: str):
        item = self.state.get_item(item_index)
        if item is None:
            self._handle_post_item_completion(error=True)
            return

        processed_preview_path = Path(processed_preview_path_str)
        item.processed_preview_path = processed_preview_path
        item.edited_preview_path = None

        self.log(f"Preview processing complete: {processed_preview_path}")
        if processed_preview_path.exists():
            self.log(f"Processed preview size: {processed_preview_path.stat().st_size} bytes")

        self._refresh_item_display(item_index)
        self.select_item(item_index)
        self._start_full_export_item(item_index, apply_preview_edits=False)

    def _on_preview_process_error(self, item_index: int, error_message: str):
        item = self.state.get_item(item_index)
        if item is not None:
            item.status = "error"
            item.processed_preview_path = None
            item.edited_preview_path = None
            self._refresh_item_display(item_index)

        self.log(f"Preview processing failed for item index {item_index}")
        self.log(f"Error: {error_message}")
        self._handle_post_item_completion(error=True)

    def _on_full_export_finished(self, item_index: int, _fullres_cache_path: str, output_path_str: str):
        item = self.state.get_item(item_index)
        if item is not None:
            item.output_path = output_path_str
            item.status = "done"
            self.log(f"Exported: {output_path_str}")
            self._refresh_item_display(item_index)
            self.select_item(item_index)

        if self.batch_mode:
            self.batch_exported_files.append(output_path_str)

        self._handle_post_item_completion()

    def _on_full_export_error(self, item_index: int, error_message: str):
        item = self.state.get_item(item_index)
        if item is not None:
            item.status = "error"
            self._refresh_item_display(item_index)

        self.log(f"Full export failed for item index {item_index}")
        self.log(f"Error: {error_message}")
        self._handle_post_item_completion(error=True)

    def _handle_post_item_completion(self, error: bool = False):
        self.current_processing_index = None

        if self.batch_mode:
            self.batch_processed_count += 1
            self._update_batch_progress()
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0 if error else 100)

        self.processing_active = False

        if self.batch_mode:
            self._start_next_batch_item()
        else:
            self._set_processing_controls_enabled(True)

    def _finish_processing_session(self, final_progress: int | None = None):
        if (
            self.settings_panel.export_zip_check.isChecked()
            and self.batch_exported_files
        ):
            output_dir = self._get_output_dir()
            if output_dir is not None:
                ok, zip_path, err = create_batch_zip(
                    self.batch_exported_files,
                    output_dir,
                )
                if ok:
                    self.log(f"ZIP export created: {zip_path}")
                else:
                    self.log(f"ZIP export failed: {err}")

        self.batch_mode = False
        self.batch_queue = []
        self.batch_total = 0
        self.batch_processed_count = 0
        self.cancel_requested = False
        self.current_processing_index = None
        self.batch_exported_files = []

        self._set_processing_controls_enabled(True)

        self.progress_bar.setRange(0, 100)
        if final_progress is not None:
            self.progress_bar.setValue(final_progress)

    def clear_all_items(self):
        if self.processing_active:
            QMessageBox.information(
                self,
                "Processing",
                "Wait for the current processing job to finish first.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Clear All",
            "Remove all loaded items from MyBGRemover?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.state.clear_all()
        self.file_panel.clear_items()
        self.preview_canvas.clear_preview()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.batch_queue = []
        self.batch_total = 0
        self.batch_processed_count = 0
        self.batch_mode = False
        self.cancel_requested = False
        self.batch_exported_files = []
        self.visible_indices = []
        self._refresh_type_filter_options()

        self.log("Cleared all items.")

    def closeEvent(self, event):
        self._stop_watch_folder()
        self.settings_store.sync()
        super().closeEvent(event)
