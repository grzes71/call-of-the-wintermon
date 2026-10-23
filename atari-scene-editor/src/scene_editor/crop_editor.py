"""Crop editor widget for inspecting tileset images and defining rectangular tile crops."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .asset_manager import AssetManager
from .scene_model import Rect, SOURCE_X_ALIGN, align_crop_width, align_source_x


class CropSelectionItem(QGraphicsRectItem):
    """Interactive rectangle with resize handles for selecting a sub-region."""

    HANDLE_SIZE = 6.0

    def __init__(
        self,
        max_bounds: QRectF,
        on_rect_changed: Optional[callable] = None,
    ) -> None:
        super().__init__()
        self.max_bounds = max_bounds
        self.on_rect_changed = on_rect_changed

        self.setPen(QPen(QColor(0, 255, 200), 1.5, Qt.PenStyle.SolidLine))
        self.setBrush(QBrush(QColor(0, 255, 200, 40)))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)

        self._active_handle: Optional[str] = None  # None, "move", "tl", "tr", "bl", "br", "l", "r", "t", "b"
        self._press_rect: Optional[QRectF] = None
        self._press_pos: Optional[QPointF] = None

    def set_max_bounds(self, bounds: QRectF) -> None:
        self.max_bounds = bounds
        self.set_crop_rect(self.rect())

    def set_crop_rect(self, rect: QRectF) -> None:
        """Set crop rect clamped to source image bounds."""
        clamped = self._clamp_rect(rect)
        self.setRect(clamped)
        self.update()
        if self.on_rect_changed:
            self.on_rect_changed(self.to_rect())

    def to_rect(self) -> Rect:
        r = self.rect()
        return Rect(
            x=align_source_x(r.x()),
            y=max(0, int(round(r.y()))),
            width=align_crop_width(r.width()),
            height=max(1, int(round(r.height()))),
        )

    def _clamp_rect(self, r: QRectF) -> QRectF:
        # The crop sits on the 4-pixel byte grid: x rounds down, width rounds up
        x = max(self.max_bounds.left(), min(float(align_source_x(r.x())), self.max_bounds.right() - 1))
        y = max(self.max_bounds.top(), min(r.y(), self.max_bounds.bottom() - 1))
        w = min(float(align_crop_width(r.width())), self.max_bounds.right() - x)
        h = max(1.0, min(r.height(), self.max_bounds.bottom() - y))
        return QRectF(round(x), round(y), round(w), round(h))

    def _get_handle_at(self, pos: QPointF) -> str:
        r = self.rect()
        hs = self.HANDLE_SIZE
        # Check corners
        if QRectF(r.left() - hs, r.top() - hs, 2 * hs, 2 * hs).contains(pos):
            return "tl"
        if QRectF(r.right() - hs, r.top() - hs, 2 * hs, 2 * hs).contains(pos):
            return "tr"
        if QRectF(r.left() - hs, r.bottom() - hs, 2 * hs, 2 * hs).contains(pos):
            return "bl"
        if QRectF(r.right() - hs, r.bottom() - hs, 2 * hs, 2 * hs).contains(pos):
            return "br"
        # Check edges
        if abs(pos.x() - r.left()) <= hs and r.top() <= pos.y() <= r.bottom():
            return "l"
        if abs(pos.x() - r.right()) <= hs and r.top() <= pos.y() <= r.bottom():
            return "r"
        if abs(pos.y() - r.top()) <= hs and r.left() <= pos.x() <= r.right():
            return "t"
        if abs(pos.y() - r.bottom()) <= hs and r.left() <= pos.x() <= r.right():
            return "b"
        if r.contains(pos):
            return "move"
        return "none"

    def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        handle = self._get_handle_at(event.pos())
        if handle in ("tl", "br"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in ("tr", "bl"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle in ("l", "r"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif handle in ("t", "b"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle == "move":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._active_handle = self._get_handle_at(event.pos())
            self._press_pos = event.pos()
            self._press_rect = self.rect()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._active_handle and self._press_pos and self._press_rect:
            dx = event.pos().x() - self._press_pos.x()
            dy = event.pos().y() - self._press_pos.y()
            pr = self._press_rect
            handle = self._active_handle

            new_x = pr.x()
            new_y = pr.y()
            new_w = pr.width()
            new_h = pr.height()

            if handle == "move":
                new_x += dx
                new_y += dy
            elif handle == "tl":
                new_x += dx
                new_y += dy
                new_w -= dx
                new_h -= dy
            elif handle == "tr":
                new_y += dy
                new_w += dx
                new_h -= dy
            elif handle == "bl":
                new_x += dx
                new_w -= dx
                new_h += dy
            elif handle == "br":
                new_w += dx
                new_h += dy
            elif handle == "l":
                new_x += dx
                new_w -= dx
            elif handle == "r":
                new_w += dx
            elif handle == "t":
                new_y += dy
                new_h -= dy
            elif handle == "b":
                new_h += dy

            # Avoid inverted rects during drag
            if new_w < 1:
                new_w = 1
            if new_h < 1:
                new_h = 1

            self.set_crop_rect(QRectF(new_x, new_y, new_w, new_h))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._active_handle = None
        self._press_pos = None
        self._press_rect = None
        super().mouseReleaseEvent(event)

    def paint(self, painter: QPainter, option: any, widget: any = None) -> None:
        super().paint(painter, option, widget)
        # Draw small corner handles
        r = self.rect()
        hs = 4.0
        handle_brush = QBrush(QColor(255, 255, 255))
        painter.setPen(QPen(QColor(0, 160, 120), 1))
        painter.setBrush(handle_brush)

        for pt in (
            (r.left() - hs / 2, r.top() - hs / 2),
            (r.right() - hs / 2, r.top() - hs / 2),
            (r.left() - hs / 2, r.bottom() - hs / 2),
            (r.right() - hs / 2, r.bottom() - hs / 2),
        ):
            painter.drawRect(QRectF(pt[0], pt[1], hs, hs))


class CropCanvasView(QGraphicsView):
    """View displaying the source tileset image with drag-to-select support."""

    crop_changed = Signal(Rect)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.canvas_scene = QGraphicsScene(self)
        self.setScene(self.canvas_scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setBackgroundBrush(QBrush(QColor(28, 28, 32)))

        self.pixmap_item: Optional[QGraphicsPixmapItem] = None
        self.selection_item: Optional[CropSelectionItem] = None
        self._drag_start: Optional[QPointF] = None

        self.zoom_factor = 3.0
        self.scale(self.zoom_factor, self.zoom_factor)

    def set_image(self, pixmap: Optional[QPixmap]) -> None:
        self.canvas_scene.clear()
        self.pixmap_item = None
        self.selection_item = None

        if pixmap is None or pixmap.isNull():
            return

        self.pixmap_item = self.canvas_scene.addPixmap(pixmap)
        self.canvas_scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())

        bounds = QRectF(0, 0, pixmap.width(), pixmap.height())
        initial_w = min(16, pixmap.width())
        initial_h = min(16, pixmap.height())
        initial_rect = QRectF(0, 0, initial_w, initial_h)

        self.selection_item = CropSelectionItem(
            max_bounds=bounds,
            on_rect_changed=self._on_item_rect_changed,
        )
        self.canvas_scene.addItem(self.selection_item)
        self.selection_item.set_crop_rect(initial_rect)

    def _on_item_rect_changed(self, rect: Rect) -> None:
        self.crop_changed.emit(rect)

    def set_rect_from_spinboxes(self, rect: Rect) -> None:
        if self.selection_item:
            self.selection_item.set_crop_rect(
                QRectF(rect.x, rect.y, rect.width, rect.height)
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.pixmap_item:
            sp = self.mapToScene(event.pos())
            # If click was outside selection item, start creating a new selection rect
            if self.selection_item and not self.selection_item.contains(
                self.selection_item.mapFromScene(sp)
            ):
                self._drag_start = sp
                self.selection_item.set_crop_rect(QRectF(sp.x(), sp.y(), 1, 1))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start and self.selection_item and self.pixmap_item:
            sp = self.mapToScene(event.pos())
            x1, x2 = min(self._drag_start.x(), sp.x()), max(self._drag_start.x(), sp.x())
            y1, y2 = min(self._drag_start.y(), sp.y()), max(self._drag_start.y(), sp.y())
            w = max(1.0, x2 - x1)
            h = max(1.0, y2 - y1)
            self.selection_item.set_crop_rect(QRectF(x1, y1, w, h))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_start:
            self._drag_start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 1.15 if event.angleDelta().y() > 0 else 0.85
            self.scale(delta, delta)
            event.accept()
        else:
            super().wheelEvent(event)


class CropEditorWidget(QWidget):
    """Full crop editor panel combining the interactive preview, spinboxes, and Add button."""

    add_to_scene_requested = Signal(str, Rect)  # source_path, crop_rect

    def __init__(self, asset_manager: AssetManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.asset_manager = asset_manager
        self.current_source: Optional[str] = None
        self._current_crop = Rect(x=0, y=0, width=16, height=16)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header info
        self.file_label = QLabel("<b>Select a graphic from tiles/</b>")
        self.file_label.setStyleSheet("color: #ccc; font-size: 11px;")
        layout.addWidget(self.file_label)

        # Canvas view
        self.canvas_view = CropCanvasView(self)
        self.canvas_view.crop_changed.connect(self._on_crop_from_view)
        layout.addWidget(self.canvas_view, stretch=1)

        # Controls Group
        controls_group = QGroupBox("Crop Rectangle (Source Pixels)")
        cg_layout = QVBoxLayout(controls_group)
        cg_layout.setContentsMargins(6, 6, 6, 6)

        grid_layout = QHBoxLayout()

        # Spinboxes: X, Y, Width, Height
        self.spin_x = self._make_spinbox("X:", grid_layout)
        self.spin_x.setSingleStep(SOURCE_X_ALIGN)
        self.spin_x.setToolTip(
            f"Crop X snaps to multiples of {SOURCE_X_ALIGN}: ANTIC Mode E packs "
            f"{SOURCE_X_ALIGN} pixels per byte and the game reads tileset bitmaps at "
            f"byte boundaries."
        )
        self.spin_y = self._make_spinbox("Y:", grid_layout)
        self.spin_w = self._make_spinbox("W:", grid_layout, min_val=1)
        self.spin_w.setSingleStep(SOURCE_X_ALIGN)
        self.spin_w.setToolTip(
            f"Crop W snaps up to multiples of {SOURCE_X_ALIGN}: the game reads tileset "
            f"bitmaps byte by byte, so e.g. a 77 px crop is drawn 80 px wide."
        )
        self.spin_h = self._make_spinbox("H:", grid_layout, min_val=1)

        cg_layout.addLayout(grid_layout)

        # Validation status label
        self.val_label = QLabel()
        self.val_label.setStyleSheet("color: #4cd964; font-size: 11px;")
        cg_layout.addWidget(self.val_label)

        # Add to Scene Button
        self.add_btn = QPushButton("Add to Scene")
        self.add_btn.setStyleSheet(
            "QPushButton { background-color: #0e70a0; color: white; font-weight: bold; "
            "padding: 6px; border-radius: 4px; } QPushButton:hover { background-color: #1288c4; }"
        )
        self.add_btn.clicked.connect(self._on_add_clicked)
        cg_layout.addWidget(self.add_btn)

        layout.addWidget(controls_group)

    def _make_spinbox(self, label_text: str, layout: QHBoxLayout, min_val: int = 0) -> QSpinBox:
        lbl = QLabel(label_text)
        spin = QSpinBox()
        spin.setRange(min_val, 9999)
        spin.setValue(0)
        spin.valueChanged.connect(self._on_spinbox_changed)
        layout.addWidget(lbl)
        layout.addWidget(spin)
        return spin

    def load_image(self, source_path: str) -> None:
        """Load graphic and reset crop view."""
        self.current_source = source_path
        pm = self.asset_manager.get_pixmap(source_path)

        if pm is None or pm.isNull():
            self.file_label.setText(f"<font color='red'>Failed to load: {source_path}</font>")
            self.canvas_view.set_image(None)
            self.add_btn.setEnabled(False)
            self.val_label.setText("Image not loaded.")
            return

        self.file_label.setText(
            f"<b>{Path(source_path).name}</b> ({pm.width()} × {pm.height()} px)"
        )
        self.canvas_view.set_image(pm)

        # Set spinbox limits based on image dimensions
        self.spin_x.setMaximum(max(0, pm.width() - 1))
        self.spin_y.setMaximum(max(0, pm.height() - 1))
        self.spin_w.setMaximum(pm.width())
        self.spin_h.setMaximum(pm.height())

        # Reset selection to an initial 16x16 byte-aligned crop (or the image size)
        init_w = max(SOURCE_X_ALIGN, min(16, pm.width()) // SOURCE_X_ALIGN * SOURCE_X_ALIGN)
        init_h = min(16, pm.height())
        self._current_crop = Rect(x=0, y=0, width=init_w, height=init_h)
        self._sync_spinboxes_from_crop(self._current_crop)
        self.add_btn.setEnabled(True)
        self._validate_current_crop()

    def _sync_spinboxes_from_crop(self, r: Rect) -> None:
        for spin in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
            spin.blockSignals(True)
        self.spin_x.setValue(r.x)
        self.spin_y.setValue(r.y)
        self.spin_w.setValue(r.width)
        self.spin_h.setValue(r.height)
        for spin in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
            spin.blockSignals(False)

    def _on_crop_from_view(self, rect: Rect) -> None:
        self._current_crop = rect
        self._sync_spinboxes_from_crop(rect)
        self._validate_current_crop()

    def _on_spinbox_changed(self) -> None:
        # Keep the crop on the byte grid so the game shows exactly what is previewed
        aligned_x = align_source_x(self.spin_x.value())
        aligned_w = align_crop_width(self.spin_w.value())
        for spin, value in ((self.spin_x, aligned_x), (self.spin_w, aligned_w)):
            if spin.value() != value:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)

        r = Rect(
            x=aligned_x,
            y=self.spin_y.value(),
            width=aligned_w,
            height=self.spin_h.value(),
        )
        self._current_crop = r
        self.canvas_view.set_rect_from_spinboxes(r)
        self._validate_current_crop()

    def _validate_current_crop(self) -> None:
        if not self.current_source:
            self.add_btn.setEnabled(False)
            self.val_label.setText("No image selected.")
            return

        is_valid, msg = self.asset_manager.validate_crop(
            self.current_source, self._current_crop
        )
        self.add_btn.setEnabled(is_valid)
        if is_valid:
            self.val_label.setStyleSheet("color: #4cd964; font-size: 11px;")
            self.val_label.setText(
                f"Valid crop: {self._current_crop.width} × {self._current_crop.height} px"
            )
        else:
            self.val_label.setStyleSheet("color: #ff5555; font-size: 11px;")
            self.val_label.setText(msg)

    def _on_add_clicked(self) -> None:
        if self.current_source and self.add_btn.isEnabled():
            self.add_to_scene_requested.emit(self.current_source, self._current_crop)
