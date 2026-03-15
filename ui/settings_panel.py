from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QCheckBox,
    QSlider,
    QHBoxLayout,
)
from PySide6.QtCore import Qt


class SettingsPanel(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("settingsPanel")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Settings Panel")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.removal_mode_label = QLabel("Removal Mode")
        self.removal_mode_combo = QComboBox()
        self.removal_mode_combo.addItems(["AI Removal", "Color Removal"])
        layout.addWidget(self.removal_mode_label)
        layout.addWidget(self.removal_mode_combo)

        self.model_label = QLabel("Model")
        self.model_combo = QComboBox()
        self.model_combo.addItems(["u2net", "u2netp", "isnet-general-use"])
        self.model_combo.setCurrentText("u2netp")
        layout.addWidget(self.model_label)
        layout.addWidget(self.model_combo)

        self.output_format_label = QLabel("Output Format")
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["PNG", "JPG", "WEBP"])
        self.output_format_combo.setCurrentText("PNG")
        layout.addWidget(self.output_format_label)
        layout.addWidget(self.output_format_combo)

        self.background_mode_label = QLabel("Background Mode")
        self.background_mode_combo = QComboBox()
        self.background_mode_combo.addItems(["Transparent", "Solid Color"])
        self.background_mode_combo.setCurrentText("Transparent")
        layout.addWidget(self.background_mode_label)
        layout.addWidget(self.background_mode_combo)

        self.background_color_label = QLabel("Solid Background Color")
        self.background_color_combo = QComboBox()
        self.background_color_combo.addItems(["White", "Black"])
        layout.addWidget(self.background_color_label)
        layout.addWidget(self.background_color_combo)

        self.output_dir_label = QLabel("Output Directory")
        self.output_dir_edit = QLineEdit()
        self.output_dir_btn = QPushButton("Choose Output Folder")
        self.open_output_btn = QPushButton("Open Output Folder")

        output_btn_row = QHBoxLayout()
        output_btn_row.addWidget(self.output_dir_btn)
        output_btn_row.addWidget(self.open_output_btn)

        layout.addWidget(self.output_dir_label)
        layout.addWidget(self.output_dir_edit)
        layout.addLayout(output_btn_row)

        self.naming_label = QLabel("Filename Suffix")
        self.naming_edit = QLineEdit("_nobg")
        layout.addWidget(self.naming_label)
        layout.addWidget(self.naming_edit)

        self.export_zip_check = QCheckBox("Export successful results as ZIP")
        layout.addWidget(self.export_zip_check)

        self.tool_section_label = QLabel("Editing Tools")
        self.tool_section_label.setObjectName("panelTitle")
        layout.addWidget(self.tool_section_label)

        self.tool_label = QLabel("Tool")
        self.tool_combo = QComboBox()
        self.tool_combo.addItems(["Erase", "Restore", "Magic Erase", "Background Erase"])
        layout.addWidget(self.tool_label)
        layout.addWidget(self.tool_combo)

        self.apply_mode_label = QLabel("Apply Mode")
        self.apply_mode_combo = QComboBox()
        self.apply_mode_combo.addItems(["Brush", "Click"])
        self.apply_mode_combo.setCurrentText("Brush")
        layout.addWidget(self.apply_mode_label)
        layout.addWidget(self.apply_mode_combo)

        self.brush_size_label = QLabel("Brush Size")
        self.brush_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.brush_size_slider.setRange(1, 200)
        self.brush_size_slider.setValue(40)
        layout.addWidget(self.brush_size_label)
        layout.addWidget(self.brush_size_slider)

        self.tolerance_label = QLabel("Tolerance")
        self.tolerance_slider = QSlider(Qt.Orientation.Horizontal)
        self.tolerance_slider.setRange(0, 255)
        self.tolerance_slider.setValue(35)
        layout.addWidget(self.tolerance_label)
        layout.addWidget(self.tolerance_slider)

        self.phase_note = QLabel(
            "Watch folder automation can monitor a folder and auto-load new images."
        )
        self.phase_note.setWordWrap(True)
        layout.addWidget(self.phase_note)

        self.softness_label = QLabel("Softness")
        self.softness_slider = QSlider(Qt.Orientation.Horizontal)
        self.softness_slider.setRange(0, 100)
        self.softness_slider.setValue(35)
        layout.addWidget(self.softness_label)
        layout.addWidget(self.softness_slider)

        self.opacity_label = QLabel("Opacity")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(100)
        layout.addWidget(self.opacity_label)
        layout.addWidget(self.opacity_slider)

        self.spacing_label = QLabel("Spacing")
        self.spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.spacing_slider.setRange(1, 100)
        self.spacing_slider.setValue(20)
        layout.addWidget(self.spacing_label)
        layout.addWidget(self.spacing_slider)

        self.threshold_label = QLabel("Color Threshold")
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 255)
        self.threshold_slider.setValue(30)

        self.pick_color_btn = QPushButton("Pick Color")

        layout.addWidget(self.threshold_label)
        layout.addWidget(self.threshold_slider)
        layout.addWidget(self.pick_color_btn)

        self.watch_section_label = QLabel("Watch Folder")
        self.watch_section_label.setObjectName("panelTitle")
        layout.addWidget(self.watch_section_label)

        self.watch_folder_edit = QLineEdit()
        self.watch_folder_btn = QPushButton("Choose Watch Folder")
        self.watch_include_subfolders_check = QCheckBox("Include subfolders in watch folder")
        self.watch_enable_check = QCheckBox("Enable watch folder automation")
        self.watch_status_label = QLabel("Watch status: Off")

        layout.addWidget(QLabel("Watch Folder Path"))
        layout.addWidget(self.watch_folder_edit)
        layout.addWidget(self.watch_folder_btn)
        layout.addWidget(self.watch_include_subfolders_check)
        layout.addWidget(self.watch_enable_check)
        layout.addWidget(self.watch_status_label)

        self.process_selected_btn = QPushButton("Process Selected")
        self.process_all_btn = QPushButton("Process All")
        self.cancel_btn = QPushButton("Cancel")

        layout.addWidget(self.process_selected_btn)
        layout.addWidget(self.process_all_btn)
        layout.addWidget(self.cancel_btn)
        layout.addStretch()

        self.output_dir_btn.clicked.connect(self.choose_output_dir)
        self.watch_folder_btn.clicked.connect(self.choose_watch_folder)
        self.removal_mode_combo.currentTextChanged.connect(self.update_mode_visibility)
        self.background_mode_combo.currentTextChanged.connect(self.update_background_visibility)
        self.tool_combo.currentTextChanged.connect(self.update_tool_visibility)

        self.update_mode_visibility()
        self.update_background_visibility()
        self.update_tool_visibility()

    def choose_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if folder:
            self.output_dir_edit.setText(folder)

    def choose_watch_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Watch Folder")
        if folder:
            self.watch_folder_edit.setText(folder)

    def update_mode_visibility(self):
        is_color_mode = self.removal_mode_combo.currentText() == "Color Removal"

        self.threshold_label.setVisible(is_color_mode)
        self.threshold_slider.setVisible(is_color_mode)
        self.pick_color_btn.setVisible(is_color_mode)

        self.model_label.setEnabled(not is_color_mode)
        self.model_combo.setEnabled(not is_color_mode)

    def update_background_visibility(self):
        is_solid = self.background_mode_combo.currentText() == "Solid Color"
        self.background_color_label.setVisible(is_solid)
        self.background_color_combo.setVisible(is_solid)

    def update_tool_visibility(self):
        tool_name = self.tool_combo.currentText()
        is_click_tool = tool_name in ("Magic Erase", "Background Erase")

        self.tolerance_label.setVisible(is_click_tool)
        self.tolerance_slider.setVisible(is_click_tool)

        self.brush_size_label.setVisible(not is_click_tool)
        self.brush_size_slider.setVisible(not is_click_tool)

        self.apply_mode_label.setVisible(True)
        self.apply_mode_combo.setVisible(True)

        self.phase_note.setVisible(True)

        self.softness_label.setVisible(True)
        self.softness_slider.setVisible(True)
        self.opacity_label.setVisible(True)
        self.opacity_slider.setVisible(True)
        self.spacing_label.setVisible(True)
        self.spacing_slider.setVisible(True)

        self.softness_slider.setEnabled(False)
        self.opacity_slider.setEnabled(False)
        self.spacing_slider.setEnabled(False)

        self.softness_label.setText("Softness (disabled)")
        self.opacity_label.setText("Opacity (disabled)")
        self.spacing_label.setText("Spacing (disabled)")

        if is_click_tool:
            self.apply_mode_combo.setCurrentText("Click")
            self.apply_mode_combo.setEnabled(False)
        else:
            self.apply_mode_combo.setCurrentText("Brush")
            self.apply_mode_combo.setEnabled(False)
