from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
)


class ThumbnailGrid(QFrame):
    item_selected = Signal(int)

    def __init__(self):
        super().__init__()

        self.setObjectName("thumbnailGrid")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Thumbnail Grid")
        title.setObjectName("panelTitle")

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.IconMode)
        self.list_widget.setResizeMode(QListWidget.Adjust)
        self.list_widget.setMovement(QListWidget.Static)
        self.list_widget.setSpacing(10)
        self.list_widget.setWrapping(True)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setIconSize(QSize(160, 160))
        self.list_widget.setGridSize(QSize(190, 220))
        self.list_widget.setWordWrap(True)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.setMinimumHeight(200)

        layout.addWidget(title)
        layout.addWidget(self.list_widget, 1)

        self.list_widget.currentRowChanged.connect(self.item_selected.emit)

    def clear_items(self):
        self.list_widget.clear()

    def add_thumbnail_item(self, text: str, thumb_path: str | None):
        item = QListWidgetItem(text)
        if thumb_path:
            item.setIcon(QIcon(thumb_path))
        item.setTextAlignment(Qt.AlignHCenter)
        self.list_widget.addItem(item)

    def update_thumbnail_item(self, index: int, text: str, thumb_path: str | None):
        item = self.list_widget.item(index)
        if item is None:
            return
        item.setText(text)
        if thumb_path:
            item.setIcon(QIcon(thumb_path))

    def set_current_row(self, index: int):
        self.list_widget.setCurrentRow(index)
