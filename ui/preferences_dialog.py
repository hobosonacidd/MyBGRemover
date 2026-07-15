import json
from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QKeySequenceEdit,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)


class PresetDetailsDialog(QDialog):
    def __init__(
        self,
        title: str,
        default_name: str,
        default_notes: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(440, 250)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(default_name)
        self.notes_edit = QPlainTextEdit(default_notes)
        self.notes_edit.setMaximumHeight(120)

        form.addRow("Name", self.name_edit)
        form.addRow("Notes / Description", self.notes_edit)
        layout.addLayout(form)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def values(self):
        return self.name_edit.text().strip(), self.notes_edit.toPlainText().strip()


class PreferencesDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings

        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.resize(860, 800)
        self.setMinimumSize(660, 540)

        self._search_targets = {}

        self._build_ui()
        self._refresh_startup_preset_combo()
        self._load_settings()
        self._refresh_preset_manager()
        self._ensure_default_preset_names()
        self._apply_search_filter()
        self._apply_dialog_styles()

    def _apply_dialog_styles(self):
        check_icon_path = (Path(__file__).resolve().parent / "assets" / "checkmark.svg").as_posix()

        self.setStyleSheet(f"""
            QDialog {{
                background: #2f2f2f;
                color: #f0f0f0;
            }}

            QGroupBox {{
                border: 1px solid #5f5f5f;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background: #343434;
                font-weight: bold;
            }}

            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px 0 4px;
                color: #ffffff;
            }}

            QLabel {{
                color: #f0f0f0;
            }}

            QLineEdit,
            QPlainTextEdit,
            QListWidget,
            QComboBox,
            QKeySequenceEdit,
            QScrollArea,
            QSpinBox {{
                background: #1f1f1f;
                color: #f0f0f0;
                border: 1px solid #666666;
                border-radius: 5px;
                padding: 4px;
                selection-background-color: #AD2831;
                selection-color: #ffffff;
            }}

            QLineEdit:hover,
            QPlainTextEdit:hover,
            QListWidget:hover,
            QComboBox:hover,
            QKeySequenceEdit:hover,
            QSpinBox:hover {{
                border: 1px solid #8a8a8a;
            }}

            QLineEdit:focus,
            QPlainTextEdit:focus,
            QListWidget:focus,
            QComboBox:focus,
            QKeySequenceEdit:focus,
            QSpinBox:focus {{
                border: 1px solid #AD2831;
            }}

            QListWidget::item {{
                padding: 4px;
                border-radius: 4px;
            }}

            QListWidget::item:hover {{
                background: #444444;
            }}

            QListWidget::item:selected {{
                background: #AD2831;
                color: #ffffff;
            }}

            QPushButton {{
                background: #4a4a4a;
                color: #ffffff;
                border: 1px solid #777777;
                border-radius: 6px;
                padding: 6px 10px;
            }}

            QPushButton:hover {{
                background: #5c5c5c;
                border: 1px solid #9a9a9a;
            }}

            QPushButton:pressed {{
                background: #6b6b6b;
                border: 1px solid #b0b0b0;
            }}

            QPushButton:disabled {{
                background: #3a3a3a;
                color: #999999;
                border: 1px solid #555555;
            }}

            QTabWidget::pane {{
                border: 1px solid #5f5f5f;
                background: #2f2f2f;
            }}

            QTabBar::tab {{
                background: #3a3a3a;
                color: #f0f0f0;
                border: 1px solid #5f5f5f;
                padding: 6px 12px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }}

            QTabBar::tab:selected {{
                background: #AD2831;
                color: #ffffff;
            }}

            QTabBar::tab:hover:!selected {{
                background: #4d4d4d;
            }}

            QCheckBox {{
                color: #f0f0f0;
            }}

            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid #888888;
                border-radius: 4px;
                background: #1f1f1f;
            }}

            QCheckBox::indicator:hover {{
                border: 1px solid #a5a5a5;
            }}

            QCheckBox::indicator:checked {{
                background: #1f1f1f;
                border: 1px solid #AD2831;
                image: url("{check_icon_path}");
            }}

            QSlider::groove:horizontal {{
                height: 6px;
                background: #444444;
                border-radius: 3px;
            }}

            QSlider::sub-page:horizontal {{
                background: #AD2831;
                border-radius: 3px;
            }}

            QSlider::handle:horizontal {{
                background: #d8d8d8;
                border: 1px solid #8a8a8a;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}

            QSlider::handle:horizontal:hover {{
                background: #f0f0f0;
            }}
        """)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        search_label = QLabel("Search Settings")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search this tab...")
        search_row.addWidget(search_label)
        search_row.addWidget(self.search_edit, 1)
        main_layout.addLayout(search_row)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        self.general_tab, self.general_layout = self._create_scrolling_tab("General")
        self.editor_tab, self.editor_layout = self._create_scrolling_tab("Editor")
        self.presets_tab, self.presets_layout = self._create_scrolling_tab("Presets")
        self.shortcuts_tab, self.shortcuts_layout = self._create_scrolling_tab("Shortcuts")

        self._build_general_tab()
        self._build_editor_tab()
        self._build_presets_tab()
        self._build_shortcuts_tab()

        button_row = QHBoxLayout()

        self.reset_btn = QPushButton("Reset to Built-in Defaults")
        button_row.addWidget(self.reset_btn)

        button_row.addStretch()

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        button_row.addWidget(self.button_box)

        main_layout.addLayout(button_row)

        self.search_edit.textChanged.connect(self._apply_search_filter)
        self.tabs.currentChanged.connect(self._apply_search_filter)

        self.reset_btn.clicked.connect(self._reset_to_builtin_defaults)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._on_apply)

    def _create_scrolling_tab(self, tab_name: str):
        tab_wrapper = QWidget()
        wrapper_layout = QVBoxLayout(tab_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)

        scroll_area.setWidget(content)
        wrapper_layout.addWidget(scroll_area)

        self.tabs.addTab(tab_wrapper, tab_name)
        self._search_targets[tab_wrapper] = []

        return tab_wrapper, content_layout

    def _register_search_target(self, tab_widget: QWidget, widget: QWidget, text: str):
        self._search_targets.setdefault(tab_widget, []).append((widget, text.lower()))

    def _apply_search_filter(self):
        query = self.search_edit.text().strip().lower()
        current_tab = self.tabs.currentWidget()

        for tab_widget, targets in self._search_targets.items():
            for widget, text in targets:
                if tab_widget != current_tab:
                    widget.setVisible(True)
                    continue

                widget.setVisible((not query) or (query in text))

    def _make_compact_button(self, button: QPushButton):
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.setMaximumWidth(120)
        button.setMinimumHeight(28)
        button.setMaximumHeight(28)

    def _tool_names(self):
        return ["Erase", "Restore", "Magic Erase", "Background Erase"]

    def _mode_names(self):
        return ["Brush", "Smart Selection"]

    def _editor_field_visibility(self, tool_name: str, mode_name: str) -> dict[str, bool]:
        is_brush = mode_name == "Brush"
        is_smart = mode_name == "Smart Selection"
        is_erase_restore = tool_name in ("Erase", "Restore")
        is_magic = tool_name == "Magic Erase"
        is_background = tool_name == "Background Erase"

        return {
            "brush_size": (
                (is_erase_restore and is_brush)
                or (is_erase_restore and is_smart)
                or (is_magic and is_brush)
                or (is_background and is_brush)
            ),
            "softness": (
                (is_erase_restore and is_brush)
                or (is_erase_restore and is_smart)
                or (is_magic and is_brush)
                or (is_background and is_brush)
            ),
            "opacity": (
                (is_erase_restore and is_brush)
                or (is_erase_restore and is_smart)
                or is_magic
                or is_background
            ),
            "flow": is_brush and is_erase_restore,
            "spacing": (
                (is_erase_restore and is_brush)
                or (is_magic and is_brush)
                or (is_background and is_brush)
            ),
            "tolerance": is_magic or is_background,
            "magic_mode": is_magic,
            "edge_protect": is_magic or is_background,
            "smart_feather": is_smart,
            "smart_expand": is_smart,
            "smart_cleanup": is_smart,
        }

    def _create_slider_row(self, min_value: int, max_value: int, parent: QWidget | None = None):
        row_widget = QWidget(parent)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        slider = QSlider(Qt.Orientation.Horizontal, row_widget)
        slider.setRange(min_value, max_value)

        value_box = QSpinBox(row_widget)
        value_box.setRange(min_value, max_value)
        value_box.setFixedWidth(72)
        value_box.setKeyboardTracking(False)

        slider.valueChanged.connect(value_box.setValue)
        value_box.valueChanged.connect(slider.setValue)

        row_layout.addWidget(slider, 1)
        row_layout.addWidget(value_box)

        return row_widget, slider, value_box

    def _create_form_label(self, text: str, parent: QWidget | None = None):
        label = QLabel(text, parent)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _build_general_tab(self):
        intro_label = QLabel(
            "These values control app-wide defaults used when the app starts."
        )
        intro_label.setWordWrap(True)
        self.general_layout.addWidget(intro_label)

        startup_group = QGroupBox("Startup and Workflow")
        startup_form = QFormLayout(startup_group)
        startup_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.default_model_combo = QComboBox()
        self.default_model_combo.addItems([
            "u2net",
            "u2netp",
            "u2net_human_seg",
            "isnet-general-use",
            "isnet-anime",
            "birefnet-general-lite",
            "birefnet-general",
            "birefnet-portrait",
            "bria-rmbg",
        ])

        self.default_action_combo = QComboBox()
        self.default_action_combo.addItems(["Process", "Export"])

        self.default_target_combo = QComboBox()
        self.default_target_combo.addItems(["Selected", "All"])

        self.default_startup_preset_combo = QComboBox()

        startup_form.addRow("Default Model", self.default_model_combo)
        startup_form.addRow("Default Action", self.default_action_combo)
        startup_form.addRow("Default Target", self.default_target_combo)
        startup_form.addRow("Startup Full Preset", self.default_startup_preset_combo)

        self.general_layout.addWidget(startup_group)
        self._register_search_target(
            self.general_tab,
            startup_group,
            "startup workflow default model default action default target startup full preset",
        )

        file_panel_group = QGroupBox("File Panel")
        file_panel_form = QFormLayout(file_panel_group)
        file_panel_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.default_view_mode_combo = QComboBox()
        self.default_view_mode_combo.addItems(["list", "thumbnail"])

        self.default_thumbnail_mode_combo = QComboBox()
        self.default_thumbnail_mode_combo.addItems(["working", "original"])

        self.default_include_subfolders_check = QCheckBox("Include subfolders when loading folders")

        file_panel_form.addRow("File Panel View", self.default_view_mode_combo)
        file_panel_form.addRow("Thumbnail Mode", self.default_thumbnail_mode_combo)
        file_panel_form.addRow("", self.default_include_subfolders_check)

        self.general_layout.addWidget(file_panel_group)
        self._register_search_target(
            self.general_tab,
            file_panel_group,
            "file panel view thumbnail mode include subfolders",
        )

        output_group = QGroupBox("Output and Export")
        output_form = QFormLayout(output_group)
        output_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.default_output_format_combo = QComboBox()
        self.default_output_format_combo.addItems(["PNG", "JPG", "WEBP"])

        self.default_background_mode_combo = QComboBox()
        self.default_background_mode_combo.addItems(["Transparent", "Solid Color"])

        self.default_background_color_combo = QComboBox()
        self.default_background_color_combo.addItems(["White", "Black"])

        self.default_open_output_after_export_check = QCheckBox("Open output folder when export finishes")
        self.default_export_zip_check = QCheckBox("Export successful results as ZIP")
        self.default_overwrite_exports_check = QCheckBox("Overwrite existing exports")
        self.default_skip_exported_check = QCheckBox("Skip already exported items")
        self.default_skip_processed_check = QCheckBox("Skip already processed items")

        output_form.addRow("Output Format", self.default_output_format_combo)
        output_form.addRow("Background Mode", self.default_background_mode_combo)
        output_form.addRow("Solid Background Color", self.default_background_color_combo)
        output_form.addRow("", self.default_open_output_after_export_check)
        output_form.addRow("", self.default_export_zip_check)
        output_form.addRow("", self.default_overwrite_exports_check)
        output_form.addRow("", self.default_skip_exported_check)
        output_form.addRow("", self.default_skip_processed_check)

        self.general_layout.addWidget(output_group)
        self._register_search_target(
            self.general_tab,
            output_group,
            "output export output format background mode solid background color open output after export zip overwrite skip exported skip processed",
        )
        
        watch_group = QGroupBox("Watch Folder")
        watch_layout = QVBoxLayout(watch_group)

        watch_path_row = QHBoxLayout()
        self.watch_folder_edit = QLineEdit()
        self.watch_folder_edit.setPlaceholderText("Choose a folder to monitor")
        self.watch_folder_btn = QPushButton("Choose Watch Folder")
        watch_path_row.addWidget(self.watch_folder_edit, 1)
        watch_path_row.addWidget(self.watch_folder_btn)

        self.watch_include_subfolders_check = QCheckBox("Include subfolders in watch folder")
        self.watch_enable_check = QCheckBox("Enable watch folder automation now")
        self.watch_status_label = QLabel("Watch status: Off — No folder selected")
        self.watch_status_label.setWordWrap(True)

        watch_layout.addWidget(QLabel("Watch Folder Path"))
        watch_layout.addLayout(watch_path_row)
        watch_layout.addWidget(self.watch_include_subfolders_check)
        watch_layout.addWidget(self.watch_enable_check)
        watch_layout.addWidget(self.watch_status_label)

        self.general_layout.addWidget(watch_group)
        self._register_search_target(
            self.general_tab,
            watch_group,
            "watch folder path include subfolders enable watch folder automation status",
        )

        self.watch_folder_btn.clicked.connect(self._choose_watch_folder)

        self.general_reset_btn = QPushButton("Reset General Settings")
        self.general_reset_btn.clicked.connect(self._reset_general_tab)
        self.general_layout.addWidget(self.general_reset_btn)
        self._register_search_target(self.general_tab, self.general_reset_btn, "reset general settings")

        self.general_layout.addStretch()

    def _choose_watch_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Watch Folder")
        if folder:
            self.watch_folder_edit.setText(folder)

    def _build_editor_tab(self):
        intro_label = QLabel(
            "These values control the default editor settings used when tools are selected."
        )
        intro_label.setWordWrap(True)
        self.editor_layout.addWidget(intro_label)

        full_preset_group = QGroupBox("Save Full Editor Preset")
        full_preset_layout = QVBoxLayout(full_preset_group)

        full_preset_row = QHBoxLayout()
        self.editor_full_preset_name_edit = QLineEdit()
        self.editor_full_preset_name_edit.setPlaceholderText("Preset 1")
        self.editor_save_full_preset_btn = QPushButton("Save Full Preset")
        self._make_compact_button(self.editor_save_full_preset_btn)

        self.editor_save_full_preset_btn.setToolTip(
            "Saves all current Editor defaults for every tool and mode as one full preset."
        )

        full_preset_row.addWidget(QLabel("Preset Name"))
        full_preset_row.addWidget(self.editor_full_preset_name_edit, 1)
        full_preset_row.addWidget(self.editor_save_full_preset_btn)

        self.editor_full_preset_notes_edit = QPlainTextEdit()
        self.editor_full_preset_notes_edit.setPlaceholderText("Optional notes for this full preset...")
        self.editor_full_preset_notes_edit.setMaximumHeight(80)

        full_preset_layout.addLayout(full_preset_row)
        full_preset_layout.addWidget(QLabel("Full Preset Notes"))
        full_preset_layout.addWidget(self.editor_full_preset_notes_edit)

        self.editor_layout.addWidget(full_preset_group)
        self._register_search_target(
            self.editor_tab,
            full_preset_group,
            "full editor preset save full preset full preset notes",
        )

        self.tool_mode_sections = {}

        for tool_name in self._tool_names():
            tool_group = QGroupBox(tool_name)
            tool_layout = QVBoxLayout(tool_group)

            self.tool_mode_sections[tool_name] = {}

            for mode_name in self._mode_names():
                mode_group = QGroupBox(f"{mode_name} Defaults")
                form = QFormLayout(mode_group)
                form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

                visible_mode_header = QLabel(f"{mode_name} Defaults", mode_group)
                visible_mode_header.setStyleSheet("font-weight: bold; font-size: 13px;")
                form.addRow(visible_mode_header)

                # Sliders
                brush_size_row, brush_size_slider, brush_size_value = self._create_slider_row(1, 200, mode_group)
                softness_row, softness_slider, softness_value = self._create_slider_row(0, 100, mode_group)
                opacity_row, opacity_slider, opacity_value = self._create_slider_row(1, 100, mode_group)
                flow_row, flow_slider, flow_value = self._create_slider_row(1, 100, mode_group)
                spacing_row, spacing_slider, spacing_value = self._create_slider_row(1, 100, mode_group)
                tolerance_row, tolerance_slider, tolerance_value = self._create_slider_row(0, 255, mode_group)

                smart_feather_row, smart_feather_slider, smart_feather_value = self._create_slider_row(0, 25, mode_group)
                smart_expand_row, smart_expand_slider, smart_expand_value = self._create_slider_row(-10, 10, mode_group)

                # Combo boxes / checkboxes
                magic_mode_combo = QComboBox(mode_group)
                magic_mode_combo.addItems(["Connected Region", "Global Match"])

                edge_protect_check = QCheckBox("Enable Edge Protect", mode_group)
                smart_cleanup_holes_check = QCheckBox("Fill Small Holes", mode_group)
                smart_cleanup_speckles_check = QCheckBox("Remove Speckles", mode_group)

                # Labels
                brush_size_label = self._create_form_label("Brush Size", mode_group)
                softness_label = self._create_form_label("Softness", mode_group)
                opacity_label = self._create_form_label("Opacity", mode_group)
                flow_label = self._create_form_label("Flow", mode_group)
                spacing_label = self._create_form_label("Spacing", mode_group)
                tolerance_label = self._create_form_label("Tolerance", mode_group)
                magic_mode_label = self._create_form_label("Magic Mode", mode_group)
                smart_feather_label = self._create_form_label("Selection Feather", mode_group)
                smart_expand_label = self._create_form_label("Expand / Contract", mode_group)

                # Tooltips
                brush_size_tip = (
                    "Controls the size of the brush or Smart Selection click area."
                )
                softness_tip = (
                    "Controls brush edge softness.\n"
                    "Lower values create a harder edge. Higher values create a softer edge."
                )
                opacity_tip = (
                    "Controls the maximum strength of the edit."
                )
                flow_tip = (
                    "Controls how quickly Erase/Restore brush strokes build up while dragging.\n"
                    "Flow 100 applies full strength immediately. Lower values build gradually."
                )
                spacing_tip = (
                    "Controls the distance between brush stamps during a stroke.\n"
                    "Lower values make strokes smoother but can be slower."
                )
                tolerance_tip = (
                    "Controls how closely colors must match for Magic Erase and Background Erase.\n"
                    "Lower values affect fewer colors. Higher values affect a wider color range."
                )
                magic_mode_tip = (
                    "Connected Region affects only the clicked connected area.\n"
                    "Global Match affects matching areas across the full preview."
                )
                edge_protect_tip = (
                    "Protects likely subject edges while using Magic Erase or Background Erase."
                )
                smart_feather_tip = (
                    "Softens the edge of Smart Selection results.\n"
                    "Use a small value for cleaner, less jagged selection edges."
                )
                smart_expand_tip = (
                    "Adjusts Smart Selection size after selection.\n"
                    "Negative values contract/shrink the selection. Positive values expand/grow it."
                )
                smart_cleanup_holes_tip = (
                    "Fills small transparent holes inside Smart Selection results."
                )
                smart_cleanup_speckles_tip = (
                    "Removes tiny isolated artifacts from Smart Selection results."
                )

                for widget in (brush_size_label, brush_size_row, brush_size_slider, brush_size_value):
                    widget.setToolTip(brush_size_tip)

                for widget in (softness_label, softness_row, softness_slider, softness_value):
                    widget.setToolTip(softness_tip)

                for widget in (opacity_label, opacity_row, opacity_slider, opacity_value):
                    widget.setToolTip(opacity_tip)

                for widget in (flow_label, flow_row, flow_slider, flow_value):
                    widget.setToolTip(flow_tip)

                for widget in (spacing_label, spacing_row, spacing_slider, spacing_value):
                    widget.setToolTip(spacing_tip)

                for widget in (tolerance_label, tolerance_row, tolerance_slider, tolerance_value):
                    widget.setToolTip(tolerance_tip)

                for widget in (magic_mode_label, magic_mode_combo):
                    widget.setToolTip(magic_mode_tip)

                edge_protect_check.setToolTip(edge_protect_tip)

                for widget in (smart_feather_label, smart_feather_row, smart_feather_slider, smart_feather_value):
                    widget.setToolTip(smart_feather_tip)

                for widget in (smart_expand_label, smart_expand_row, smart_expand_slider, smart_expand_value):
                    widget.setToolTip(smart_expand_tip)

                smart_cleanup_holes_check.setToolTip(smart_cleanup_holes_tip)
                smart_cleanup_speckles_check.setToolTip(smart_cleanup_speckles_tip)

                save_preset_tip = (
                    "Saves the current values for this specific tool and mode."
                )
                save_preset_as_tip = (
                    "Saves the current values for this specific tool and mode with a custom name and notes."
                )

                # Rows in the order they should appear
                form.addRow(brush_size_label, brush_size_row)
                form.addRow(softness_label, softness_row)
                form.addRow(opacity_label, opacity_row)
                form.addRow(flow_label, flow_row)
                form.addRow(spacing_label, spacing_row)
                form.addRow(tolerance_label, tolerance_row)
                form.addRow(magic_mode_label, magic_mode_combo)
                form.addRow(smart_feather_label, smart_feather_row)
                form.addRow(smart_expand_label, smart_expand_row)
                form.addRow("", smart_cleanup_holes_check)
                form.addRow("", smart_cleanup_speckles_check)
                form.addRow("", edge_protect_check)

                visibility = self._editor_field_visibility(tool_name, mode_name)

                brush_size_label.setVisible(visibility["brush_size"])
                brush_size_row.setVisible(visibility["brush_size"])

                softness_label.setVisible(visibility["softness"])
                softness_row.setVisible(visibility["softness"])

                opacity_label.setVisible(visibility["opacity"])
                opacity_row.setVisible(visibility["opacity"])

                flow_label.setVisible(visibility["flow"])
                flow_row.setVisible(visibility["flow"])

                spacing_label.setVisible(visibility["spacing"])
                spacing_row.setVisible(visibility["spacing"])

                tolerance_label.setVisible(visibility["tolerance"])
                tolerance_row.setVisible(visibility["tolerance"])

                magic_mode_label.setVisible(visibility["magic_mode"])
                magic_mode_combo.setVisible(visibility["magic_mode"])

                smart_feather_label.setVisible(visibility["smart_feather"])
                smart_feather_row.setVisible(visibility["smart_feather"])

                smart_expand_label.setVisible(visibility["smart_expand"])
                smart_expand_row.setVisible(visibility["smart_expand"])

                smart_cleanup_holes_check.setVisible(visibility["smart_cleanup"])
                smart_cleanup_speckles_check.setVisible(visibility["smart_cleanup"])

                edge_protect_check.setVisible(visibility["edge_protect"])

                button_row = QHBoxLayout()
                button_row.addStretch()

                save_preset_btn = QPushButton("Save Preset")
                save_preset_as_btn = QPushButton("Save Preset...")
                save_preset_btn.setToolTip(save_preset_tip)
                save_preset_as_btn.setToolTip(save_preset_as_tip)
                self._make_compact_button(save_preset_btn)
                self._make_compact_button(save_preset_as_btn)

                button_row.addWidget(save_preset_btn)
                button_row.addWidget(save_preset_as_btn)
                form.addRow("", button_row)

                self.tool_mode_sections[tool_name][mode_name] = {
                    "brush_size_label": brush_size_label,
                    "brush_size_row": brush_size_row,
                    "brush_size_slider": brush_size_slider,
                    "brush_size_value": brush_size_value,
                    "softness_label": softness_label,
                    "softness_row": softness_row,
                    "softness_slider": softness_slider,
                    "softness_value": softness_value,
                    "opacity_label": opacity_label,
                    "opacity_row": opacity_row,
                    "opacity_slider": opacity_slider,
                    "opacity_value": opacity_value,
                    "flow_label": flow_label,
                    "flow_row": flow_row,
                    "flow_slider": flow_slider,
                    "flow_value": flow_value,
                    "spacing_label": spacing_label,
                    "spacing_row": spacing_row,
                    "spacing_slider": spacing_slider,
                    "spacing_value": spacing_value,
                    "tolerance_label": tolerance_label,
                    "tolerance_row": tolerance_row,
                    "tolerance_slider": tolerance_slider,
                    "tolerance_value": tolerance_value,
                    "magic_mode_label": magic_mode_label,
                    "magic_mode": magic_mode_combo,
                    "edge_protect": edge_protect_check,
                    "smart_feather_label": smart_feather_label,
                    "smart_feather_row": smart_feather_row,
                    "smart_feather_slider": smart_feather_slider,
                    "smart_feather_value": smart_feather_value,
                    "smart_expand_label": smart_expand_label,
                    "smart_expand_row": smart_expand_row,
                    "smart_expand_slider": smart_expand_slider,
                    "smart_expand_value": smart_expand_value,
                    "smart_cleanup_holes": smart_cleanup_holes_check,
                    "smart_cleanup_speckles": smart_cleanup_speckles_check,
                    "save_btn": save_preset_btn,
                    "save_as_btn": save_preset_as_btn,
                }

                save_preset_btn.clicked.connect(
                    lambda checked=False, t=tool_name, m=mode_name: self._quick_save_mode_preset(t, m)
                )
                save_preset_as_btn.clicked.connect(
                    lambda checked=False, t=tool_name, m=mode_name: self._save_mode_preset_with_dialog(t, m)
                )

                tool_layout.addWidget(mode_group)

            self.editor_layout.addWidget(tool_group)
            self._register_search_target(
                self.editor_tab,
                tool_group,
                (
                    f"{tool_name} brush smart selection save preset brush size softness "
                    "opacity flow spacing tolerance magic mode edge protect selection feather "
                    "expand contract fill holes remove speckles"
                ),
            )

        self.editor_reset_btn = QPushButton("Reset Editor Defaults")
        self.editor_reset_btn.clicked.connect(self._reset_editor_tab)
        self.editor_layout.addWidget(self.editor_reset_btn)
        self._register_search_target(self.editor_tab, self.editor_reset_btn, "reset editor defaults")

        self.editor_layout.addStretch()

        self.editor_save_full_preset_btn.clicked.connect(self._save_full_preset_from_editor_tab)
        
    def _build_presets_tab(self):
        intro_label = QLabel(
            "Manage mode presets, full presets, and older legacy tool presets from one place."
        )
        intro_label.setWordWrap(True)
        self.presets_layout.addWidget(intro_label)

        filters_group = QGroupBox("Filters")
        filters_layout = QGridLayout(filters_group)

        self.preset_type_filter_combo = QComboBox()
        self.preset_type_filter_combo.addItems([
            "All Presets",
            "Mode Presets",
            "Full Presets",
            "Legacy Tool Presets",
        ])

        self.preset_tool_filter_combo = QComboBox()
        self.preset_tool_filter_combo.addItems(["All Tools"] + self._tool_names())

        self.preset_mode_filter_combo = QComboBox()
        self.preset_mode_filter_combo.addItems(["All Modes"] + self._mode_names())

        filters_layout.addWidget(QLabel("Type"), 0, 0)
        filters_layout.addWidget(self.preset_type_filter_combo, 0, 1)
        filters_layout.addWidget(QLabel("Tool"), 0, 2)
        filters_layout.addWidget(self.preset_tool_filter_combo, 0, 3)
        filters_layout.addWidget(QLabel("Mode"), 1, 0)
        filters_layout.addWidget(self.preset_mode_filter_combo, 1, 1)

        self.presets_layout.addWidget(filters_group)

        manager_group = QGroupBox("Preset Manager")
        manager_layout = QVBoxLayout(manager_group)

        self.presets_list = QListWidget()

        detail_form = QFormLayout()
        self.preset_selected_type_label = QLabel("-")
        self.preset_selected_tool_label = QLabel("-")
        self.preset_selected_mode_label = QLabel("-")
        self.preset_name_edit = QLineEdit()
        self.preset_notes_edit = QPlainTextEdit()
        self.preset_notes_edit.setMaximumHeight(90)

        detail_form.addRow("Preset Type", self.preset_selected_type_label)
        detail_form.addRow("Tool", self.preset_selected_tool_label)
        detail_form.addRow("Mode", self.preset_selected_mode_label)
        detail_form.addRow("Name", self.preset_name_edit)
        detail_form.addRow("Notes / Description", self.preset_notes_edit)

        self.preset_legacy_note_label = QLabel(
            "Legacy tool presets are kept for compatibility. "
            "Mode presets and full presets are preferred for new saves."
        )
        self.preset_legacy_note_label.setWordWrap(True)
        self.preset_legacy_note_label.setStyleSheet("color: #cfcfcf; font-size: 11px;")
        self.preset_legacy_note_label.hide()

        action_row_1 = QHBoxLayout()
        self.presets_load_btn = QPushButton("Load Preset")
        self.presets_delete_btn = QPushButton("Delete Preset")
        self.presets_rename_btn = QPushButton("Rename Preset")
        self.presets_duplicate_btn = QPushButton("Duplicate Preset")

        action_row_1.addWidget(self.presets_load_btn)
        action_row_1.addWidget(self.presets_delete_btn)
        action_row_1.addWidget(self.presets_rename_btn)
        action_row_1.addWidget(self.presets_duplicate_btn)

        action_row_2 = QHBoxLayout()
        self.presets_import_btn = QPushButton("Import Preset")
        self.presets_export_btn = QPushButton("Export Preset")
        self.presets_reset_btn = QPushButton("Reset Preset Fields")

        action_row_2.addWidget(self.presets_import_btn)
        action_row_2.addWidget(self.presets_export_btn)
        action_row_2.addWidget(self.presets_reset_btn)
        action_row_2.addStretch()

        manager_layout.addWidget(self.presets_list)
        manager_layout.addLayout(detail_form)
        manager_layout.addWidget(self.preset_legacy_note_label)
        manager_layout.addLayout(action_row_1)
        manager_layout.addLayout(action_row_2)

        self.presets_layout.addWidget(manager_group)
        self._register_search_target(
            self.presets_tab,
            manager_group,
            "preset manager mode preset tool preset full preset filters load delete rename duplicate import export notes",
        )

        self.presets_layout.addStretch()

        self.preset_type_filter_combo.currentTextChanged.connect(self._refresh_preset_manager)
        self.preset_tool_filter_combo.currentTextChanged.connect(self._refresh_preset_manager)
        self.preset_mode_filter_combo.currentTextChanged.connect(self._refresh_preset_manager)

        self.presets_list.itemSelectionChanged.connect(self._sync_selected_preset_details)

        self.presets_load_btn.clicked.connect(self._load_selected_preset)
        self.presets_delete_btn.clicked.connect(self._delete_selected_preset)
        self.presets_rename_btn.clicked.connect(self._rename_selected_preset)
        self.presets_duplicate_btn.clicked.connect(self._duplicate_selected_preset)
        self.presets_import_btn.clicked.connect(self._import_preset_from_file)
        self.presets_export_btn.clicked.connect(self._export_selected_preset)
        self.presets_reset_btn.clicked.connect(self._reset_presets_tab_fields)

    def _build_shortcuts_tab(self):
        intro_label = QLabel(
            "These shortcuts are used by the menu actions. Leave a field empty to remove that shortcut."
        )
        intro_label.setWordWrap(True)
        self.shortcuts_layout.addWidget(intro_label)

        shortcuts_group = QGroupBox("Keyboard Shortcuts")
        form = QFormLayout(shortcuts_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.shortcut_edits = {}

        shortcut_fields = [
            ("open_files", "Open Files"),
            ("open_folder", "Open Folder"),
            ("open_preferences", "Open Preferences"),
            ("undo", "Undo"),
            ("redo", "Redo"),
            ("reset_edits", "Reset Edits"),
            ("preview_mode", "Preview Mode"),
            ("edit_mode", "Edit Mode"),
            ("show_before", "Show Before"),
            ("show_after", "Show After"),
            ("zoom_in", "Zoom In"),
            ("zoom_out", "Zoom Out"),
        ]

        for key, label in shortcut_fields:
            editor = QKeySequenceEdit()
            self.shortcut_edits[key] = editor
            form.addRow(label, editor)

        self.shortcuts_layout.addWidget(shortcuts_group)
        self._register_search_target(
            self.shortcuts_tab,
            shortcuts_group,
            "shortcuts open files open folder open preferences undo redo reset edits preview mode edit mode show before show after zoom in zoom out",
        )

        self.shortcuts_reset_btn = QPushButton("Reset Shortcuts")
        self.shortcuts_reset_btn.clicked.connect(self._reset_shortcuts_tab)
        self.shortcuts_layout.addWidget(self.shortcuts_reset_btn)
        self._register_search_target(self.shortcuts_tab, self.shortcuts_reset_btn, "reset shortcuts")

        self.shortcuts_layout.addStretch()

    def _builtin_defaults(self):
        return {
            "general": {
                "model": "u2netp",
                "action": "Process",
                "target": "Selected",
                "startup_preset": "",
                "view_mode": "list",
                "thumbnail_mode": "working",
                "output_format": "PNG",
                "background_mode": "Transparent",
                "background_color": "White",
                "open_output_after_export": False,
                "export_zip": False,
                "overwrite_exports": False,
                "skip_exported": False,
                "skip_processed": False,
                "include_subfolders": False,
            },
            "editor_modes": {
                "Erase": {
                    "Brush": {
                        "brush_size": 42,
                        "softness": 35,
                        "opacity": 100,
                        "flow": 100,
                        "spacing": 1,
                        "tolerance": 35,
                        "magic_mode": "Connected Region",
                        "edge_protect": True,
                        "smart_feather": 0,
                        "smart_expand": 1,
                        "smart_cleanup_holes": True,
                        "smart_cleanup_speckles": True,
                    },
                    "Smart Selection": {
                        "brush_size": 42,
                        "softness": 35,
                        "opacity": 100,
                        "flow": 100,
                        "spacing": 1,
                        "tolerance": 35,
                        "magic_mode": "Connected Region",
                        "edge_protect": True,
                        "smart_feather": 0,
                        "smart_expand": 1,
                        "smart_cleanup_holes": True,
                        "smart_cleanup_speckles": True,
                    },
                },
                "Restore": {
                    "Brush": {
                        "brush_size": 42,
                        "softness": 45,
                        "opacity": 100,
                        "flow": 100,
                        "spacing": 1,
                        "tolerance": 35,
                        "magic_mode": "Connected Region",
                        "edge_protect": True,
                        "smart_feather": 0,
                        "smart_expand": 1,
                        "smart_cleanup_holes": True,
                        "smart_cleanup_speckles": True,
                    },
                    "Smart Selection": {
                        "brush_size": 42,
                        "softness": 45,
                        "opacity": 100,
                        "flow": 100,
                        "spacing": 1,
                        "tolerance": 35,
                        "magic_mode": "Connected Region",
                        "edge_protect": True,
                        "smart_feather": 0,
                        "smart_expand": 1,
                        "smart_cleanup_holes": True,
                        "smart_cleanup_speckles": True,
                    },
                },
                "Magic Erase": {
                    "Brush": {
                        "brush_size": 36,
                        "softness": 55,
                        "opacity": 100,
                        "flow": 100,
                        "spacing": 1,
                        "tolerance": 24,
                        "magic_mode": "Connected Region",
                        "edge_protect": True,
                        "smart_feather": 0,
                        "smart_expand": 1,
                        "smart_cleanup_holes": True,
                        "smart_cleanup_speckles": True,
                    },
                    "Smart Selection": {
                        "brush_size": 36,
                        "softness": 55,
                        "opacity": 100,
                        "flow": 100,
                        "spacing": 1,
                        "tolerance": 24,
                        "magic_mode": "Connected Region",
                        "edge_protect": True,
                        "smart_feather": 0,
                        "smart_expand": 1,
                        "smart_cleanup_holes": True,
                        "smart_cleanup_speckles": True,
                    },
                },
                "Background Erase": {
                    "Brush": {
                        "brush_size": 36,
                        "softness": 55,
                        "opacity": 100,
                        "flow": 100,
                        "spacing": 1,
                        "tolerance": 20,
                        "magic_mode": "Connected Region",
                        "edge_protect": True,
                        "smart_feather": 0,
                        "smart_expand": 1,
                        "smart_cleanup_holes": True,
                        "smart_cleanup_speckles": True,
                    },
                    "Smart Selection": {
                        "brush_size": 36,
                        "softness": 55,
                        "opacity": 100,
                        "flow": 100,
                        "spacing": 1,
                        "tolerance": 20,
                        "magic_mode": "Connected Region",
                        "edge_protect": True,
                        "smart_feather": 0,
                        "smart_expand": 1,
                        "smart_cleanup_holes": True,
                        "smart_cleanup_speckles": True,
                    },
                },
            },
            "shortcuts": {
                "open_files": "Ctrl+O",
                "open_folder": "Ctrl+Shift+O",
                "open_preferences": "Ctrl+,",
                "undo": "Ctrl+Z",
                "redo": "Ctrl+Y",
                "reset_edits": "Ctrl+Shift+R",
                "preview_mode": "Ctrl+1",
                "edit_mode": "Ctrl+2",
                "show_before": "Ctrl+B",
                "show_after": "Ctrl+N",
                "zoom_in": "Ctrl+=",
                "zoom_out": "Ctrl+-",
            },
        }

    def _tool_key(self, tool_name: str) -> str:
        return tool_name.lower().replace(" ", "_")

    def _mode_key(self, mode_name: str) -> str:
        return mode_name.lower().replace(" ", "_")
        
    def _saved_startup_preset_name(self) -> str:
        preset_name = self.settings.value("prefs/startup_preset_name", "", type=str)
        preset_name = str(preset_name).strip()

        if not preset_name:
            preset_name = self.settings.value("prefs/startup_preset", "", type=str)
            preset_name = str(preset_name).strip()

        return preset_name

    def _tool_preset_names(self) -> list[str]:
        names = self.settings.value("tool_presets/names", [], type=list)
        if names is None:
            return []
        return [str(name) for name in names if str(name).strip()]

    def _save_tool_preset_names(self, names: list[str]):
        cleaned = sorted([name for name in names if name.strip()], key=str.lower)
        self.settings.setValue("tool_presets/names", cleaned)

    def _full_preset_names(self) -> list[str]:
        names = self.settings.value("editor_presets/names", [], type=list)
        if names is None:
            return []
        return [str(name) for name in names if str(name).strip()]

    def _save_full_preset_names(self, names: list[str]):
        cleaned = sorted([name for name in names if name.strip()], key=str.lower)
        self.settings.setValue("editor_presets/names", cleaned)

    def _internal_scope_to_summary(self, scope: str) -> tuple[str, str]:
        if scope == "mode_brush":
            return "Mode Preset", "Brush"
        if scope == "mode_smart_selection":
            return "Mode Preset", "Smart Selection"
        if scope == "tool":
            return "Legacy Tool Preset", "Both Modes"
        return "Full Preset", "All Modes"

    def _next_default_mode_preset_name(self, tool_name: str, mode_name: str) -> str:
        existing = set(self._tool_preset_names())
        prefix = f"{tool_name} - {mode_name}"
        index = 1
        while True:
            candidate = f"{prefix} - {index}"
            if candidate not in existing:
                return candidate
            index += 1

    def _next_default_full_preset_name(self) -> str:
        existing = set(self._full_preset_names())
        index = 1
        while True:
            candidate = f"Full Preset - {index}"
            if candidate not in existing:
                return candidate
            index += 1

    def _ensure_default_preset_names(self):
        if not self.editor_full_preset_name_edit.text().strip():
            self.editor_full_preset_name_edit.setText(self._next_default_full_preset_name())

    def _collect_mode_values(self, tool_name: str, mode_name: str) -> dict:
        widgets = self.tool_mode_sections[tool_name][mode_name]
        return {
            "brush_size": widgets["brush_size_slider"].value(),
            "softness": widgets["softness_slider"].value(),
            "opacity": widgets["opacity_slider"].value(),
            "flow": widgets["flow_slider"].value(),
            "spacing": widgets["spacing_slider"].value(),
            "tolerance": widgets["tolerance_slider"].value(),
            "magic_mode": widgets["magic_mode"].currentText(),
            "edge_protect": widgets["edge_protect"].isChecked(),
            "smart_feather": widgets["smart_feather_slider"].value(),
            "smart_expand": widgets["smart_expand_slider"].value(),
            "smart_cleanup_holes": widgets["smart_cleanup_holes"].isChecked(),
            "smart_cleanup_speckles": widgets["smart_cleanup_speckles"].isChecked(),
        }

    def _collect_tool_values(self, tool_name: str) -> dict:
        data = {}
        for mode_name in self._mode_names():
            data[mode_name] = self._collect_mode_values(tool_name, mode_name)
        return data

    def _collect_full_editor_values(self) -> dict:
        data = {}
        for tool_name in self._tool_names():
            data[tool_name] = self._collect_tool_values(tool_name)
        return data

    def _apply_mode_values(self, tool_name: str, mode_name: str, values: dict):
        widgets = self.tool_mode_sections[tool_name][mode_name]
        widgets["brush_size_slider"].setValue(values.get("brush_size", 42))
        widgets["softness_slider"].setValue(values.get("softness", 35))
        widgets["opacity_slider"].setValue(values.get("opacity", 100))
        widgets["flow_slider"].setValue(values.get("flow", 100))
        widgets["spacing_slider"].setValue(values.get("spacing", 1))
        widgets["tolerance_slider"].setValue(values.get("tolerance", 35))
        widgets["magic_mode"].setCurrentText(values.get("magic_mode", "Connected Region"))
        widgets["edge_protect"].setChecked(values.get("edge_protect", True))
        widgets["smart_feather_slider"].setValue(values.get("smart_feather", 0))
        widgets["smart_expand_slider"].setValue(values.get("smart_expand", 1))
        widgets["smart_cleanup_holes"].setChecked(values.get("smart_cleanup_holes", True))
        widgets["smart_cleanup_speckles"].setChecked(values.get("smart_cleanup_speckles", True))
        self._update_editor_mode_section_visibility(tool_name, mode_name)

    def _update_editor_mode_section_visibility(self, tool_name: str, mode_name: str):
        widgets = self.tool_mode_sections[tool_name][mode_name]
        visibility = self._editor_field_visibility(tool_name, mode_name)

        widgets["brush_size_label"].setVisible(visibility["brush_size"])
        widgets["brush_size_row"].setVisible(visibility["brush_size"])

        widgets["softness_label"].setVisible(visibility["softness"])
        widgets["softness_row"].setVisible(visibility["softness"])

        widgets["opacity_label"].setVisible(visibility["opacity"])
        widgets["opacity_row"].setVisible(visibility["opacity"])

        widgets["flow_label"].setVisible(visibility["flow"])
        widgets["flow_row"].setVisible(visibility["flow"])

        widgets["spacing_label"].setVisible(visibility["spacing"])
        widgets["spacing_row"].setVisible(visibility["spacing"])

        widgets["tolerance_label"].setVisible(visibility["tolerance"])
        widgets["tolerance_row"].setVisible(visibility["tolerance"])

        widgets["magic_mode_label"].setVisible(visibility["magic_mode"])
        widgets["magic_mode"].setVisible(visibility["magic_mode"])

        widgets["edge_protect"].setVisible(visibility["edge_protect"])

        widgets["smart_feather_label"].setVisible(visibility["smart_feather"])
        widgets["smart_feather_row"].setVisible(visibility["smart_feather"])

        widgets["smart_expand_label"].setVisible(visibility["smart_expand"])
        widgets["smart_expand_row"].setVisible(visibility["smart_expand"])

        widgets["smart_cleanup_holes"].setVisible(visibility["smart_cleanup"])
        widgets["smart_cleanup_speckles"].setVisible(visibility["smart_cleanup"])

    def _apply_tool_values(self, tool_name: str, data: dict):
        for mode_name in self._mode_names():
            self._apply_mode_values(tool_name, mode_name, data.get(mode_name, {}))

    def _apply_full_editor_values(self, data: dict):
        for tool_name in self._tool_names():
            self._apply_tool_values(tool_name, data.get(tool_name, {}))

    def _quick_save_mode_preset(self, tool_name: str, mode_name: str):
        preset_name = self._next_default_mode_preset_name(tool_name, mode_name)
        self._save_named_mode_preset(preset_name, tool_name, mode_name, "")

    def _save_mode_preset_with_dialog(self, tool_name: str, mode_name: str):
        dialog = PresetDetailsDialog(
            title=f"Save {tool_name} {mode_name} Preset",
            default_name=self._next_default_mode_preset_name(tool_name, mode_name),
            default_notes="",
            parent=self,
        )
        if dialog.exec():
            preset_name, notes = dialog.values()
            self._save_named_mode_preset(preset_name, tool_name, mode_name, notes)

    def _save_named_mode_preset(self, preset_name: str, tool_name: str, mode_name: str, notes: str):
        preset_name = preset_name.strip()
        if not preset_name:
            preset_name = self._next_default_mode_preset_name(tool_name, mode_name)

        existing_names = self._tool_preset_names()
        if preset_name in existing_names:
            reply = QMessageBox.question(
                self,
                "Overwrite Preset",
                f'A preset named "{preset_name}" already exists.\nOverwrite it?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        tool_key = self._tool_key(tool_name)
        mode_key = self._mode_key(mode_name)

        self.settings.setValue(f"tool_presets/{preset_name}/tool_name", tool_name)
        self.settings.setValue(f"tool_presets/{preset_name}/scope", "mode_brush" if mode_name == "Brush" else "mode_smart_selection")
        self.settings.setValue(f"tool_presets/{preset_name}/mode_name", mode_name)
        self.settings.setValue(f"tool_presets/{preset_name}/notes", notes.strip())

        values = self._collect_mode_values(tool_name, mode_name)
        for key, value in values.items():
            self.settings.setValue(f"tool_presets/{preset_name}/{tool_key}/{mode_key}/{key}", value)

        if preset_name not in existing_names:
            existing_names.append(preset_name)
            self._save_tool_preset_names(existing_names)

        self.settings.sync()
        self._refresh_preset_manager()

        QMessageBox.information(self, "Preset Saved", f'Saved preset "{preset_name}".')

    def _load_named_tool_preset(self, preset_name: str):
        tool_name = self.settings.value(f"tool_presets/{preset_name}/tool_name", "", type=str)
        scope = self.settings.value(f"tool_presets/{preset_name}/scope", "tool", type=str)
        mode_name = self.settings.value(f"tool_presets/{preset_name}/mode_name", "", type=str)

        if not tool_name or tool_name not in self._tool_names():
            QMessageBox.warning(self, "Load Failed", f'Preset "{preset_name}" is missing a valid tool.')
            return

        builtin_defaults = self._builtin_defaults()["editor_modes"][tool_name]
        tool_key = self._tool_key(tool_name)

        if scope == "mode_brush":
            mode_names = ["Brush"]
        elif scope == "mode_smart_selection":
            mode_names = ["Smart Selection"]
        elif scope == "tool":
            mode_names = self._mode_names()
        else:
            mode_names = [mode_name] if mode_name else []

        for current_mode_name in mode_names:
            mode_key = self._mode_key(current_mode_name)
            mode_defaults = builtin_defaults[current_mode_name]
            values = {
                "brush_size": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/brush_size",
                    mode_defaults["brush_size"],
                    type=int,
                ),
                "softness": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/softness",
                    mode_defaults["softness"],
                    type=int,
                ),
                "opacity": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/opacity",
                    mode_defaults["opacity"],
                    type=int,
                ),
                "flow": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/flow",
                    mode_defaults.get("flow", 100),
                    type=int,
                ),
                "spacing": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/spacing",
                    mode_defaults["spacing"],
                    type=int,
                ),
                "tolerance": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/tolerance",
                    mode_defaults["tolerance"],
                    type=int,
                ),
                "magic_mode": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/magic_mode",
                    mode_defaults["magic_mode"],
                    type=str,
                ),
                "edge_protect": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/edge_protect",
                    mode_defaults["edge_protect"],
                    type=bool,
                ),
                "smart_feather": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_feather",
                    mode_defaults.get("smart_feather", 0),
                    type=int,
                ),
                "smart_expand": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_expand",
                    mode_defaults.get("smart_expand", 1),
                    type=int,
                ),
                "smart_cleanup_holes": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_holes",
                    mode_defaults.get("smart_cleanup_holes", True),
                    type=bool,
                ),
                "smart_cleanup_speckles": self.settings.value(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_speckles",
                    mode_defaults.get("smart_cleanup_speckles", True),
                    type=bool,
                ),
            }
            self._apply_mode_values(tool_name, current_mode_name, values)

        QMessageBox.information(self, "Preset Loaded", f'Loaded preset "{preset_name}".')

    def _save_named_full_preset(self, preset_name: str, notes: str):
        preset_name = preset_name.strip()
        if not preset_name:
            preset_name = self._next_default_full_preset_name()

        existing_names = self._full_preset_names()
        if preset_name in existing_names:
            reply = QMessageBox.question(
                self,
                "Overwrite Preset",
                f'A preset named "{preset_name}" already exists.\nOverwrite it?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        data = self._collect_full_editor_values()

        for tool_name, mode_map in data.items():
            tool_key = self._tool_key(tool_name)
            for mode_name, values in mode_map.items():
                mode_key = self._mode_key(mode_name)
                for key, value in values.items():
                    self.settings.setValue(f"editor_presets/{preset_name}/{tool_key}/{mode_key}/{key}", value)

        self.settings.setValue(f"editor_presets/{preset_name}/notes", notes.strip())

        if preset_name not in existing_names:
            existing_names.append(preset_name)
            self._save_full_preset_names(existing_names)

        self.settings.sync()
        self._refresh_startup_preset_combo()
        self._refresh_preset_manager()

        QMessageBox.information(self, "Preset Saved", f'Saved preset "{preset_name}".')

    def _load_named_full_preset(self, preset_name: str):
        builtin_defaults = self._builtin_defaults()["editor_modes"]
        data = {}

        for tool_name in self._tool_names():
            tool_key = self._tool_key(tool_name)
            data[tool_name] = {}

            for mode_name in self._mode_names():
                mode_key = self._mode_key(mode_name)
                mode_defaults = builtin_defaults[tool_name][mode_name]
                data[tool_name][mode_name] = {
                    "brush_size": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/brush_size",
                        mode_defaults["brush_size"],
                        type=int,
                    ),
                    "softness": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/softness",
                        mode_defaults["softness"],
                        type=int,
                    ),
                    "opacity": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/opacity",
                        mode_defaults["opacity"],
                        type=int,
                    ),
                    "flow": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/flow",
                        mode_defaults.get("flow", 100),
                        type=int,
                    ),
                    "spacing": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/spacing",
                        mode_defaults["spacing"],
                        type=int,
                    ),
                    "tolerance": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/tolerance",
                        mode_defaults["tolerance"],
                        type=int,
                    ),
                    "magic_mode": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/magic_mode",
                        mode_defaults["magic_mode"],
                        type=str,
                    ),
                    "edge_protect": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/edge_protect",
                        mode_defaults["edge_protect"],
                        type=bool,
                    ),
                    "smart_feather": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_feather",
                        mode_defaults.get("smart_feather", 0),
                        type=int,
                    ),
                    "smart_expand": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_expand",
                        mode_defaults.get("smart_expand", 1),
                        type=int,
                    ),
                    "smart_cleanup_holes": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_holes",
                        mode_defaults.get("smart_cleanup_holes", True),
                        type=bool,
                    ),
                    "smart_cleanup_speckles": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_speckles",
                        mode_defaults.get("smart_cleanup_speckles", True),
                        type=bool,
                    ),
                }

        self._apply_full_editor_values(data)
        QMessageBox.information(self, "Preset Loaded", f'Loaded preset "{preset_name}".')

    def _delete_named_tool_preset_without_prompt(self, preset_name: str):
        tool_name = self.settings.value(f"tool_presets/{preset_name}/tool_name", "", type=str)
        if tool_name:
            tool_key = self._tool_key(tool_name)
            for mode_name in self._mode_names():
                mode_key = self._mode_key(mode_name)
                self.settings.remove(f"tool_presets/{preset_name}/{tool_key}/{mode_key}")

        self.settings.remove(f"tool_presets/{preset_name}/tool_name")
        self.settings.remove(f"tool_presets/{preset_name}/scope")
        self.settings.remove(f"tool_presets/{preset_name}/mode_name")
        self.settings.remove(f"tool_presets/{preset_name}/notes")

        names = [name for name in self._tool_preset_names() if name != preset_name]
        self._save_tool_preset_names(names)

    def _delete_named_full_preset_without_prompt(self, preset_name: str):
        for tool_name in self._tool_names():
            tool_key = self._tool_key(tool_name)
            for mode_name in self._mode_names():
                mode_key = self._mode_key(mode_name)
                self.settings.remove(f"editor_presets/{preset_name}/{tool_key}/{mode_key}")

        self.settings.remove(f"editor_presets/{preset_name}/notes")

        names = [name for name in self._full_preset_names() if name != preset_name]
        self._save_full_preset_names(names)

    def _all_presets(self):
        entries = []

        for name in self._tool_preset_names():
            scope = self.settings.value(f"tool_presets/{name}/scope", "tool", type=str)
            tool_name = self.settings.value(f"tool_presets/{name}/tool_name", "", type=str)
            mode_name = self.settings.value(f"tool_presets/{name}/mode_name", "", type=str)
            notes = self.settings.value(f"tool_presets/{name}/notes", "", type=str)

            display_type, display_mode = self._internal_scope_to_summary(scope)

            entries.append({
                "store": "tool",
                "name": name,
                "scope": scope,
                "type_label": display_type,
                "tool_name": tool_name or "-",
                "mode_name": display_mode if not mode_name else mode_name,
                "notes": notes,
            })

        for name in self._full_preset_names():
            notes = self.settings.value(f"editor_presets/{name}/notes", "", type=str)
            entries.append({
                "store": "full",
                "name": name,
                "scope": "full",
                "type_label": "Full Preset",
                "tool_name": "All Tools",
                "mode_name": "All Modes",
                "notes": notes,
            })

        return sorted(entries, key=lambda item: item["name"].lower())

    def _format_preset_entry_label(self, entry: dict) -> str:
        preset_name = entry["name"]
        scope = entry["scope"]
        tool_name = entry["tool_name"]
        mode_name = entry["mode_name"]

        if scope in ("mode_brush", "mode_smart_selection"):
            return f"[Mode] {tool_name} / {mode_name} — {preset_name}"

        if scope == "tool":
            return f"[Legacy] {tool_name} — {preset_name}"

        return f"[Full] {preset_name}"

    def _filtered_presets(self):
        type_filter = self.preset_type_filter_combo.currentText()
        tool_filter = self.preset_tool_filter_combo.currentText()
        mode_filter = self.preset_mode_filter_combo.currentText()

        entries = []
        for entry in self._all_presets():
            if type_filter == "Mode Presets" and entry["scope"] not in ("mode_brush", "mode_smart_selection"):
                continue
            if type_filter == "Full Presets" and entry["scope"] != "full":
                continue
            if type_filter == "Legacy Tool Presets" and entry["scope"] != "tool":
                continue

            if tool_filter != "All Tools":
                if entry["scope"] == "full":
                    continue
                if entry["tool_name"] != tool_filter:
                    continue

            if mode_filter != "All Modes":
                if entry["scope"] == "full":
                    continue
                if entry["mode_name"] != mode_filter:
                    continue

            entries.append(entry)

        return entries

    def _refresh_preset_manager(self):
        current_name = ""
        current_entry = self._selected_preset_entry()
        if current_entry is not None:
            current_name = current_entry["name"]

        self.presets_list.clear()

        for entry in self._filtered_presets():
            item = QListWidgetItem(self._format_preset_entry_label(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.presets_list.addItem(item)

        if current_name:
            for index in range(self.presets_list.count()):
                item = self.presets_list.item(index)
                entry = item.data(Qt.ItemDataRole.UserRole)
                if entry and entry.get("name") == current_name:
                    self.presets_list.setCurrentItem(item)
                    break

        self._sync_selected_preset_details()

    def _selected_preset_entry(self):
        item = self.presets_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _sync_selected_preset_details(self):
        entry = self._selected_preset_entry()
        if entry is None:
            self.preset_selected_type_label.setText("-")
            self.preset_selected_tool_label.setText("-")
            self.preset_selected_mode_label.setText("-")
            self.preset_name_edit.clear()
            self.preset_notes_edit.clear()
            self.preset_legacy_note_label.hide()
            return

        self.preset_selected_type_label.setText(entry["type_label"])
        self.preset_selected_tool_label.setText(entry["tool_name"])
        self.preset_selected_mode_label.setText(entry["mode_name"])
        self.preset_name_edit.setText(entry["name"])
        self.preset_notes_edit.setPlainText(entry["notes"])

        self.preset_legacy_note_label.setVisible(entry.get("scope") == "tool")

    def _load_selected_preset(self):
        entry = self._selected_preset_entry()
        if entry is None:
            QMessageBox.information(self, "No Preset Selected", "Select a preset first.")
            return

        if entry["store"] == "tool":
            self._load_named_tool_preset(entry["name"])
        else:
            self._load_named_full_preset(entry["name"])

    def _delete_selected_preset(self):
        entry = self._selected_preset_entry()
        if entry is None:
            QMessageBox.information(self, "No Preset Selected", "Select a preset first.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Preset",
            f'Delete preset "{entry["name"]}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if entry["store"] == "tool":
            self._delete_named_tool_preset_without_prompt(entry["name"])
        else:
            self._delete_named_full_preset_without_prompt(entry["name"])
            if self.settings.value("prefs/startup_preset", "", type=str) == entry["name"]:
                self.settings.setValue("prefs/startup_preset", "")

        self.settings.sync()
        self._refresh_startup_preset_combo()
        self._refresh_preset_manager()

    def _rename_selected_preset(self):
        entry = self._selected_preset_entry()
        if entry is None:
            QMessageBox.information(self, "No Preset Selected", "Select a preset first.")
            return

        old_name = entry["name"]
        new_name = self.preset_name_edit.text().strip()

        if not new_name:
            QMessageBox.information(self, "Preset Name Required", "Enter a new preset name first.")
            return

        if new_name == old_name:
            return

        all_names = {item["name"] for item in self._all_presets()}
        if new_name in all_names:
            QMessageBox.information(self, "Name Already Exists", f'A preset named "{new_name}" already exists.')
            return

        exported = self._export_preset_data(entry)
        if exported is None:
            QMessageBox.warning(self, "Rename Failed", f'Could not read preset "{old_name}".')
            return

        exported["preset_name"] = new_name
        imported = self._import_preset_data(exported, allow_overwrite=False)
        if imported is False:
            return

        if entry["store"] == "tool":
            self._delete_named_tool_preset_without_prompt(old_name)
        else:
            self._delete_named_full_preset_without_prompt(old_name)
            if self.settings.value("prefs/startup_preset", "", type=str) == old_name:
                self.settings.setValue("prefs/startup_preset", new_name)

        self.settings.sync()
        self._refresh_startup_preset_combo()
        self._refresh_preset_manager()

        matches = self.presets_list.findItems(new_name, Qt.MatchFlag.MatchExactly)
        if matches:
            self.presets_list.setCurrentItem(matches[0])

    def _duplicate_selected_preset(self):
        entry = self._selected_preset_entry()
        if entry is None:
            QMessageBox.information(self, "No Preset Selected", "Select a preset first.")
            return

        new_name = self.preset_name_edit.text().strip()
        if not new_name:
            new_name = f'{entry["name"]} Copy'

        all_names = {item["name"] for item in self._all_presets()}
        if new_name in all_names:
            QMessageBox.information(self, "Name Already Exists", f'A preset named "{new_name}" already exists.')
            return

        exported = self._export_preset_data(entry)
        if exported is None:
            QMessageBox.warning(self, "Duplicate Failed", f'Could not read preset "{entry["name"]}".')
            return

        exported["preset_name"] = new_name
        imported = self._import_preset_data(exported, allow_overwrite=False)
        if imported is False:
            return

        self._refresh_startup_preset_combo()
        self._refresh_preset_manager()

        matches = self.presets_list.findItems(new_name, Qt.MatchFlag.MatchExactly)
        if matches:
            self.presets_list.setCurrentItem(matches[0])

    def _export_preset_data(self, entry: dict):
        if entry["store"] == "tool":
            preset_name = entry["name"]
            tool_name = self.settings.value(f"tool_presets/{preset_name}/tool_name", "", type=str)
            if not tool_name:
                return None

            scope = self.settings.value(f"tool_presets/{preset_name}/scope", "tool", type=str)
            data = {
                "version": 2,
                "preset_type": "tool",
                "preset_name": preset_name,
                "tool_name": tool_name,
                "scope": scope,
                "mode_name": self.settings.value(f"tool_presets/{preset_name}/mode_name", "", type=str),
                "notes": self.settings.value(f"tool_presets/{preset_name}/notes", "", type=str),
                "tool_modes": {},
            }

            tool_key = self._tool_key(tool_name)
            builtin_defaults = self._builtin_defaults()["editor_modes"][tool_name]

            if scope == "mode_brush":
                mode_names = ["Brush"]
            elif scope == "mode_smart_selection":
                mode_names = ["Smart Selection"]
            else:
                mode_names = self._mode_names()

            for mode_name in mode_names:
                mode_key = self._mode_key(mode_name)
                mode_defaults = builtin_defaults[mode_name]
                data["tool_modes"][mode_name] = {
                    "brush_size": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/brush_size",
                        mode_defaults["brush_size"],
                        type=int,
                    ),
                    "softness": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/softness",
                        mode_defaults["softness"],
                        type=int,
                    ),
                    "opacity": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/opacity",
                        mode_defaults["opacity"],
                        type=int,
                    ),
                    "flow": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/flow",
                        mode_defaults.get("flow", 100),
                        type=int,
                    ),
                    "spacing": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/spacing",
                        mode_defaults["spacing"],
                        type=int,
                    ),
                    "tolerance": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/tolerance",
                        mode_defaults["tolerance"],
                        type=int,
                    ),
                    "magic_mode": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/magic_mode",
                        mode_defaults["magic_mode"],
                        type=str,
                    ),
                   "edge_protect": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/edge_protect",
                        mode_defaults["edge_protect"],
                        type=bool,
                    ),
                    "smart_feather": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_feather",
                        mode_defaults.get("smart_feather", 0),
                        type=int,
                    ),
                    "smart_expand": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_expand",
                        mode_defaults.get("smart_expand", 1),
                        type=int,
                    ),
                    "smart_cleanup_holes": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_holes",
                        mode_defaults.get("smart_cleanup_holes", True),
                        type=bool,
                    ),
                    "smart_cleanup_speckles": self.settings.value(
                        f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_speckles",
                        mode_defaults.get("smart_cleanup_speckles", True),
                        type=bool,
                    ),
                }

            return data

        preset_name = entry["name"]
        builtin_defaults = self._builtin_defaults()["editor_modes"]
        data = {
            "version": 3,
            "preset_type": "full",
            "preset_name": preset_name,
            "notes": self.settings.value(f"editor_presets/{preset_name}/notes", "", type=str),
            "editor_modes": {},
        }

        for tool_name in self._tool_names():
            tool_key = self._tool_key(tool_name)
            data["editor_modes"][tool_name] = {}

            for mode_name in self._mode_names():
                mode_key = self._mode_key(mode_name)
                mode_defaults = builtin_defaults[tool_name][mode_name]
                data["editor_modes"][tool_name][mode_name] = {
                    "brush_size": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/brush_size",
                        mode_defaults["brush_size"],
                        type=int,
                    ),
                    "softness": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/softness",
                        mode_defaults["softness"],
                        type=int,
                    ),
                    "opacity": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/opacity",
                        mode_defaults["opacity"],
                        type=int,
                    ),
                    "flow": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/flow",
                        mode_defaults.get("flow", 100),
                        type=int,
                    ),
                    "spacing": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/spacing",
                        mode_defaults["spacing"],
                        type=int,
                    ),
                    "tolerance": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/tolerance",
                        mode_defaults["tolerance"],
                        type=int,
                    ),
                    "magic_mode": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/magic_mode",
                        mode_defaults["magic_mode"],
                        type=str,
                    ),
                    "edge_protect": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/edge_protect",
                        mode_defaults["edge_protect"],
                        type=bool,
                    ),
                    "smart_feather": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_feather",
                        mode_defaults.get("smart_feather", 0),
                        type=int,
                    ),
                    "smart_expand": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_expand",
                        mode_defaults.get("smart_expand", 1),
                        type=int,
                    ),
                    "smart_cleanup_holes": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_holes",
                        mode_defaults.get("smart_cleanup_holes", True),
                        type=bool,
                    ),
                    "smart_cleanup_speckles": self.settings.value(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_speckles",
                        mode_defaults.get("smart_cleanup_speckles", True),
                        type=bool,
                    ),
                }

        return data

    def _import_preset_data(self, data: dict, allow_overwrite: bool = True):
        preset_type = str(data.get("preset_type", "")).strip()

        if preset_type == "tool":
            preset_name = str(data.get("preset_name", "")).strip()
            tool_name = str(data.get("tool_name", "")).strip()
            scope = str(data.get("scope", "tool")).strip()

            if not preset_name:
                raise ValueError("Tool preset file is missing a preset name.")
            if not tool_name or tool_name not in self._tool_names():
                raise ValueError("Tool preset file is missing a valid tool name.")

            all_names = {item["name"] for item in self._all_presets()}
            if preset_name in all_names and allow_overwrite:
                reply = QMessageBox.question(
                    self,
                    "Overwrite Preset",
                    f'A preset named "{preset_name}" already exists.\nOverwrite it?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return False

            tool_modes = data.get("tool_modes")
            if not isinstance(tool_modes, dict):
                raise ValueError("Tool preset file is missing tool_modes data.")

            tool_key = self._tool_key(tool_name)
            self.settings.setValue(f"tool_presets/{preset_name}/tool_name", tool_name)
            self.settings.setValue(f"tool_presets/{preset_name}/scope", scope)
            self.settings.setValue(f"tool_presets/{preset_name}/notes", str(data.get("notes", "")).strip())

            if scope == "mode_brush":
                self.settings.setValue(f"tool_presets/{preset_name}/mode_name", "Brush")
                mode_names = ["Brush"]
            elif scope == "mode_smart_selection":
                self.settings.setValue(f"tool_presets/{preset_name}/mode_name", "Smart Selection")
                mode_names = ["Smart Selection"]
            else:
                self.settings.remove(f"tool_presets/{preset_name}/mode_name")
                mode_names = self._mode_names()

            builtin_defaults = self._builtin_defaults()["editor_modes"][tool_name]

            for mode_name in mode_names:
                mode_data = tool_modes.get(mode_name, {})
                if not isinstance(mode_data, dict):
                    mode_data = {}
                defaults = builtin_defaults[mode_name]
                mode_key = self._mode_key(mode_name)

                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/brush_size",
                    int(mode_data.get("brush_size", defaults["brush_size"])),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/softness",
                    int(mode_data.get("softness", defaults["softness"])),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/opacity",
                    int(mode_data.get("opacity", defaults["opacity"])),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/flow",
                    int(mode_data.get("flow", defaults.get("flow", 100))),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/spacing",
                    int(mode_data.get("spacing", defaults["spacing"])),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/tolerance",
                    int(mode_data.get("tolerance", defaults["tolerance"])),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/magic_mode",
                    str(mode_data.get("magic_mode", defaults["magic_mode"])),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/edge_protect",
                    bool(mode_data.get("edge_protect", defaults["edge_protect"])),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_feather",
                    int(mode_data.get("smart_feather", defaults.get("smart_feather", 0))),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_expand",
                    int(mode_data.get("smart_expand", defaults.get("smart_expand", 1))),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_holes",
                    bool(mode_data.get("smart_cleanup_holes", defaults.get("smart_cleanup_holes", True))),
                )
                self.settings.setValue(
                    f"tool_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_speckles",
                    bool(mode_data.get("smart_cleanup_speckles", defaults.get("smart_cleanup_speckles", True))),
                )

            names = self._tool_preset_names()
            if preset_name not in names:
                names.append(preset_name)
                self._save_tool_preset_names(names)

            self.settings.sync()
            return True

        if preset_type == "full":
            preset_name = str(data.get("preset_name", "")).strip()
            if not preset_name:
                raise ValueError("Full preset file is missing a preset name.")

            all_names = {item["name"] for item in self._all_presets()}
            if preset_name in all_names and allow_overwrite:
                reply = QMessageBox.question(
                    self,
                    "Overwrite Preset",
                    f'A preset named "{preset_name}" already exists.\nOverwrite it?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return False

            editor_modes = data.get("editor_modes")
            if not isinstance(editor_modes, dict):
                raise ValueError("Full preset file is missing editor_modes data.")

            builtin_defaults = self._builtin_defaults()["editor_modes"]

            for tool_name in self._tool_names():
                tool_key = self._tool_key(tool_name)
                tool_data = editor_modes.get(tool_name, {})
                if not isinstance(tool_data, dict):
                    tool_data = {}

                for mode_name in self._mode_names():
                    mode_data = tool_data.get(mode_name, {})
                    if not isinstance(mode_data, dict):
                        mode_data = {}
                    defaults = builtin_defaults[tool_name][mode_name]
                    mode_key = self._mode_key(mode_name)

                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/brush_size",
                        int(mode_data.get("brush_size", defaults["brush_size"])),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/softness",
                        int(mode_data.get("softness", defaults["softness"])),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/opacity",
                        int(mode_data.get("opacity", defaults["opacity"])),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/flow",
                        int(mode_data.get("flow", defaults.get("flow", 100))),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/spacing",
                        int(mode_data.get("spacing", defaults["spacing"])),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/tolerance",
                        int(mode_data.get("tolerance", defaults["tolerance"])),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/magic_mode",
                        str(mode_data.get("magic_mode", defaults["magic_mode"])),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/edge_protect",
                        bool(mode_data.get("edge_protect", defaults["edge_protect"])),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_feather",
                        int(mode_data.get("smart_feather", defaults.get("smart_feather", 0))),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_expand",
                        int(mode_data.get("smart_expand", defaults.get("smart_expand", 1))),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_holes",
                        bool(mode_data.get("smart_cleanup_holes", defaults.get("smart_cleanup_holes", True))),
                    )
                    self.settings.setValue(
                        f"editor_presets/{preset_name}/{tool_key}/{mode_key}/smart_cleanup_speckles",
                        bool(mode_data.get("smart_cleanup_speckles", defaults.get("smart_cleanup_speckles", True))),
                    )

            self.settings.setValue(f"editor_presets/{preset_name}/notes", str(data.get("notes", "")).strip())

            names = self._full_preset_names()
            if preset_name not in names:
                names.append(preset_name)
                self._save_full_preset_names(names)

            self.settings.sync()
            return True

        raise ValueError("Unknown preset type.")

    def _import_preset_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Preset",
            "",
            "JSON Files (*.json)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            imported = self._import_preset_data(data, allow_overwrite=True)
            if imported:
                self._refresh_startup_preset_combo()
                self._refresh_preset_manager()
                preset_name = str(data.get("preset_name", "")).strip()
                matches = self.presets_list.findItems(preset_name, Qt.MatchFlag.MatchExactly)
                if matches:
                    self.presets_list.setCurrentItem(matches[0])
                QMessageBox.information(self, "Preset Imported", f'Imported preset "{preset_name}".')
        except Exception as e:
            QMessageBox.warning(self, "Import Failed", f"Could not import preset.\n\n{e}")

    def _export_selected_preset(self):
        entry = self._selected_preset_entry()
        if entry is None:
            QMessageBox.information(self, "No Preset Selected", "Select a preset first.")
            return

        export_data = self._export_preset_data(entry)
        if export_data is None:
            QMessageBox.warning(self, "Export Failed", f'Could not read preset "{entry["name"]}".')
            return

        suggested_name = f'{entry["name"]}.json'
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Preset",
            suggested_name,
            "JSON Files (*.json)",
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".json"):
            file_path += ".json"

        try:
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(export_data, handle, indent=2)
            QMessageBox.information(self, "Preset Exported", f'Exported preset "{entry["name"]}".')
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Could not export preset.\n\n{e}")

    def _save_full_preset_from_editor_tab(self):
        preset_name = self.editor_full_preset_name_edit.text().strip()
        if not preset_name:
            preset_name = self._next_default_full_preset_name()
        self._save_named_full_preset(preset_name, self.editor_full_preset_notes_edit.toPlainText())

    def _reset_general_tab(self):
        defaults = self._builtin_defaults()["general"]
        self.default_model_combo.setCurrentText(defaults["model"])
        self.default_action_combo.setCurrentText(defaults["action"])
        self.default_target_combo.setCurrentText(defaults["target"])
        self.default_view_mode_combo.setCurrentText(defaults["view_mode"])
        self.default_thumbnail_mode_combo.setCurrentText(defaults["thumbnail_mode"])
        self.default_output_format_combo.setCurrentText(defaults["output_format"])
        self.default_background_mode_combo.setCurrentText(defaults["background_mode"])
        self.default_background_color_combo.setCurrentText(defaults["background_color"])
        self.default_open_output_after_export_check.setChecked(defaults["open_output_after_export"])
        self.default_export_zip_check.setChecked(defaults["export_zip"])
        self.default_overwrite_exports_check.setChecked(defaults["overwrite_exports"])
        self.default_skip_exported_check.setChecked(defaults["skip_exported"])
        self.default_skip_processed_check.setChecked(defaults["skip_processed"])
        self.default_include_subfolders_check.setChecked(defaults["include_subfolders"])
        self._refresh_startup_preset_combo()
        self.default_startup_preset_combo.setCurrentIndex(0)

    def _reset_editor_tab(self):
        defaults = self._builtin_defaults()["editor_modes"]
        for tool_name in self._tool_names():
            for mode_name in self._mode_names():
                widgets = self.tool_mode_sections[tool_name][mode_name]
                mode_defaults = defaults[tool_name][mode_name]
                widgets["brush_size_slider"].setValue(mode_defaults["brush_size"])
                widgets["softness_slider"].setValue(mode_defaults["softness"])
                widgets["opacity_slider"].setValue(mode_defaults["opacity"])
                widgets["flow_slider"].setValue(mode_defaults.get("flow", 100))
                widgets["spacing_slider"].setValue(mode_defaults["spacing"])
                widgets["tolerance_slider"].setValue(mode_defaults["tolerance"])
                widgets["magic_mode"].setCurrentText(mode_defaults["magic_mode"])
                widgets["edge_protect"].setChecked(mode_defaults["edge_protect"])
                widgets["smart_feather_slider"].setValue(mode_defaults.get("smart_feather", 0))
                widgets["smart_expand_slider"].setValue(mode_defaults.get("smart_expand", 1))
                widgets["smart_cleanup_holes"].setChecked(mode_defaults.get("smart_cleanup_holes", True))
                widgets["smart_cleanup_speckles"].setChecked(mode_defaults.get("smart_cleanup_speckles", True))
                self._update_editor_mode_section_visibility(tool_name, mode_name)

        self.editor_full_preset_name_edit.setText(self._next_default_full_preset_name())
        self.editor_full_preset_notes_edit.clear()

    def _reset_presets_tab_fields(self):
        self.presets_list.clearSelection()
        self.preset_selected_type_label.setText("-")
        self.preset_selected_tool_label.setText("-")
        self.preset_selected_mode_label.setText("-")
        self.preset_name_edit.clear()
        self.preset_notes_edit.clear()

    def _reset_shortcuts_tab(self):
        defaults = self._builtin_defaults()["shortcuts"]
        for key, editor in self.shortcut_edits.items():
            editor.setKeySequence(QKeySequence(defaults[key]))

    def _reset_to_builtin_defaults(self):
        self._reset_general_tab()
        self._reset_editor_tab()
        self._reset_shortcuts_tab()
        self._reset_presets_tab_fields()

    def _refresh_startup_preset_combo(self):
        current_value = self._saved_startup_preset_name()
        print(f"DEBUG LOAD: _saved_startup_preset_name={repr(current_value)}, full_preset_names={self._full_preset_names()}")

        self.default_startup_preset_combo.blockSignals(True)
        self.default_startup_preset_combo.clear()
        self.default_startup_preset_combo.addItem("None", "")

        preset_names = self._full_preset_names()
        for preset_name in preset_names:
            clean_name = str(preset_name).strip()
            self.default_startup_preset_combo.addItem(clean_name, clean_name)

        index = self.default_startup_preset_combo.findData(current_value)

        if index < 0 and current_value:
            index = self.default_startup_preset_combo.findText(current_value)

        if index < 0:
            index = 0

        self.default_startup_preset_combo.setCurrentIndex(index)
        self.default_startup_preset_combo.blockSignals(False)

    def _load_settings(self):
        general_defaults = self._builtin_defaults()["general"]
        editor_defaults = self._builtin_defaults()["editor_modes"]
        shortcut_defaults = self._builtin_defaults()["shortcuts"]

        self.default_model_combo.setCurrentText(
            self.settings.value("prefs/model", general_defaults["model"], type=str)
        )
        self.default_action_combo.setCurrentText(
            self.settings.value("prefs/action", general_defaults["action"], type=str)
        )
        self.default_target_combo.setCurrentText(
            self.settings.value("prefs/target", general_defaults["target"], type=str)
        )
        self.default_view_mode_combo.setCurrentText(
            self.settings.value("prefs/view_mode", general_defaults["view_mode"], type=str)
        )
        self.default_thumbnail_mode_combo.setCurrentText(
            self.settings.value("prefs/thumbnail_mode", general_defaults["thumbnail_mode"], type=str)
        )
        self.default_output_format_combo.setCurrentText(
            self.settings.value("prefs/output_format", general_defaults["output_format"], type=str)
        )
        self.default_background_mode_combo.setCurrentText(
            self.settings.value("prefs/background_mode", general_defaults["background_mode"], type=str)
        )
        self.default_background_color_combo.setCurrentText(
            self.settings.value("prefs/background_color", general_defaults["background_color"], type=str)
        )

        self.default_open_output_after_export_check.setChecked(
            self.settings.value(
                "prefs/open_output_after_export",
                general_defaults["open_output_after_export"],
                type=bool,
            )
        )
        self.default_export_zip_check.setChecked(
            self.settings.value("prefs/export_zip", general_defaults["export_zip"], type=bool)
        )
        self.default_overwrite_exports_check.setChecked(
            self.settings.value(
                "prefs/overwrite_exports",
                general_defaults["overwrite_exports"],
                type=bool,
            )
        )
        self.default_skip_exported_check.setChecked(
            self.settings.value("prefs/skip_exported", general_defaults["skip_exported"], type=bool)
        )
        self.default_skip_processed_check.setChecked(
            self.settings.value("prefs/skip_processed", general_defaults["skip_processed"], type=bool)
        )
        self.default_include_subfolders_check.setChecked(
            self.settings.value(
                "prefs/include_subfolders",
                general_defaults["include_subfolders"],
                type=bool,
            )
        )

        startup_preset = self._saved_startup_preset_name()
        if not startup_preset:
            startup_preset = str(general_defaults["startup_preset"]).strip()

        startup_index = self.default_startup_preset_combo.findData(startup_preset)
        if startup_index < 0 and startup_preset:
            startup_index = self.default_startup_preset_combo.findText(startup_preset)
        if startup_index < 0:
            startup_index = 0

        self.default_startup_preset_combo.setCurrentIndex(startup_index)

        for tool_name in self._tool_names():
            tool_key = self._tool_key(tool_name)
            for mode_name in self._mode_names():
                mode_key = self._mode_key(mode_name)
                defaults = editor_defaults[tool_name][mode_name]

                values = {
                    "brush_size": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/brush_size",
                        defaults["brush_size"],
                        type=int,
                    ),
                    "softness": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/softness",
                        defaults["softness"],
                        type=int,
                    ),
                    "opacity": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/opacity",
                        defaults["opacity"],
                        type=int,
                    ),
                    "flow": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/flow",
                        defaults.get("flow", 100),
                        type=int,
                    ),
                    "spacing": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/spacing",
                        defaults["spacing"],
                        type=int,
                    ),
                    "tolerance": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/tolerance",
                        defaults["tolerance"],
                        type=int,
                    ),
                    "magic_mode": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/magic_mode",
                        defaults["magic_mode"],
                        type=str,
                    ),
                    "edge_protect": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/edge_protect",
                        defaults["edge_protect"],
                        type=bool,
                    ),
                    "smart_feather": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/smart_feather",
                        defaults.get("smart_feather", 0),
                        type=int,
                    ),
                    "smart_expand": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/smart_expand",
                        defaults.get("smart_expand", 1),
                        type=int,
                    ),
                    "smart_cleanup_holes": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/smart_cleanup_holes",
                        defaults.get("smart_cleanup_holes", True),
                        type=bool,
                    ),
                    "smart_cleanup_speckles": self.settings.value(
                        f"editor_defaults/{tool_key}/{mode_key}/smart_cleanup_speckles",
                        defaults.get("smart_cleanup_speckles", True),
                        type=bool,
                    ),
                }

                self._apply_mode_values(tool_name, mode_name, values)

        for key, editor in self.shortcut_edits.items():
            editor.setKeySequence(
                QKeySequence(
                    self.settings.value(f"shortcuts/{key}", shortcut_defaults[key], type=str)
                )
            )

        if hasattr(self, "watch_folder_edit"):
            self.watch_folder_edit.setText(
                self.settings.value("watch/path", "", type=str)
            )
        if hasattr(self, "watch_include_subfolders_check"):
            self.watch_include_subfolders_check.setChecked(
                self.settings.value("watch/include_subfolders", False, type=bool)
            )
        if hasattr(self, "watch_enable_check"):
            self.watch_enable_check.setChecked(False)

        if hasattr(self, "watch_folder_edit"):
            self.watch_folder_edit.setText(
                self.settings.value("watch/path", "", type=str)
            )
        if hasattr(self, "watch_include_subfolders_check"):
            self.watch_include_subfolders_check.setChecked(
                self.settings.value("watch/include_subfolders", False, type=bool)
            )
        if hasattr(self, "watch_enable_check"):
            self.watch_enable_check.setChecked(False)

    def save_settings(self):
        self.settings.setValue("prefs/model", self.default_model_combo.currentText())
        self.settings.setValue("prefs/action", self.default_action_combo.currentText())
        self.settings.setValue("prefs/target", self.default_target_combo.currentText())
        self.settings.setValue("prefs/view_mode", self.default_view_mode_combo.currentText())
        self.settings.setValue("prefs/thumbnail_mode", self.default_thumbnail_mode_combo.currentText())
        self.settings.setValue("prefs/output_format", self.default_output_format_combo.currentText())
        self.settings.setValue("prefs/background_mode", self.default_background_mode_combo.currentText())
        self.settings.setValue("prefs/background_color", self.default_background_color_combo.currentText())
        self.settings.setValue(
            "prefs/open_output_after_export",
            self.default_open_output_after_export_check.isChecked(),
        )
        self.settings.setValue("prefs/export_zip", self.default_export_zip_check.isChecked())
        self.settings.setValue(
            "prefs/overwrite_exports",
            self.default_overwrite_exports_check.isChecked(),
        )
        self.settings.setValue(
            "prefs/skip_exported",
            self.default_skip_exported_check.isChecked(),
        )
        self.settings.setValue(
            "prefs/skip_processed",
            self.default_skip_processed_check.isChecked(),
        )
        self.settings.setValue(
            "prefs/include_subfolders",
            self.default_include_subfolders_check.isChecked(),
        )

        startup_preset = self.default_startup_preset_combo.currentData()
        if startup_preset is None:
            current_text = self.default_startup_preset_combo.currentText().strip()
            startup_preset = "" if current_text == "None" else current_text

        startup_preset = str(startup_preset).strip()

        self.settings.setValue("prefs/startup_preset", startup_preset)
        self.settings.setValue("prefs/startup_preset_name", startup_preset)

        for tool_name in self._tool_names():
            tool_key = self._tool_key(tool_name)
            for mode_name in self._mode_names():
                mode_key = self._mode_key(mode_name)
                values = self._collect_mode_values(tool_name, mode_name)

                for key, value in values.items():
                    self.settings.setValue(
                        f"editor_defaults/{tool_key}/{mode_key}/{key}",
                        value,
                    )

        for key, editor in self.shortcut_edits.items():
            self.settings.setValue(
                f"shortcuts/{key}",
                editor.keySequence().toString(QKeySequence.SequenceFormat.NativeText),
            )

        if hasattr(self, "watch_folder_edit"):
            self.settings.setValue("watch/path", self.watch_folder_edit.text().strip())
        if hasattr(self, "watch_include_subfolders_check"):
            self.settings.setValue(
                "watch/include_subfolders",
                self.watch_include_subfolders_check.isChecked(),
            )

        self.settings.sync()

    def _on_apply(self):
        self.save_settings()
        # Signal the parent to reload without closing the dialog
        parent = self.parent()
        if parent is not None and hasattr(parent, "_on_preferences_applied"):
            parent._on_preferences_applied(self)

    def _on_accept(self):
        self.save_settings()
        self.accept()
