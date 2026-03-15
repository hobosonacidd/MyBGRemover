from typing import List, Optional
from core.models import ImageItem


class StateManager:
    def __init__(self):
        self.items: List[ImageItem] = []
        self.selected_index: Optional[int] = None

    def add_item(self, item: ImageItem):
        self.items.append(item)

    def clear_all(self):
        self.items.clear()
        self.selected_index = None

    def get_item(self, index: int) -> Optional[ImageItem]:
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def set_selected_index(self, index: Optional[int]):
        if index is None:
            self.selected_index = None
            return

        if 0 <= index < len(self.items):
            self.selected_index = index

    def get_selected_item(self) -> Optional[ImageItem]:
        if self.selected_index is None:
            return None
        return self.get_item(self.selected_index)
