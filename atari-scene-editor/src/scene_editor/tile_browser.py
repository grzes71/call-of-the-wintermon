"""Tile browser widget for listing and selecting graphics from the tiles/ directory."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .asset_manager import AssetManager


class TileBrowserWidget(QWidget):
    """Widget displaying tileset images from the tiles/ directory with thumbnails."""

    image_selected = Signal(str)  # Emits relative or path string

    def __init__(self, asset_manager: AssetManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.asset_manager = asset_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header toolbar
        header_layout = QHBoxLayout()
        header_label = QLabel("<b>Tileset Library (tiles/)</b>")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Reload graphics from tiles/ directory")
        self.refresh_btn.clicked.connect(self.reload_tiles)
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        header_layout.addWidget(self.refresh_btn)
        layout.addLayout(header_layout)

        # Status / message label if empty
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #aaa; font-style: italic; padding: 4px;")
        layout.addWidget(self.status_label)

        # Tile list widget
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(48, 48))
        self.list_widget.setSpacing(4)
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget)

        self.reload_tiles()

    def reload_tiles(self) -> None:
        """Scan tiles/ directory and repopulate the list with thumbnails."""
        self.list_widget.clear()
        tiles = self.asset_manager.scan_tiles()

        if not tiles:
            self.status_label.setText(
                "No graphic files found in 'tiles/' directory.\n"
                "Place PNG, BMP, GIF, or JPEG files in the 'tiles/' folder."
            )
            self.status_label.show()
            return

        self.status_label.hide()
        for tile_path in tiles:
            rel_str = self.asset_manager.to_relative_path(tile_path)
            thumb = self.asset_manager.get_thumbnail(tile_path, QSize(48, 48))
            icon = QIcon(thumb) if thumb else QIcon()

            item = QListWidgetItem(icon, tile_path.name)
            item.setData(Qt.ItemDataRole.UserRole, rel_str)
            item.setToolTip(f"File: {rel_str}")
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def select_file(self, source_path: str) -> None:
        """Highlight and select a specific file in the browser."""
        norm_target = source_path.replace("\\", "/").lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            rel = str(item.data(Qt.ItemDataRole.UserRole)).replace("\\", "/").lower()
            if rel == norm_target or rel.endswith(norm_target) or norm_target.endswith(rel):
                self.list_widget.setCurrentRow(i)
                self.image_selected.emit(str(item.data(Qt.ItemDataRole.UserRole)))
                break

    def get_selected_path(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if current:
            rel_path = current.data(Qt.ItemDataRole.UserRole)
            self.image_selected.emit(rel_path)
