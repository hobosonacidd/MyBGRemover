from pathlib import Path
import hashlib

from PySide6.QtCore import Qt, QThread, QUrl, QSettings, QSignalBlocker, QTimer
from PySide6.QtGui import QDesktopServices, QAction, QKeySequence
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
    QFileDialog,
)

from ui.file_panel import FilePanel
from ui.preview_canvas import PreviewCanvas
from ui.settings_panel import SettingsPanel
from ui.preferences_dialog import PreferencesDialog

from core.state_manager import StateManager
from core.models import ImageItem

from utils.file_utils import scan_paths
from utils.image_utils import get_image_metadata, create_thumbnail, create_preview_image
from workers.process_worker import ProcessWorker
from workers.full_export_worker import FullExportWorker
from workers.watch_folder_worker import WatchFolderWorker
from processing.export_utils import create_batch_zip


class MainWindow(QMainWindow):

    def _finalize_preview_thread(self):
        if self.preview_worker_thread is not None and self.preview_worker_thread.isRunning():
            self.preview_worker_thread.quit()
            self.preview_worker_thread.wait(10000)

        if self.preview_worker is not None:
            self.preview_worker.deleteLater()
            self.preview_worker = None

        if self.preview_worker_thread is not None:
            self.preview_worker_thread.deleteLater()
            self.preview_worker_thread = None

    def _finalize_export_thread(self):
        if self.export_worker_thread is not None and self.export_worker_thread.isRunning():
            self.export_worker_thread.quit()
            self.export_worker_thread.wait(10000)

        if self.export_worker is not None:
            self.export_worker.deleteLater()
            self.export_worker = None

        if self.export_worker_thread is not None:
            self.export_worker_thread.deleteLater()
            self.export_worker_thread = None

    def _shutdown_running_threads(self):
        if self.preview_worker_thread is not None and self.preview_worker_thread.isRunning():
            self.preview_worker_thread.quit()
            self.preview_worker_thread.wait(3000)

        if self.export_worker_thread is not None and self.export_worker_thread.isRunning():
            self.export_worker_thread.quit()
            self.export_worker_thread.wait(3000)

        if self.watch_worker is not None:
            self.watch_worker.stop()

        if self.watch_worker_thread is not None and self.watch_worker_thread.isRunning():
            self.watch_worker_thread.quit()
            self.watch_worker_thread.wait(3000)

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
        self.batch_action = None
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

        self._create_menu_bar()

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
        self._update_watch_status_label(False, "")
        self.preview_canvas.clear_preview()
        QTimer.singleShot(0, self._finalize_editor_restore_after_startup)

        self.log("MyBGRemover started.")
        self.log("Drag and drop files or folders into the window.")
        self.log("Process = preview/background removal only.")
        self.log("Export = final full-resolution file output.")
        self.log("Preview processing uses preview-size images for speed.")
        self.log("Final export uses the original full-resolution source image.")
        self.log("Output folder is preserved between sessions.")
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

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        view_menu = menu_bar.addMenu("View")
        tools_menu = menu_bar.addMenu("Tools")
        preferences_menu = menu_bar.addMenu("Preferences")
        help_menu = menu_bar.addMenu("Help")

        self.open_files_action = QAction("Open Files", self)
        self.open_files_action.triggered.connect(self.open_files_dialog)
        file_menu.addAction(self.open_files_action)

        self.open_folder_action = QAction("Open Folder", self)
        self.open_folder_action.triggered.connect(self.open_folder_dialog)
        file_menu.addAction(self.open_folder_action)

        self.recent_menu = file_menu.addMenu("Open Recent")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        self.open_output_action = QAction("Open Output Folder", self)
        self.open_output_action.triggered.connect(self.open_output_folder)
        file_menu.addAction(self.open_output_action)

        file_menu.addSeparator()

        self.clear_all_action = QAction("Clear All Items", self)
        self.clear_all_action.triggered.connect(self.clear_all_items)
        file_menu.addAction(self.clear_all_action)

        file_menu.addSeparator()

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        self.undo_action = QAction("Undo", self)
        self.undo_action.triggered.connect(self.preview_canvas.undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.triggered.connect(self.preview_canvas.redo)
        edit_menu.addAction(self.redo_action)

        self.reset_edits_action = QAction("Reset Edits", self)
        self.reset_edits_action.triggered.connect(self.preview_canvas.reset_edits)
        edit_menu.addAction(self.reset_edits_action)

        edit_menu.addSeparator()

        self.check_all_action = QAction("Check All", self)
        self.check_all_action.triggered.connect(self._check_all_visible_items)
        edit_menu.addAction(self.check_all_action)

        self.uncheck_all_action = QAction("Uncheck All", self)
        self.uncheck_all_action.triggered.connect(self._uncheck_all_visible_items)
        edit_menu.addAction(self.uncheck_all_action)

        edit_menu.addSeparator()

        self.remove_checked_action = QAction("Remove Checked", self)
        self.remove_checked_action.triggered.connect(self.remove_checked_items)
        edit_menu.addAction(self.remove_checked_action)

        self.reset_checked_action = QAction("Reset Checked to Original", self)
        self.reset_checked_action.triggered.connect(self.undo_all_selected_to_originals)
        edit_menu.addAction(self.reset_checked_action)

        self.show_before_action = QAction("Before", self)
        self.show_before_action.triggered.connect(self.preview_canvas.show_before)
        view_menu.addAction(self.show_before_action)

        self.show_after_action = QAction("After", self)
        self.show_after_action.triggered.connect(self.preview_canvas.show_after)
        view_menu.addAction(self.show_after_action)

        view_menu.addSeparator()

        self.preview_mode_action = QAction("Preview Mode", self)
        self.preview_mode_action.triggered.connect(self.preview_canvas.set_preview_mode)
        view_menu.addAction(self.preview_mode_action)

        self.edit_mode_action = QAction("Edit Mode", self)
        self.edit_mode_action.triggered.connect(self.preview_canvas.set_edit_mode)
        view_menu.addAction(self.edit_mode_action)

        view_menu.addSeparator()

        self.zoom_in_action = QAction("Zoom In", self)
        self.zoom_in_action.triggered.connect(self.preview_canvas.zoom_in)
        view_menu.addAction(self.zoom_in_action)

        self.zoom_out_action = QAction("Zoom Out", self)
        self.zoom_out_action.triggered.connect(self.preview_canvas.zoom_out)
        view_menu.addAction(self.zoom_out_action)

        self.erase_action = QAction("Erase", self)
        self.erase_action.triggered.connect(lambda: self._select_tool_from_menu("Erase"))
        tools_menu.addAction(self.erase_action)

        self.restore_action = QAction("Restore", self)
        self.restore_action.triggered.connect(lambda: self._select_tool_from_menu("Restore"))
        tools_menu.addAction(self.restore_action)

        self.magic_erase_action = QAction("Magic Erase", self)
        self.magic_erase_action.triggered.connect(lambda: self._select_tool_from_menu("Magic Erase"))
        tools_menu.addAction(self.magic_erase_action)

        self.background_erase_action = QAction("Background Erase", self)
        self.background_erase_action.triggered.connect(lambda: self._select_tool_from_menu("Background Erase"))
        tools_menu.addAction(self.background_erase_action)

        self.open_preferences_action = QAction("Open Preferences", self)
        self.open_preferences_action.triggered.connect(self._open_preferences_dialog)
        preferences_menu.addAction(self.open_preferences_action)

        self.about_action = QAction("About MyBGRemover", self)
        self.about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(self.about_action)

        self._apply_menu_shortcuts()

    def _select_tool_from_menu(self, tool_name: str):
        if self.settings_panel.tool_combo.findText(tool_name) >= 0:
            self.settings_panel.tool_combo.setCurrentText(tool_name)

    def _show_about_dialog(self):
        QMessageBox.information(
            self,
            "About MyBGRemover",
            "MyBGRemover\n\n"
            "Desktop background remover and editor built with Python and PySide6.\n\n"
            "Process updates the preview.\n"
            "Export creates the final full-resolution output.",
        )

    def _general_preference_default(self, key: str, fallback):
        return self.settings_store.value(
            f"general/{key}",
            fallback,
            type=type(fallback),
        )

    def _shortcut_preference_default(self, key: str, fallback: str) -> str:
        return self.settings_store.value(
            f"shortcuts/{key}",
            fallback,
            type=str,
        )

    def _editor_mode_key(self, mode_name: str) -> str:
        return mode_name.lower().replace(" ", "_")

    def _apply_general_preferences_to_ui(self):
        model_name = self._general_preference_default("model", "u2netp")
        action_name = self._general_preference_default("action", "Process")
        target_name = self._general_preference_default("target", "Selected")
        view_mode = self._general_preference_default("view_mode", "list")
        thumbnail_mode = self._general_preference_default("thumbnail_mode", "working")
        output_format = self._general_preference_default("output_format", "PNG")
        background_mode = self._general_preference_default("background_mode", "Transparent")
        background_color = self._general_preference_default("background_color", "White")
        open_output_after_export = self._general_preference_default("open_output_after_export", False)
        export_zip = self._general_preference_default("export_zip", False)
        overwrite_exports = self._general_preference_default("overwrite_exports", False)
        skip_exported = self._general_preference_default("skip_exported", False)
        skip_processed = self._general_preference_default("skip_processed", False)
        include_subfolders = self._general_preference_default("include_subfolders", False)

        if self.settings_panel.model_combo.findText(model_name) >= 0:
            self.settings_panel.model_combo.setCurrentText(model_name)

        if self.settings_panel.action_combo.findText(action_name) >= 0:
            self.settings_panel.action_combo.setCurrentText(action_name)

        if self.settings_panel.target_combo.findText(target_name) >= 0:
            self.settings_panel.target_combo.setCurrentText(target_name)

        if self.settings_panel.output_format_combo.findText(output_format) >= 0:
            self.settings_panel.output_format_combo.setCurrentText(output_format)

        if self.settings_panel.background_mode_combo.findText(background_mode) >= 0:
            self.settings_panel.background_mode_combo.setCurrentText(background_mode)

        if self.settings_panel.background_color_combo.findText(background_color) >= 0:
            self.settings_panel.background_color_combo.setCurrentText(background_color)

        self.settings_panel.open_output_after_export_check.setChecked(open_output_after_export)
        self.settings_panel.export_zip_check.setChecked(export_zip)
        self.settings_panel.overwrite_exports_check.setChecked(overwrite_exports)
        self.settings_panel.skip_exported_check.setChecked(skip_exported)
        self.settings_panel.skip_processed_check.setChecked(skip_processed)

        if hasattr(self.file_panel, "include_subfolders_check"):
            self.file_panel.include_subfolders_check.setChecked(include_subfolders)

        if hasattr(self.file_panel, "view_mode_combo"):
            blocker = QSignalBlocker(self.file_panel.view_mode_combo)
            if self.file_panel.view_mode_combo.findText(view_mode) >= 0:
                self.file_panel.view_mode_combo.setCurrentText(view_mode)
            del blocker

        if hasattr(self.file_panel, "thumbnail_mode_combo"):
            blocker = QSignalBlocker(self.file_panel.thumbnail_mode_combo)
            if self.file_panel.thumbnail_mode_combo.findText(thumbnail_mode) >= 0:
                self.file_panel.thumbnail_mode_combo.setCurrentText(thumbnail_mode)
            del blocker

        self.settings_panel.update_background_visibility()
        self.settings_panel.update_model_hint()
        self.rebuild_file_panel()
        self._refresh_main_panel_tool_preset_options()

    def _apply_menu_shortcuts(self):
        if hasattr(self, "open_files_action"):
            self.open_files_action.setShortcut(QKeySequence(self._shortcut_preference_default("open_files", "Ctrl+O")))
        if hasattr(self, "open_folder_action"):
            self.open_folder_action.setShortcut(QKeySequence(self._shortcut_preference_default("open_folder", "Ctrl+Shift+O")))
        if hasattr(self, "open_preferences_action"):
            self.open_preferences_action.setShortcut(QKeySequence(self._shortcut_preference_default("open_preferences", "Ctrl+,")))
        if hasattr(self, "undo_action"):
            self.undo_action.setShortcut(QKeySequence(self._shortcut_preference_default("undo", "Ctrl+Z")))
        if hasattr(self, "redo_action"):
            self.redo_action.setShortcut(QKeySequence(self._shortcut_preference_default("redo", "Ctrl+Y")))
        if hasattr(self, "reset_edits_action"):
            self.reset_edits_action.setShortcut(QKeySequence(self._shortcut_preference_default("reset_edits", "Ctrl+Shift+R")))
        if hasattr(self, "preview_mode_action"):
            self.preview_mode_action.setShortcut(QKeySequence(self._shortcut_preference_default("preview_mode", "Ctrl+1")))
        if hasattr(self, "edit_mode_action"):
            self.edit_mode_action.setShortcut(QKeySequence(self._shortcut_preference_default("edit_mode", "Ctrl+2")))
        if hasattr(self, "show_before_action"):
            self.show_before_action.setShortcut(QKeySequence(self._shortcut_preference_default("show_before", "Ctrl+B")))
        if hasattr(self, "show_after_action"):
            self.show_after_action.setShortcut(QKeySequence(self._shortcut_preference_default("show_after", "Ctrl+N")))
        if hasattr(self, "zoom_in_action"):
            self.zoom_in_action.setShortcut(QKeySequence(self._shortcut_preference_default("zoom_in", "Ctrl+=")))
        if hasattr(self, "zoom_out_action"):
            self.zoom_out_action.setShortcut(QKeySequence(self._shortcut_preference_default("zoom_out", "Ctrl+-")))

    def open_files_dialog(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "Wait for the current job to finish first.")
            return

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Image Files",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)",
        )

        if not file_paths:
            return

        for path_text in file_paths:
            self._add_recent_entry("files", path_text)

        self._rebuild_recent_menu()
        self._load_paths_into_app(file_paths)

    def open_folder_dialog(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "Wait for the current job to finish first.")
            return

        folder_path = QFileDialog.getExistingDirectory(self, "Open Folder")
        if not folder_path:
            return

        self._add_recent_entry("folders", folder_path)
        self._rebuild_recent_menu()
        self._load_paths_into_app([folder_path])

    def _load_paths_into_app(self, incoming_paths):
        include_subfolders = False
        if hasattr(self.file_panel, "include_subfolders_check"):
            include_subfolders = self.file_panel.include_subfolders_check.isChecked()

        files, skipped = scan_paths(incoming_paths, include_subfolders=include_subfolders)

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

        if new_files:
            self.log(f"Loaded {len(new_files)} item(s) from menu action.")

    def _get_recent_entries(self, category: str) -> list[str]:
        entries = self.settings_store.value(f"recent/{category}", [], type=list)
        if entries is None:
            return []
        return [str(entry) for entry in entries if str(entry).strip()]

    def _add_recent_entry(self, category: str, path_text: str):
        path_text = str(path_text).strip()
        if not path_text:
            return

        current_entries = self._get_recent_entries(category)
        normalized_new = str(Path(path_text).expanduser())

        filtered = []
        for entry in current_entries:
            normalized_entry = str(Path(entry).expanduser())
            if normalized_entry != normalized_new:
                filtered.append(entry)

        updated = [normalized_new] + filtered[:9]
        self.settings_store.setValue(f"recent/{category}", updated)

    def _open_recent_path(self, path_text: str):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "Wait for the current job to finish first.")
            return

        if not path_text:
            return

        self._load_paths_into_app([path_text])

    def _rebuild_recent_menu(self):
        if not hasattr(self, "recent_menu"):
            return

        self.recent_menu.clear()

        recent_files = self._get_recent_entries("files")
        recent_folders = self._get_recent_entries("folders")

        if not recent_files and not recent_folders:
            empty_action = QAction("No recent items", self)
            empty_action.setEnabled(False)
            self.recent_menu.addAction(empty_action)
            return

        if recent_files:
            files_header = QAction("Recent Files", self)
            files_header.setEnabled(False)
            self.recent_menu.addAction(files_header)

            for file_path in recent_files:
                action = QAction(file_path, self)
                action.triggered.connect(lambda checked=False, p=file_path: self._open_recent_path(p))
                self.recent_menu.addAction(action)

        if recent_files and recent_folders:
            self.recent_menu.addSeparator()

        if recent_folders:
            folders_header = QAction("Recent Folders", self)
            folders_header.setEnabled(False)
            self.recent_menu.addAction(folders_header)

            for folder_path in recent_folders:
                action = QAction(folder_path, self)
                action.triggered.connect(lambda checked=False, p=folder_path: self._open_recent_path(p))
                self.recent_menu.addAction(action)

        self.recent_menu.addSeparator()

        clear_recent_action = QAction("Clear Recent Items", self)
        clear_recent_action.triggered.connect(self._clear_recent_entries)
        self.recent_menu.addAction(clear_recent_action)

    def _clear_recent_entries(self):
        self.settings_store.setValue("recent/files", [])
        self.settings_store.setValue("recent/folders", [])
        self._rebuild_recent_menu()
        self.log("Cleared recent files and folders.")

    def _check_all_visible_items(self):
        if not hasattr(self.file_panel, "file_view"):
            return

        self.file_panel.file_view.blockSignals(True)

        for i in range(self.file_panel.file_view.count()):
            item = self.file_panel.file_view.item(i)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)

        self.file_panel.file_view.blockSignals(False)

        if hasattr(self.file_panel, "_sync_master_checkbox"):
            self.file_panel._sync_master_checkbox()
        if hasattr(self.file_panel, "_update_counts"):
            self.file_panel._update_counts()

        self.log("Checked all visible items.")

    def _uncheck_all_visible_items(self):
        if not hasattr(self.file_panel, "file_view"):
            return

        self.file_panel.file_view.blockSignals(True)

        for i in range(self.file_panel.file_view.count()):
            item = self.file_panel.file_view.item(i)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)

        self.file_panel.file_view.blockSignals(False)

        if hasattr(self.file_panel, "_sync_master_checkbox"):
            self.file_panel._sync_master_checkbox()
        if hasattr(self.file_panel, "_update_counts"):
            self.file_panel._update_counts()

        self.log("Unchecked all visible items.")

    def _editor_preference_default(self, tool_name: str, apply_mode: str, key: str, fallback):
        tool_key = tool_name.lower().replace(" ", "_")
        mode_key = self._editor_mode_key(apply_mode)
        return self.settings_store.value(
            f"editor_defaults/{tool_key}/{mode_key}/{key}",
            fallback,
            type=type(fallback),
        )

    def _builtin_editor_defaults(self):
        return {
            "Erase": {
                "Brush": {
                    "apply_mode": "Brush",
                    "brush_size": 42,
                    "softness": 35,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 35,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
                "Smart Selection": {
                    "apply_mode": "Smart Selection",
                    "brush_size": 42,
                    "softness": 35,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 35,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
            },
            "Restore": {
                "Brush": {
                    "apply_mode": "Brush",
                    "brush_size": 42,
                    "softness": 45,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 35,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
                "Smart Selection": {
                    "apply_mode": "Smart Selection",
                    "brush_size": 42,
                    "softness": 45,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 35,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
            },
            "Magic Erase": {
                "Brush": {
                    "apply_mode": "Brush",
                    "brush_size": 36,
                    "softness": 55,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 24,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
                "Smart Selection": {
                    "apply_mode": "Smart Selection",
                    "brush_size": 36,
                    "softness": 55,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 24,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
            },
            "Background Erase": {
                "Brush": {
                    "apply_mode": "Brush",
                    "brush_size": 36,
                    "softness": 55,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 20,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
                "Smart Selection": {
                    "apply_mode": "Smart Selection",
                    "brush_size": 36,
                    "softness": 55,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 20,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
            },
        }

    def _sync_settings_panel_tool_defaults_from_preferences(self):
        builtin_defaults = self._builtin_editor_defaults()

        updated_defaults = {}

        for tool_name, mode_defaults in builtin_defaults.items():
            updated_defaults[tool_name] = {}

            for apply_mode, defaults in mode_defaults.items():
                updated_defaults[tool_name][apply_mode] = {
                    "apply_mode": apply_mode,
                    "brush_size": self._editor_preference_default(tool_name, apply_mode, "brush_size", defaults["brush_size"]),
                    "softness": self._editor_preference_default(tool_name, apply_mode, "softness", defaults["softness"]),
                    "opacity": self._editor_preference_default(tool_name, apply_mode, "opacity", defaults["opacity"]),
                    "spacing": self._editor_preference_default(tool_name, apply_mode, "spacing", defaults["spacing"]),
                    "tolerance": self._editor_preference_default(tool_name, apply_mode, "tolerance", defaults["tolerance"]),
                    "magic_mode": self._editor_preference_default(tool_name, apply_mode, "magic_mode", defaults["magic_mode"]),
                    "edge_protect": self._editor_preference_default(tool_name, apply_mode, "edge_protect", defaults["edge_protect"]),
                }

        self.settings_panel.tool_defaults = updated_defaults

    def _ensure_builtin_starter_presets(self):
        seeded_flag = self.settings_store.value("preset_builtins/seeded_v1", False, type=bool)
        if seeded_flag:
            return

        builtin_defaults = self._builtin_editor_defaults()

        tool_preset_names = self.settings_store.value("tool_presets/names", [], type=list) or []
        full_preset_names = self.settings_store.value("editor_presets/names", [], type=list) or []

        def save_mode_preset(preset_name: str, tool_name: str, mode_name: str, notes: str, values: dict):
            tool_key = tool_name.lower().replace(" ", "_")
            mode_key = mode_name.lower().replace(" ", "_").replace(" ", "_")

            self.settings_store.setValue(f"tool_presets/{preset_name}/tool_name", tool_name)
            self.settings_store.setValue(
                f"tool_presets/{preset_name}/scope",
                "mode_brush" if mode_name == "Brush" else "mode_smart_selection",
            )
            self.settings_store.setValue(f"tool_presets/{preset_name}/mode_name", mode_name)
            self.settings_store.setValue(f"tool_presets/{preset_name}/notes", notes)

            for key, value in values.items():
                self.settings_store.setValue(f"tool_presets/{preset_name}/{tool_key}/{mode_key}/{key}", value)

            if preset_name not in tool_preset_names:
                tool_preset_names.append(preset_name)

        def save_full_preset(preset_name: str, notes: str, data: dict):
            for tool_name, mode_map in data.items():
                tool_key = tool_name.lower().replace(" ", "_")
                for mode_name, values in mode_map.items():
                    mode_key = mode_name.lower().replace(" ", "_")
                    for key, value in values.items():
                        self.settings_store.setValue(
                            f"editor_presets/{preset_name}/{tool_key}/{mode_key}/{key}",
                            value,
                        )

            self.settings_store.setValue(f"editor_presets/{preset_name}/notes", notes)

            if preset_name not in full_preset_names:
                full_preset_names.append(preset_name)

        save_mode_preset(
            "Magic Erase - Smart Selection - Tight Edge",
            "Magic Erase",
            "Smart Selection",
            "Conservative magic erase for tighter selections near edges.",
            {
                "brush_size": 36,
                "softness": 55,
                "opacity": 100,
                "spacing": 1,
                "tolerance": 14,
                "magic_mode": "Connected Region",
                "edge_protect": True,
            },
        )

        save_mode_preset(
            "Magic Erase - Smart Selection - Broad Fill",
            "Magic Erase",
            "Smart Selection",
            "More aggressive magic erase for larger matching areas.",
            {
                "brush_size": 36,
                "softness": 55,
                "opacity": 100,
                "spacing": 1,
                "tolerance": 38,
                "magic_mode": "Global Match",
                "edge_protect": False,
            },
        )

        save_mode_preset(
            "Background Erase - Smart Selection - Conservative",
            "Background Erase",
            "Smart Selection",
            "Safer background erase with lower tolerance and edge protection.",
            {
                "brush_size": 36,
                "softness": 55,
                "opacity": 100,
                "spacing": 1,
                "tolerance": 12,
                "magic_mode": "Connected Region",
                "edge_protect": True,
            },
        )

        save_mode_preset(
            "Erase - Brush - Soft Cleanup",
            "Erase",
            "Brush",
            "Soft brush cleanup for manual edge refinement.",
            {
                "brush_size": 48,
                "softness": 65,
                "opacity": 100,
                "spacing": 2,
                "tolerance": 35,
                "magic_mode": "Connected Region",
                "edge_protect": True,
            },
        )

        save_mode_preset(
            "Restore - Brush - Fine Recovery",
            "Restore",
            "Brush",
            "Smaller restore brush for fine recovery work.",
            {
                "brush_size": 20,
                "softness": 55,
                "opacity": 70,
                "spacing": 2,
                "tolerance": 35,
                "magic_mode": "Connected Region",
                "edge_protect": True,
            },
        )

        save_full_preset(
            "Balanced Editor Setup",
            "Starter full preset using balanced editor defaults.",
            builtin_defaults,
        )

        detailed_recovery = {
            "Erase": {
                "Brush": {
                    "brush_size": 30,
                    "softness": 55,
                    "opacity": 90,
                    "spacing": 2,
                    "tolerance": 35,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
                "Smart Selection": builtin_defaults["Erase"]["Smart Selection"].copy(),
            },
            "Restore": {
                "Brush": {
                    "brush_size": 18,
                    "softness": 60,
                    "opacity": 75,
                    "spacing": 2,
                    "tolerance": 35,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
                "Smart Selection": builtin_defaults["Restore"]["Smart Selection"].copy(),
            },
            "Magic Erase": {
                "Brush": builtin_defaults["Magic Erase"]["Brush"].copy(),
                "Smart Selection": {
                    "brush_size": 36,
                    "softness": 55,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 16,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
            },
            "Background Erase": {
                "Brush": builtin_defaults["Background Erase"]["Brush"].copy(),
                "Smart Selection": {
                    "brush_size": 36,
                    "softness": 55,
                    "opacity": 100,
                    "spacing": 1,
                    "tolerance": 14,
                    "magic_mode": "Connected Region",
                    "edge_protect": True,
                },
            },
        }

        save_full_preset(
            "Detailed Recovery Setup",
            "Starter full preset for more conservative cleanup and recovery work.",
            detailed_recovery,
        )

        self.settings_store.setValue("tool_presets/names", sorted(tool_preset_names, key=str.lower))
        self.settings_store.setValue("editor_presets/names", sorted(full_preset_names, key=str.lower))
        self.settings_store.setValue("preset_builtins/seeded_v1", True)

    def _open_preferences_dialog(self):
        dialog = PreferencesDialog(self.settings_store, self)
        result = dialog.exec()

        if result:
            self._ensure_builtin_starter_presets()
            self._apply_startup_preset_to_editor_defaults()
            self._apply_general_preferences_to_ui()
            self._sync_settings_panel_tool_defaults_from_preferences()

            self._apply_menu_shortcuts()
            self._rebuild_recent_menu()
            self._refresh_main_panel_tool_preset_options()

            QTimer.singleShot(0, self._finalize_editor_restore_after_startup)

            self.log("Preferences updated.")
            self.log("General settings, startup preset, editor defaults, shortcuts, file panel defaults, per-mode live editor state, and tool preset lists were reloaded from Preferences.")

    def _connect_signals(self):
        self.file_panel.item_selected.connect(self.select_item_from_panel)
        self.file_panel.sort_changed.connect(self.rebuild_file_panel)
        self.file_panel.status_filter_changed.connect(self.rebuild_file_panel)
        self.file_panel.type_filter_changed.connect(self.rebuild_file_panel)
        self.file_panel.view_mode_changed.connect(self.rebuild_file_panel)
        self.file_panel.thumbnail_mode_changed.connect(self.rebuild_file_panel)

        self.file_panel.remove_selected_btn.clicked.connect(self.remove_checked_items)
        self.file_panel.reset_selected_btn.clicked.connect(self.undo_all_selected_to_originals)
        self.file_panel.clear_completed_btn.clicked.connect(self.clear_completed_items)
        self.file_panel.retry_failed_btn.clicked.connect(self.retry_failed_items)
        self.file_panel.clear_all_btn.clicked.connect(self.clear_all_items)
        self.file_panel.open_output_btn.clicked.connect(self.open_output_folder)

        self.settings_panel.run_action_btn.clicked.connect(self.run_selected_action)
        self.settings_panel.cancel_btn.clicked.connect(self.request_cancel)

        self.settings_panel.tool_mode_about_to_change.connect(self._persist_specific_editor_state)
        self.settings_panel.tool_preset_apply_requested.connect(self._apply_tool_preset_from_main_panel)
        self.settings_panel.tool_combo.currentTextChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.tool_combo.currentTextChanged.connect(self._refresh_main_panel_tool_preset_options)
        self.settings_panel.apply_mode_combo.currentTextChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.apply_mode_combo.currentTextChanged.connect(self._refresh_main_panel_tool_preset_options)
        self.settings_panel.brush_size_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.softness_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.opacity_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.spacing_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.tolerance_slider.valueChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.magic_mode_combo.currentTextChanged.connect(self._sync_preview_tool_settings)
        self.settings_panel.edge_protect_check.toggled.connect(self._sync_preview_tool_settings)

        self.settings_panel.tool_combo.currentTextChanged.connect(self._persist_editor_settings)
        self.settings_panel.apply_mode_combo.currentTextChanged.connect(self._persist_editor_settings)
        self.settings_panel.brush_size_slider.valueChanged.connect(self._persist_editor_settings)
        self.settings_panel.softness_slider.valueChanged.connect(self._persist_editor_settings)
        self.settings_panel.opacity_slider.valueChanged.connect(self._persist_editor_settings)
        self.settings_panel.spacing_slider.valueChanged.connect(self._persist_editor_settings)
        self.settings_panel.tolerance_slider.valueChanged.connect(self._persist_editor_settings)
        self.settings_panel.magic_mode_combo.currentTextChanged.connect(self._persist_editor_settings)
        self.settings_panel.edge_protect_check.toggled.connect(self._persist_editor_settings)

        self.settings_panel.watch_enable_check.toggled.connect(self._on_watch_enable_toggled)
        self.settings_panel.output_dir_edit.textChanged.connect(self._persist_output_dir)
        self.settings_panel.naming_edit.textChanged.connect(self._persist_naming_suffix)

        self.preview_canvas.image_edited.connect(self._on_preview_image_edited)
        self.preview_canvas.edits_reset.connect(self._on_preview_edits_reset)

    def _startup_preset_name(self) -> str:
        return self.settings_store.value("general/startup_preset", "", type=str).strip()

    def _apply_startup_preset_to_editor_defaults(self):
        preset_name = self._startup_preset_name()
        if not preset_name:
            return

        preset_names = self.settings_store.value("editor_presets/names", [], type=list)
        if preset_names is None or preset_name not in preset_names:
            return

        tool_names = ["Erase", "Restore", "Magic Erase", "Background Erase"]
        mode_names = ["Brush", "Smart Selection"]
        value_keys = ["brush_size", "softness", "opacity", "spacing", "tolerance", "magic_mode", "edge_protect"]

        for tool_name in tool_names:
            tool_key = tool_name.lower().replace(" ", "_")
            for mode_name in mode_names:
                mode_key = self._editor_mode_key(mode_name)
                for value_key in value_keys:
                    preset_value = self.settings_store.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/{value_key}"
                    )
                    if preset_value is not None:
                        self.settings_store.setValue(
                            f"editor_defaults/{tool_key}/{mode_key}/{value_key}",
                            preset_value,
                        )

    def _has_startup_preset(self) -> bool:
        return bool(self._startup_preset_name())

    def _finalize_editor_restore_after_startup(self):
        self._sync_settings_panel_tool_defaults_from_preferences()
        self._restore_editor_settings()
        self._sync_preview_tool_settings()

    def _restore_persistent_settings(self):
        self._ensure_builtin_starter_presets()

        output_dir = self.settings_store.value("output_dir", "", type=str)
        naming_suffix = self.settings_store.value("naming_suffix", "_nobg", type=str)

        if output_dir:
            self.settings_panel.output_dir_edit.setText(output_dir)
        if naming_suffix:
            self.settings_panel.naming_edit.setText(naming_suffix)

        self._apply_startup_preset_to_editor_defaults()
        self._apply_general_preferences_to_ui()
        self._sync_settings_panel_tool_defaults_from_preferences()
        self._apply_menu_shortcuts()
        self._refresh_main_panel_tool_preset_options()



    def _restore_editor_settings(self):
        tool_name = self.settings_store.value("editor/tool_name", "Erase", type=str)
        apply_mode = self.settings_store.value("editor/apply_mode", "Brush", type=str)

        default_brush_size = self._editor_preference_default(tool_name, apply_mode, "brush_size", 42)
        default_softness = self._editor_preference_default(tool_name, apply_mode, "softness", 35)
        default_opacity = self._editor_preference_default(tool_name, apply_mode, "opacity", 100)
        default_spacing = self._editor_preference_default(tool_name, apply_mode, "spacing", 1)
        default_tolerance = self._editor_preference_default(tool_name, apply_mode, "tolerance", 35)
        default_magic_mode = self._editor_preference_default(tool_name, apply_mode, "magic_mode", "Connected Region")
        default_edge_protect = self._editor_preference_default(tool_name, apply_mode, "edge_protect", True)

        if self._has_startup_preset():
            magic_mode = default_magic_mode
            edge_protect = default_edge_protect
            brush_size = default_brush_size
            softness = default_softness
            opacity = default_opacity
            spacing = default_spacing
            tolerance = default_tolerance
        else:
            startup_preset_name = self._startup_preset_name()

        if startup_preset_name:
            magic_mode = default_magic_mode
            edge_protect = default_edge_protect
            brush_size = default_brush_size
            softness = default_softness
            opacity = default_opacity
            spacing = default_spacing
            tolerance = default_tolerance
        else:
            magic_mode = self._editor_state_value(tool_name, apply_mode, "magic_mode", default_magic_mode)
            edge_protect = self._editor_state_value(tool_name, apply_mode, "edge_protect", default_edge_protect)
            brush_size = self._editor_state_value(tool_name, apply_mode, "brush_size", default_brush_size)
            softness = self._editor_state_value(tool_name, apply_mode, "softness", default_softness)
            opacity = self._editor_state_value(tool_name, apply_mode, "opacity", default_opacity)
            spacing = self._editor_state_value(tool_name, apply_mode, "spacing", default_spacing)
            tolerance = self._editor_state_value(tool_name, apply_mode, "tolerance", default_tolerance)

        controls = [
            self.settings_panel.tool_combo,
            self.settings_panel.apply_mode_combo,
            self.settings_panel.magic_mode_combo,
            self.settings_panel.edge_protect_check,
            self.settings_panel.brush_size_slider,
            self.settings_panel.softness_slider,
            self.settings_panel.opacity_slider,
            self.settings_panel.spacing_slider,
            self.settings_panel.tolerance_slider,
        ]

        for control in controls:
            control.blockSignals(True)

        if self.settings_panel.tool_combo.findText(tool_name) >= 0:
            self.settings_panel.tool_combo.setCurrentText(tool_name)

        if self.settings_panel.apply_mode_combo.findText(apply_mode) >= 0:
            self.settings_panel.apply_mode_combo.setCurrentText(apply_mode)

        if self.settings_panel.magic_mode_combo.findText(magic_mode) >= 0:
            self.settings_panel.magic_mode_combo.setCurrentText(magic_mode)

        self.settings_panel.edge_protect_check.setChecked(edge_protect)
        self.settings_panel.brush_size_slider.setValue(max(1, min(200, brush_size)))
        self.settings_panel.softness_slider.setValue(max(0, min(100, softness)))
        self.settings_panel.opacity_slider.setValue(max(1, min(100, opacity)))
        self.settings_panel.spacing_slider.setValue(max(1, min(100, spacing)))
        self.settings_panel.tolerance_slider.setValue(max(0, min(255, tolerance)))

        for control in controls:
            control.blockSignals(False)

        self.settings_panel.update_tool_visibility()
    def _editor_state_value(self, tool_name: str, apply_mode: str, key: str, fallback):
        tool_key = tool_name.lower().replace(" ", "_")
        mode_key = self._editor_mode_key(apply_mode)
        return self.settings_store.value(
            f"editor_state/{tool_key}/{mode_key}/{key}",
            fallback,
            type=type(fallback),
        )

    def _current_editor_value(self, key: str, fallback):
        return self.settings_store.value(
            f"editor/current/{key}",
            fallback,
            type=type(fallback),
        )

    def _persist_specific_editor_state(self, tool_name: str, apply_mode: str):
        if not tool_name or not apply_mode:
            return

        tool_key = tool_name.lower().replace(" ", "_")
        mode_key = self._editor_mode_key(apply_mode).replace(" ", "_")

        self.settings_store.setValue("editor/tool_name", tool_name)
        self.settings_store.setValue("editor/apply_mode", apply_mode)

        self.settings_store.setValue(f"editor_state/{tool_key}/{mode_key}/magic_mode", self.settings_panel.magic_mode_combo.currentText())
        self.settings_store.setValue(f"editor_state/{tool_key}/{mode_key}/edge_protect", self.settings_panel.edge_protect_check.isChecked())
        self.settings_store.setValue(f"editor_state/{tool_key}/{mode_key}/brush_size", self.settings_panel.brush_size_slider.value())
        self.settings_store.setValue(f"editor_state/{tool_key}/{mode_key}/softness", self.settings_panel.softness_slider.value())
        self.settings_store.setValue(f"editor_state/{tool_key}/{mode_key}/opacity", self.settings_panel.opacity_slider.value())
        self.settings_store.setValue(f"editor_state/{tool_key}/{mode_key}/spacing", self.settings_panel.spacing_slider.value())
        self.settings_store.setValue(f"editor_state/{tool_key}/{mode_key}/tolerance", self.settings_panel.tolerance_slider.value())

    def _tool_preset_names_for_tool(self, tool_name: str) -> list[str]:
        preset_names = self.settings_store.value("tool_presets/names", [], type=list)
        if preset_names is None:
            return []

        current_mode = self.settings_panel.apply_mode_combo.currentText()

        matches = []
        for preset_name in preset_names:
            preset_name = str(preset_name)
            stored_tool_name = self.settings_store.value(
                f"tool_presets/{preset_name}/tool_name",
                "",
                type=str,
            )
            preset_scope = self.settings_store.value(
                f"tool_presets/{preset_name}/scope",
                "tool",
                type=str,
            )
            stored_mode_name = self.settings_store.value(
                f"tool_presets/{preset_name}/mode_name",
                "",
                type=str,
            )

            if stored_tool_name != tool_name:
                continue

            if preset_scope == "mode_brush" and current_mode != "Brush":
                continue

            if preset_scope == "mode_smart_selection" and current_mode != "Smart Selection":
                continue

            if (
                preset_scope in ("mode_brush", "mode_smart_selection")
                and stored_mode_name
                and stored_mode_name != current_mode
            ):
                continue

            matches.append(preset_name)

        return sorted(matches, key=str.lower)

    def _collect_available_preset_entries_for_context(self):
        entries = []

        current_tool = self.settings_panel.tool_combo.currentText()
        current_mode = self.settings_panel.apply_mode_combo.currentText()

        tool_preset_names = self.settings_store.value("tool_presets/names", [], type=list) or []
        for preset_name in tool_preset_names:
            scope = self.settings_store.value(f"tool_presets/{preset_name}/scope", "tool", type=str)
            tool_name = self.settings_store.value(f"tool_presets/{preset_name}/tool_name", "", type=str)
            mode_name = self.settings_store.value(f"tool_presets/{preset_name}/mode_name", "", type=str)
            notes = self.settings_store.value(f"tool_presets/{preset_name}/notes", "", type=str)

            include_entry = False
            display_prefix = "[Legacy]"

            if scope == "mode_brush":
                include_entry = tool_name == current_tool and current_mode == "Brush"
                display_prefix = "[Mode]"
                mode_name = "Brush"
            elif scope == "mode_smart_selection":
                include_entry = tool_name == current_tool and current_mode == "Smart Selection"
                display_prefix = "[Mode]"
                mode_name = "Smart Selection"
            elif scope == "tool":
                include_entry = tool_name == current_tool
                mode_name = "Both Modes"

            if include_entry:
                if scope in ("mode_brush", "mode_smart_selection"):
                    display_name = f"{display_prefix} {tool_name} / {mode_name} — {preset_name}"
                    type_label = "Mode Preset"
                else:
                    display_name = f"{display_prefix} {tool_name} — {preset_name}"
                    type_label = "Legacy Tool Preset"

                entries.append({
                    "store": "tool",
                    "scope": scope,
                    "type_label": type_label,
                    "tool_name": tool_name,
                    "mode_name": mode_name,
                    "name": preset_name,
                    "display_name": display_name,
                    "notes": notes,
                })

        full_preset_names = self.settings_store.value("editor_presets/names", [], type=list) or []
        for preset_name in full_preset_names:
            notes = self.settings_store.value(f"editor_presets/{preset_name}/notes", "", type=str)
            entries.append({
                "store": "full",
                "scope": "full",
                "type_label": "Full Preset",
                "tool_name": "All Tools",
                "mode_name": "All Modes",
                "name": preset_name,
                "display_name": f"[Full] {preset_name}",
                "notes": notes,
            })

        return sorted(entries, key=lambda item: item["display_name"].lower())

    def _refresh_main_panel_tool_preset_options(self):
        current_entry = self.settings_panel.current_preset_entry()
        preferred_name = ""
        if current_entry:
            preferred_name = str(current_entry.get("name", "")).strip()

        entries = self._collect_available_preset_entries_for_context()
        self.settings_panel.set_tool_preset_entries(entries, preferred_name=preferred_name)

    def _apply_editor_values_to_settings_panel(self, tool_name: str, mode_name: str, values: dict):
        defaults = self.settings_panel.tool_defaults.get(tool_name, {}).get(mode_name, {})
        merged = dict(defaults)
        merged.update(values)

        widgets = [
            self.settings_panel.magic_mode_combo,
            self.settings_panel.edge_protect_check,
            self.settings_panel.brush_size_slider,
            self.settings_panel.brush_size_value_box,
            self.settings_panel.softness_slider,
            self.settings_panel.softness_value_box,
            self.settings_panel.opacity_slider,
            self.settings_panel.opacity_value_box,
            self.settings_panel.spacing_slider,
            self.settings_panel.spacing_value_box,
            self.settings_panel.tolerance_slider,
            self.settings_panel.tolerance_value_box,
        ]

        for widget in widgets:
            widget.blockSignals(True)

        self.settings_panel._set_slider_and_box_value(
            self.settings_panel.brush_size_slider,
            self.settings_panel.brush_size_value_box,
            int(merged.get("brush_size", 42)),
        )
        self.settings_panel._set_slider_and_box_value(
            self.settings_panel.softness_slider,
            self.settings_panel.softness_value_box,
            int(merged.get("softness", 35)),
        )
        self.settings_panel._set_slider_and_box_value(
            self.settings_panel.opacity_slider,
            self.settings_panel.opacity_value_box,
            int(merged.get("opacity", 100)),
        )
        self.settings_panel._set_slider_and_box_value(
            self.settings_panel.spacing_slider,
            self.settings_panel.spacing_value_box,
            int(merged.get("spacing", 1)),
        )
        self.settings_panel._set_slider_and_box_value(
            self.settings_panel.tolerance_slider,
            self.settings_panel.tolerance_value_box,
            int(merged.get("tolerance", 35)),
        )

        self.settings_panel.magic_mode_combo.setCurrentText(
            str(merged.get("magic_mode", "Connected Region"))
        )
        self.settings_panel.edge_protect_check.setChecked(
            bool(merged.get("edge_protect", True))
        )

        for widget in widgets:
            widget.blockSignals(False)

        self.settings_panel.update_tool_visibility()

    def _apply_tool_preset_from_main_panel(self, tool_name: str, preset_name: str, preset_store: str):
        if not preset_name:
            return

        if preset_store == "full":
            self._load_full_editor_preset_into_settings_panel(preset_name)
            self._persist_editor_settings()
            self._sync_preview_tool_settings()
            self.log(
                f'Applied full preset "{preset_name}" to '
                f'{tool_name} ({self.settings_panel.apply_mode_combo.currentText()}).'
            )
            return

        self._load_tool_preset_into_settings_panel(tool_name, preset_name)
        self._persist_editor_settings()
        self._sync_preview_tool_settings()
        self.log(
            f'Applied preset "{preset_name}" to '
            f'{tool_name} ({self.settings_panel.apply_mode_combo.currentText()}).'
        )

    def _load_tool_preset_into_settings_panel(self, tool_name: str, preset_name: str):
        scope = self.settings_store.value(f"tool_presets/{preset_name}/scope", "tool", type=str)
        stored_tool_name = self.settings_store.value(f"tool_presets/{preset_name}/tool_name", "", type=str)

        if stored_tool_name != tool_name:
            return

        current_mode = self.settings_panel.apply_mode_combo.currentText()

        if scope == "mode_brush" and current_mode != "Brush":
            return

        if scope == "mode_smart_selection" and current_mode != "Smart Selection":
            return

        mode_name = current_mode
        tool_key = tool_name.lower().replace(" ", "_")
        mode_key = mode_name.lower().replace(" ", "_")

        def read_value(key, default, value_type):
            return self.settings_store.value(
                f"tool_presets/{preset_name}/{tool_key}/{mode_key}/{key}",
                default,
                type=value_type,
            )

        values = {
            "brush_size": read_value("brush_size", 42, int),
            "softness": read_value("softness", 35, int),
            "opacity": read_value("opacity", 100, int),
            "spacing": read_value("spacing", 1, int),
            "tolerance": read_value("tolerance", 35, int),
            "magic_mode": read_value("magic_mode", "Connected Region", str),
            "edge_protect": read_value("edge_protect", True, bool),
        }

        self._apply_editor_values_to_settings_panel(tool_name, mode_name, values)

    def _load_full_editor_preset_into_settings_panel(self, preset_name: str):
        tool_name = self.settings_panel.tool_combo.currentText()
        mode_name = self.settings_panel.apply_mode_combo.currentText()

        tool_key = tool_name.lower().replace(" ", "_")
        mode_key = mode_name.lower().replace(" ", "_")

        def read_value(key, default, value_type):
            return self.settings_store.value(
                f"editor_presets/{preset_name}/{tool_key}/{mode_key}/{key}",
                default,
                type=value_type,
            )

        values = {
            "brush_size": read_value("brush_size", 42, int),
            "softness": read_value("softness", 35, int),
            "opacity": read_value("opacity", 100, int),
            "spacing": read_value("spacing", 1, int),
            "tolerance": read_value("tolerance", 35, int),
            "magic_mode": read_value("magic_mode", "Connected Region", str),
            "edge_protect": read_value("edge_protect", True, bool),
        }

        self._apply_editor_values_to_settings_panel(tool_name, mode_name, values)

    def _persist_output_dir(self, text: str):
        self.settings_store.setValue("output_dir", text)

    def _persist_naming_suffix(self, text: str):
        self.settings_store.setValue("naming_suffix", text)

    def _persist_editor_settings(self):
        current_tool = self.settings_panel.tool_combo.currentText()
        current_apply_mode = self.settings_panel.apply_mode_combo.currentText()

        self.settings_store.setValue("editor/tool_name", current_tool)
        self.settings_store.setValue("editor/apply_mode", current_apply_mode)

        self.settings_store.setValue("editor/current/magic_mode", self.settings_panel.magic_mode_combo.currentText())
        self.settings_store.setValue("editor/current/edge_protect", self.settings_panel.edge_protect_check.isChecked())
        self.settings_store.setValue("editor/current/brush_size", self.settings_panel.brush_size_slider.value())
        self.settings_store.setValue("editor/current/softness", self.settings_panel.softness_slider.value())
        self.settings_store.setValue("editor/current/opacity", self.settings_panel.opacity_slider.value())
        self.settings_store.setValue("editor/current/spacing", self.settings_panel.spacing_slider.value())
        self.settings_store.setValue("editor/current/tolerance", self.settings_panel.tolerance_slider.value())

        self._persist_specific_editor_state(current_tool, current_apply_mode)

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
        self.preview_canvas.set_magic_mode(
            self.settings_panel.magic_mode_combo.currentText()
        )
        self.preview_canvas.set_edge_protect_enabled(
            self.settings_panel.edge_protect_check.isChecked()
        )

    def run_selected_action(self):
        action = self.settings_panel.action_combo.currentText()
        target = self.settings_panel.target_combo.currentText()

        if action == "Process":
            if target == "Selected":
                self.process_checked_items()
            else:
                self.process_all_items()
        else:
            if target == "Selected":
                self.export_checked_items()
            else:
                self.export_all_items()

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

    def _summarize_process_candidates(self, indices: list[int], skip_processed: bool):
        valid_indices = []
        skipped_missing_preview = 0
        skipped_already_processed = 0

        for index in indices:
            if not (0 <= index < len(self.state.items)):
                continue

            item = self.state.items[index]

            has_preview_source = (
                (item.preview_path is not None and Path(item.preview_path).exists())
                or self._has_edited_preview(item)
            )

            if not has_preview_source:
                skipped_missing_preview += 1
                continue

            if skip_processed and self._has_processed_preview(item):
                skipped_already_processed += 1
                continue

            valid_indices.append(index)

        return valid_indices, skipped_missing_preview, skipped_already_processed

    def _summarize_export_candidates(self, indices: list[int], skip_exported: bool):
        valid_indices = []
        skipped_already_exported = 0

        for index in indices:
            if not (0 <= index < len(self.state.items)):
                continue

            item = self.state.items[index]

            if skip_exported and item.status == "exported":
                skipped_already_exported += 1
                continue

            valid_indices.append(index)

        return valid_indices, skipped_already_exported

    def _has_processed_preview(self, item: ImageItem) -> bool:
        return item.processed_preview_path is not None and Path(item.processed_preview_path).exists()

    def _has_edited_preview(self, item: ImageItem) -> bool:
        return item.edited_preview_path is not None and Path(item.edited_preview_path).exists()

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
            if self.watch_worker_thread.isRunning():
                self.watch_worker_thread.quit()
                self.watch_worker_thread.wait(3000)
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

        self._load_paths_into_app(dropped_paths)
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
            indices.sort(key=lambda i: (self.state.items[i].file_type.lower(), self.state.items[i].filename.lower()))
        elif effective_sort == "Status":
            indices.sort(key=lambda i: (self.state.items[i].status.lower(), self.state.items[i].filename.lower()))

        return indices

    def _build_panel_text(self, item: ImageItem) -> str:
        if self.file_panel.current_view_mode == "thumbnail":
            return item.filename

        return (
            f"{self._short_text(item.filename, 42)}\n"
            f"{item.file_type} | {item.dimensions} | DPI: {item.dpi} | {item.status}"
        )

    def rebuild_file_panel(self, *_args, reload_preview: bool = True):
        selected_index = self.state.selected_index
        checked_indices = set(self.file_panel.get_checked_user_indices())
        status_filter = self.file_panel.status_filter_combo.currentText()
        type_filter = self.file_panel.type_filter_combo.currentText()

        scroll_bar = self.file_panel.file_view.verticalScrollBar()
        previous_scroll_value = scroll_bar.value() if scroll_bar is not None else 0

        self.file_panel.file_view.blockSignals(True)
        self.file_panel.clear_items()
        self.visible_indices = []

        for item_index in self._sorted_indices():
            item = self.state.items[item_index]
            if not self._item_matches_filter(item, status_filter, type_filter):
                continue

            if getattr(self.file_panel, "current_thumbnail_mode", "working") == "original":
                thumb_path = item.thumb_path
            else:
                thumb_path = item.edited_preview_path or item.processed_preview_path or item.thumb_path

            self.file_panel.add_item(
                self._build_panel_text(item),
                str(thumb_path) if thumb_path else None,
                item_index,
                checked=item_index in checked_indices,
            )
            self.visible_indices.append(item_index)

        selected_to_show = None

        if selected_index is not None and selected_index in self.visible_indices:
            visible_row = self.visible_indices.index(selected_index)
            self.file_panel.set_current_visible_row(visible_row)
            selected_to_show = selected_index
        elif self.visible_indices:
            selected_to_show = self.visible_indices[0]
            self.state.set_selected_index(selected_to_show)
            self.file_panel.set_current_visible_row(0)
        else:
            self.state.set_selected_index(None)
            self.preview_canvas.clear_preview()

        self.file_panel.file_view.blockSignals(False)

        if scroll_bar is not None:
            scroll_bar.setValue(min(previous_scroll_value, scroll_bar.maximum()))

        if hasattr(self.file_panel, "_update_counts"):
            self.file_panel._update_counts()

        if selected_to_show is not None and reload_preview:
            self.select_item(selected_to_show)

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

        preferred_interaction_mode = getattr(self.preview_canvas, "_interaction_mode", "preview")
        preferred_view_mode = getattr(self.preview_canvas, "_current_mode", "after")

        if before_path and Path(before_path).exists():
            title_text = (
                f"{self._short_text(item.filename, 60)} | "
                f"{item.dimensions} | DPI: {item.dpi} | {item.status}"
            )

            self.preview_canvas.set_preview_images(
                before_image_path=str(before_path),
                after_image_path=str(after_path) if after_path and Path(after_path).exists() else None,
                title_text=title_text,
                default_mode="after",
                editable_save_path=str(editable_save_path),
                preferred_interaction_mode=preferred_interaction_mode,
                preferred_view_mode=preferred_view_mode,
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

        if item.processed_preview_path is None:
            item.extra["preprocess_edit_preview_path"] = save_path_str
            item.extra["preprocess_edit_base_preview_path"] = (
                str(item.preview_path) if item.preview_path is not None else ""
            )

        if item.status != "processing":
            item.status = "edited"

        self.rebuild_file_panel(reload_preview=False)

    def _on_preview_edits_reset(self):
        selected_index = self.state.selected_index
        if selected_index is None:
            return

        item = self.state.get_item(selected_index)
        if item is None:
            return

        if item.edited_preview_path is not None:
            try:
                edited_path = Path(item.edited_preview_path)
                if edited_path.exists():
                    edited_path.unlink()
            except Exception as e:
                self.log(f"Could not remove edited preview cache: {e}")

        item.edited_preview_path = None
        item.extra.pop("preprocess_edit_preview_path", None)
        item.extra.pop("preprocess_edit_base_preview_path", None)

        if item.processed_preview_path is not None and Path(item.processed_preview_path).exists():
            item.status = "processed"
        else:
            item.status = "pending"

        self.rebuild_file_panel(reload_preview=False)
        self.select_item(selected_index)
        self.log(f"Reset edits: {item.filename}")

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

        self.state.items = [item for idx, item in enumerate(self.state.items) if idx not in checked]

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
        self.state.items = [item for item in self.state.items if item.status != "exported"]

        for idx, state_item in enumerate(self.state.items):
            state_item.date_added = idx
        self._next_date_added = len(self.state.items)

        removed_count = before_count - len(self.state.items)
        self.state.set_selected_index(None)
        self._refresh_type_filter_options()
        self.rebuild_file_panel()
        self.preview_canvas.clear_preview()

        self.log(f"Cleared exported items: {removed_count}")

    def undo_all_selected_to_originals(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "Wait for processing to finish first.")
            return

        checked = self.file_panel.get_checked_user_indices()
        if not checked:
            QMessageBox.information(self, "Nothing Selected", "No selected files to reset.")
            return

        reset_count = 0
        current_index = self.state.selected_index

        for index in checked:
            item = self.state.get_item(index)
            if item is None:
                continue

            if item.edited_preview_path is not None:
                try:
                    edited_path = Path(item.edited_preview_path)
                    if edited_path.exists():
                        edited_path.unlink()
                except Exception as e:
                    self.log(f"Could not remove edited preview cache for {item.filename}: {e}")

            item.edited_preview_path = None
            item.processed_preview_path = None
            item.output_path = ""
            item.extra.pop("preprocess_edit_preview_path", None)
            item.extra.pop("preprocess_edit_base_preview_path", None)
            item.status = "pending"
            reset_count += 1

        self.rebuild_file_panel(reload_preview=False)

        if current_index is not None:
            self.select_item(current_index)

        self.log(f"Reset selected images to original: {reset_count}")

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
            if state_item is not None and state_item.status == "exported":
                item.setCheckState(Qt.CheckState.Unchecked)

        self.file_panel.file_view.blockSignals(False)

        if hasattr(self.file_panel, "_sync_master_checkbox"):
            self.file_panel._sync_master_checkbox()
        if hasattr(self.file_panel, "_update_counts"):
            self.file_panel._update_counts()

        self.log("Unchecked exported items.")

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
            item.extra.pop("preprocess_edit_preview_path", None)
            item.extra.pop("preprocess_edit_base_preview_path", None)

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

        if self.settings_panel.removal_mode_combo.currentText() != "AI Removal":
            QMessageBox.information(
                self,
                "Not Yet Available",
                "Color Removal will be added later. Use AI Removal for now.",
            )
            return

        self.batch_mode = False
        self.batch_action = "process"
        self.batch_queue = []
        self.batch_total = 1
        self.batch_processed_count = 0
        self.batch_success_count = 0
        self.batch_error_count = 0
        self.cancel_requested = False
        self.batch_exported_files = []

        self._start_preview_processing_item(selected_index, force_reprocess=True)

    def process_checked_items(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "A processing job is already active.")
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
            QMessageBox.information(self, "Nothing Selected", "No selected files to process.")
            return

        skip_processed = self.settings_panel.skip_processed_check.isChecked()

        self.batch_queue, skipped_missing_preview, skipped_already_processed = self._summarize_process_candidates(
            checked,
            skip_processed,
        )

        if skipped_missing_preview:
            self.log(f"Skipped {skipped_missing_preview} selected item(s) with no valid preview data to process.")

        if skipped_already_processed:
            self.log(f"Skipped {skipped_already_processed} selected item(s) already marked as processed.")

        if not self.batch_queue:
            message_parts = []

            if skipped_missing_preview:
                message_parts.append(
                    f"{skipped_missing_preview} selected item(s) had no valid preview data."
                )

            if skipped_already_processed:
                message_parts.append(
                    f"{skipped_already_processed} selected item(s) were skipped because Skip Already Processed is enabled."
                )

            if not message_parts:
                message_parts.append("No selected items were available to process.")

            QMessageBox.information(
                self,
                "Nothing To Process",
                "\n".join(message_parts),
            )
            return

        self.batch_total = len(self.batch_queue)
        self.batch_processed_count = 0
        self.batch_success_count = 0
        self.batch_error_count = 0
        self.batch_mode = True
        self.batch_action = "process"
        self.cancel_requested = False
        self.batch_exported_files = []

        self.log(f"Starting batch process for {self.batch_total} selected image(s).")
        self._start_next_batch_item()

    def process_all_items(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "A processing job is already active.")
            return

        if not self.state.items:
            QMessageBox.information(self, "No Images", "Load images first.")
            return

        if self.settings_panel.removal_mode_combo.currentText() != "AI Removal":
            QMessageBox.information(
                self,
                "Not Yet Available",
                "Color Removal will be added later. Use AI Removal for now.",
            )
            return

        skip_processed = self.settings_panel.skip_processed_check.isChecked()

        self.batch_queue, skipped_missing_preview, skipped_already_processed = self._summarize_process_candidates(
            list(range(len(self.state.items))),
            skip_processed,
        )

        if skipped_missing_preview:
            self.log(f"Skipped {skipped_missing_preview} item(s) with no valid preview data to process.")

        if skipped_already_processed:
            self.log(f"Skipped {skipped_already_processed} item(s) already marked as processed.")

        if not self.batch_queue:
            message_parts = []

            if skipped_missing_preview:
                message_parts.append(
                    f"{skipped_missing_preview} item(s) had no valid preview data."
                )

            if skipped_already_processed:
                message_parts.append(
                    f"{skipped_already_processed} item(s) were skipped because Skip Already Processed is enabled."
                )

            if not message_parts:
                message_parts.append("No items were available to process.")

            QMessageBox.information(
                self,
                "Nothing To Process",
                "\n".join(message_parts),
            )
            return

        self.batch_mode = True
        self.batch_action = "process"
        self.batch_total = len(self.batch_queue)
        self.batch_processed_count = 0
        self.batch_success_count = 0
        self.batch_error_count = 0
        self.cancel_requested = False
        self.batch_exported_files = []

        self.log(f"Starting batch processing for {self.batch_total} image(s).")
        self._start_next_batch_item()

    def export_selected_item(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "A job is already active.")
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
                "Choose a valid output folder before exporting.",
            )
            return

        if self.settings_panel.removal_mode_combo.currentText() != "AI Removal":
            QMessageBox.information(
                self,
                "Not Yet Available",
                "Color Removal export will be added later. Use AI Removal for now.",
            )
            return

        self.batch_mode = False
        self.batch_action = "export"
        self.batch_queue = []
        self.batch_total = 1
        self.batch_processed_count = 0
        self.batch_success_count = 0
        self.batch_error_count = 0
        self.cancel_requested = False
        self.batch_exported_files = []

        self._start_export_item(selected_index)

    def export_checked_items(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "A job is already active.")
            return

        if self._get_output_dir() is None:
            QMessageBox.information(
                self,
                "Output Folder Required",
                "Choose a valid output folder before exporting.",
            )
            return

        if self.settings_panel.removal_mode_combo.currentText() != "AI Removal":
            QMessageBox.information(
                self,
                "Not Yet Available",
                "Color Removal export will be added later. Use AI Removal for now.",
            )
            return

        checked = self.file_panel.get_checked_user_indices()
        if not checked:
            QMessageBox.information(self, "Nothing Selected", "No selected files to export.")
            return

        skip_exported = self.settings_panel.skip_exported_check.isChecked()

        self.batch_queue, skipped_already_exported = self._summarize_export_candidates(
            checked,
            skip_exported,
        )

        if skipped_already_exported:
            self.log(f"Skipped {skipped_already_exported} selected item(s) already marked as exported.")

        if not self.batch_queue:
            message_parts = []

            if skipped_already_exported:
                message_parts.append(
                    f"{skipped_already_exported} selected item(s) were skipped because Skip Already Exported is enabled."
                )

            if not message_parts:
                message_parts.append("No selected items were available to export.")

            QMessageBox.information(
                self,
                "Nothing To Export",
                "\n".join(message_parts),
            )
            return

        self.batch_total = len(self.batch_queue)
        self.batch_processed_count = 0
        self.batch_success_count = 0
        self.batch_error_count = 0
        self.batch_mode = True
        self.batch_action = "export"
        self.cancel_requested = False
        self.batch_exported_files = []

        self.log(f"Starting batch export for {self.batch_total} selected image(s).")
        self._start_next_batch_item()

    def export_all_items(self):
        if self.processing_active:
            QMessageBox.information(self, "Processing", "A job is already active.")
            return

        if not self.state.items:
            QMessageBox.information(self, "No Images", "Load images first.")
            return

        if self._get_output_dir() is None:
            QMessageBox.information(
                self,
                "Output Folder Required",
                "Choose a valid output folder before exporting.",
            )
            return

        if self.settings_panel.removal_mode_combo.currentText() != "AI Removal":
            QMessageBox.information(
                self,
                "Not Yet Available",
                "Color Removal export will be added later. Use AI Removal for now.",
            )
            return

        skip_exported = self.settings_panel.skip_exported_check.isChecked()

        self.batch_queue, skipped_already_exported = self._summarize_export_candidates(
            list(range(len(self.state.items))),
            skip_exported,
        )

        if skipped_already_exported:
            self.log(f"Skipped {skipped_already_exported} item(s) already marked as exported.")

        if not self.batch_queue:
            message_parts = []

            if skipped_already_exported:
                message_parts.append(
                    f"{skipped_already_exported} item(s) were skipped because Skip Already Exported is enabled."
                )

            if not message_parts:
                message_parts.append("No items were available to export.")

            QMessageBox.information(
                self,
                "Nothing To Export",
                "\n".join(message_parts),
            )
            return

        self.batch_mode = True
        self.batch_action = "export"
        self.batch_total = len(self.batch_queue)
        self.batch_processed_count = 0
        self.batch_success_count = 0
        self.batch_error_count = 0
        self.cancel_requested = False
        self.batch_exported_files = []

        self.log(f"Starting batch export for {self.batch_total} image(s).")
        self._start_next_batch_item()

    def request_cancel(self):
        if not self.processing_active:
            self.log("No active job to cancel.")
            return

        self.cancel_requested = True
        self.log("Cancel requested. The current item will finish, then the batch will stop.")

    def _start_next_batch_item(self):
        if self.cancel_requested:
            self.log("Batch canceled by user.")
            self.log(
                f"Batch summary: completed {self.batch_processed_count}/{self.batch_total}, "
                f"succeeded {self.batch_success_count}, failed {self.batch_error_count}."
            )
            self._finish_processing_session()
            return

        if not self.batch_queue:
            if self.batch_action == "export":
                self.log("Batch export complete.")
            else:
                self.log("Batch processing complete.")

            self.log(
                f"Batch summary: completed {self.batch_processed_count}/{self.batch_total}, "
                f"succeeded {self.batch_success_count}, failed {self.batch_error_count}."
            )
            self._finish_processing_session(final_progress=100)
            return

        next_index = self.batch_queue.pop(0)

        if self.batch_action == "export":
            self._start_export_item(next_index)
        else:
            self._start_preview_processing_item(next_index, force_reprocess=True)

    def _set_processing_controls_enabled(self, enabled: bool):
        self.settings_panel.run_action_btn.setEnabled(enabled)
        self.settings_panel.cancel_btn.setVisible(not enabled)
        self.settings_panel.cancel_btn.setEnabled(not enabled)

        if not enabled:
            self._scroll_settings_to_bottom()

        if hasattr(self.file_panel, "process_checked_btn"):
            self.file_panel.process_checked_btn.setEnabled(enabled)

    def _scroll_settings_to_bottom(self):
        if hasattr(self, "settings_scroll") and self.settings_scroll is not None:
            bar = self.settings_scroll.verticalScrollBar()
            if bar is not None:
                bar.setValue(bar.maximum())

    def _update_batch_progress_busy(self):
        completed_percent = int((self.batch_processed_count / self.batch_total) * 100) if self.batch_total > 0 else 0
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(completed_percent)

    def _update_batch_progress(self):
        percent = int((self.batch_processed_count / self.batch_total) * 100) if self.batch_total > 0 else 0
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(percent)

    def _start_preview_processing_item(self, item_index: int, force_reprocess: bool = False):
        item = self.state.get_item(item_index)
        if item is None:
            if self.batch_mode:
                self._start_next_batch_item()
            return

        preview_input_path = item.edited_preview_path or item.preview_path

        if item.edited_preview_path is not None and Path(item.edited_preview_path).exists():
            item.extra["preprocess_edit_preview_path"] = str(item.edited_preview_path)
            item.extra["preprocess_edit_base_preview_path"] = (
                str(item.preview_path) if item.preview_path is not None else ""
            )
        else:
            item.extra.pop("preprocess_edit_preview_path", None)
            item.extra.pop("preprocess_edit_base_preview_path", None)

        if preview_input_path is None or not Path(preview_input_path).exists():
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

        if self._has_processed_preview(item) and not force_reprocess:
            item.status = "processed"
            self._refresh_item_display(item_index)
            self.select_item(item_index)

            if self.batch_mode:
                self.batch_processed_count += 1
                self._update_batch_progress()
                self._start_next_batch_item()
            return

        model_name = self.settings_panel.model_combo.currentText()
        token = self._cache_token(item.source_path)
        processed_preview_path = self.processed_preview_cache_dir / f"{token}_processed.png"

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

        item_number = self.batch_processed_count + 1 if self.batch_mode else 1
        item_total = self.batch_total if self.batch_mode else 1

        self.log(f"[{item_number}/{item_total}] Processing preview: {item.filename}")
        self.log(f"Model: {model_name}")
        self.log(f"Input preview path: {preview_input_path}")
        self.log(f"Output preview path: {processed_preview_path}")

        self.preview_worker_thread = QThread(self)
        self.preview_worker = ProcessWorker(
            item_index=item_index,
            input_path=Path(preview_input_path),
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

    def _start_export_item(self, item_index: int):
        item = self.state.get_item(item_index)
        if item is None:
            if self.batch_mode:
                self._start_next_batch_item()
            return

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

        self._start_full_export_item(item_index, apply_preview_edits=True)

    def _cleanup_preview_worker(self):
        if self.preview_worker is not None:
            self.preview_worker.deleteLater()
            self.preview_worker = None

        if self.preview_worker_thread is not None and not self.preview_worker_thread.isRunning():
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

        base_preview_mask_path = None
        edited_preview_mask_path = None
        resolved_apply_preview_edits = False
        skip_background_removal = False

        if self._has_processed_preview(item) and self._has_edited_preview(item):
            base_preview_mask_path = item.processed_preview_path
            edited_preview_mask_path = item.edited_preview_path
            resolved_apply_preview_edits = True
        else:
            preprocess_edit_preview = item.extra.get("preprocess_edit_preview_path")
            preprocess_base_preview = item.extra.get("preprocess_edit_base_preview_path")

            if preprocess_edit_preview and preprocess_base_preview:
                preprocess_edit_preview_path = Path(preprocess_edit_preview)
                preprocess_base_preview_path = Path(preprocess_base_preview)

                if preprocess_edit_preview_path.exists() and preprocess_base_preview_path.exists():
                    base_preview_mask_path = preprocess_base_preview_path
                    edited_preview_mask_path = preprocess_edit_preview_path
                    resolved_apply_preview_edits = True
                    skip_background_removal = True

        item_number = self.batch_processed_count + 1 if self.batch_mode else 1
        item_total = self.batch_total if self.batch_mode else 1

        self.log(f"Starting full-resolution export for: {item.filename}")
        self.log(f"Source image: {item.source_path}")
        self.log(f"Full-res temp path: {fullres_cache_path}")
        self.log(f"Filename suffix: {suffix}")
        self.log(f"Apply preview edits: {'yes' if resolved_apply_preview_edits and edited_preview_mask_path else 'no'}")
        self.log(f"Skip AI background removal: {'yes' if skip_background_removal else 'no'}")

        if base_preview_mask_path is not None:
            self.log(f"Base preview mask path: {base_preview_mask_path}")
        if edited_preview_mask_path is not None:
            self.log(f"Edited preview mask path: {edited_preview_mask_path}")

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
                resolved_apply_preview_edits
                and base_preview_mask_path is not None
                and edited_preview_mask_path is not None
            ),
            skip_background_removal=skip_background_removal,
            overwrite_existing=self.settings_panel.overwrite_exports_check.isChecked(),
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

        if self.export_worker_thread is not None and not self.export_worker_thread.isRunning():
            self.export_worker_thread.deleteLater()
            self.export_worker_thread = None

    def _on_preview_process_finished(self, item_index: int, processed_preview_path_str: str):
        item = self.state.get_item(item_index)
        if item is None:
            self._finalize_preview_thread()
            self._handle_post_item_completion(error=True)
            return

        processed_preview_path = Path(processed_preview_path_str)
        item.processed_preview_path = processed_preview_path
        item.edited_preview_path = None
        item.status = "processed"

        self.batch_success_count += 1
        self.log(f"Process success: {item.filename}")
        self.log(f"Preview processing complete: {processed_preview_path}")
        if processed_preview_path.exists():
            self.log(f"Processed preview size: {processed_preview_path.stat().st_size} bytes")

        self._refresh_item_display(item_index)
        self.select_item(item_index)
        self._finalize_preview_thread()
        self._handle_post_item_completion()

    def _on_preview_process_error(self, item_index: int, error_message: str):
        item = self.state.get_item(item_index)
        if item is not None:
            item.status = "error"
            item.processed_preview_path = None
            item.edited_preview_path = None
            self._refresh_item_display(item_index)
            self.log(f"Process failed: {item.filename}")
        else:
            self.log(f"Preview processing failed for item index {item_index}")

        self.batch_error_count += 1
        self.log(f"Error: {error_message}")
        self._finalize_preview_thread()
        self._handle_post_item_completion(error=True)

    def _on_full_export_finished(self, item_index: int, _fullres_cache_path: str, output_path_str: str):
        item = self.state.get_item(item_index)
        if item is not None:
            item.output_path = output_path_str
            item.status = "exported"
            self.batch_success_count += 1
            self.log(f"Export success: {item.filename}")
            self.log(f"Exported: {output_path_str}")
            self._refresh_item_display(item_index)
            self.select_item(item_index)

        if self.batch_mode:
            self.batch_exported_files.append(output_path_str)

        self._finalize_export_thread()
        self._handle_post_item_completion()

    def _on_full_export_error(self, item_index: int, error_message: str):
        item = self.state.get_item(item_index)
        if item is not None:
            item.status = "error"
            self._refresh_item_display(item_index)
            self.log(f"Export failed: {item.filename}")
        else:
            self.log(f"Full export failed for item index {item_index}")

        self.batch_error_count += 1
        self.log(f"Error: {error_message}")
        self._finalize_export_thread()
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
        should_open_output_folder = False

        if self.batch_action == "export" and self.batch_success_count > 0:
            should_open_output_folder = self.settings_panel.open_output_after_export_check.isChecked()

        if self.batch_action == "export" and self.settings_panel.export_zip_check.isChecked() and self.batch_exported_files:
            output_dir = self._get_output_dir()
            if output_dir is not None:
                ok, zip_path, err = create_batch_zip(self.batch_exported_files, output_dir)
                if ok:
                    self.log(f"ZIP export created: {zip_path}")

                    for exported_file in self.batch_exported_files:
                        exported_path = Path(exported_file)
                        try:
                            if exported_path.exists() and exported_path.is_file():
                                exported_path.unlink()
                                self.log(f"Removed loose export after ZIP creation: {exported_path.name}")
                        except Exception as e:
                            self.log(f"Could not remove loose export {exported_path.name}: {e}")
                else:
                    self.log(f"ZIP export failed: {err}")

        completed_count = self.batch_processed_count
        success_count = self.batch_success_count
        error_count = self.batch_error_count
        skipped_count = max(0, completed_count - success_count - error_count)

        if self.batch_action == "export":
            self.log(
                f"Export session summary: completed {completed_count}, "
                f"succeeded {success_count}, failed {error_count}, skipped {skipped_count}."
            )
        elif self.batch_action == "process":
            self.log(
                f"Process session summary: completed {completed_count}, "
                f"succeeded {success_count}, failed {error_count}, skipped {skipped_count}."
            )

        self.batch_mode = False
        self.batch_action = None
        self.batch_queue = []
        self.batch_total = 0
        self.batch_processed_count = 0
        self.batch_success_count = 0
        self.batch_error_count = 0
        self.cancel_requested = False
        self.current_processing_index = None
        self.batch_exported_files = []

        self._set_processing_controls_enabled(True)

        self._set_processing_controls_enabled(True)

        if should_open_output_folder:
            output_dir = self._get_output_dir()
            if output_dir is not None and output_dir.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))
                self.log(f"Opened output folder after export: {output_dir}")

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
        self.batch_success_count = 0
        self.batch_error_count = 0
        self.batch_mode = False
        self.batch_action = None
        self.cancel_requested = False
        self.batch_exported_files = []
        self.visible_indices = []
        self._refresh_type_filter_options()

        self.log("Cleared all items.")

    def closeEvent(self, event):
        self.cancel_requested = True
        self._stop_watch_folder()
        self._shutdown_running_threads()
        self._persist_editor_settings()
        self.settings_store.sync()
        super().closeEvent(event)
