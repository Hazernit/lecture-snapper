"""
Виджет предпросмотра последнего сохранённого кадра.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QSizePolicy

from PIL import Image
import numpy as np


class PreviewWidget(QWidget):
    """Показывает последний захваченный скриншот с масштабированием."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel("Предпросмотр\n(нет кадров)")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "color: #888; border: 1px solid #3a3a3a; border-radius: 6px;"
            "background: #1a1a1a;"
        )
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._label.setMinimumSize(200, 130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self._current_pil: Image.Image | None = None

    def set_image(self, pil_image: Image.Image):
        """Обновить превью новым PIL-изображением."""
        self._current_pil = pil_image
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_pil:
            self._refresh()

    def _refresh(self):
        if self._current_pil is None:
            return
        img = self._current_pil.convert("RGB")
        w = self._label.width() - 4
        h = self._label.height() - 4
        if w < 10 or h < 10:
            return
        img.thumbnail((w, h), Image.LANCZOS)
        arr = np.array(img)
        qimg = QImage(
            arr.data,
            arr.shape[1],
            arr.shape[0],
            arr.shape[1] * 3,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(qimg)
        self._label.setPixmap(pixmap)
        self._label.setText("")
