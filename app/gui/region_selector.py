"""
Виджет выбора области экрана мышкой.
Открывает полупрозрачный оверлей поверх всего экрана,
пользователь рисует прямоугольник — результат возвращается через сигнал.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QFont
from PySide6.QtWidgets import QWidget, QApplication


class RegionSelector(QWidget):
    """
    Полноэкранный оверлей для выбора области.
    После выбора испускает сигнал region_selected(left, top, width, height).
    """

    region_selected = Signal(int, int, int, int)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self._start: QPoint | None = None   # глобальные координаты
        self._end: QPoint | None = None     # глобальные координаты
        self._selecting = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setMouseTracking(True)

    def showEvent(self, event):
        super().showEvent(event)

        # Геометрия всех экранов сразу
        geo = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(geo)

        self._start = None
        self._end = None
        self._selecting = False
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.globalPosition().toPoint()
            self._end = self._start
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self._selecting and self._start is not None:
            self._end = event.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            self._end = event.globalPosition().toPoint()
            self.update()
            self._emit_region()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self._start and self._end:
            rect_global = self._get_rect_global()
            rect_local = self._global_rect_to_local(rect_global)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect_local, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            pen = QPen(QColor(70, 170, 255), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect_local)

            w = rect_global.width()
            h = rect_global.height()
            label = f"{w} × {h}"

            font = QFont("Segoe UI", 11, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))

            text_x = rect_local.x() + 4
            text_y = max(20, rect_local.y() - 6)
            painter.drawText(text_x, text_y, label)

        if not self._selecting and self._start is None:
            hint = "Нарисуйте прямоугольник мышью. ESC — отмена."
            font = QFont("Segoe UI", 13)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 200))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                hint
            )

        painter.end()

    def _get_rect_global(self) -> QRect:
        if self._start is None or self._end is None:
            return QRect()
        return QRect(self._start, self._end).normalized()

    def _global_rect_to_local(self, rect: QRect) -> QRect:
        top_left = self.mapFromGlobal(rect.topLeft())
        bottom_right = self.mapFromGlobal(rect.bottomRight())
        return QRect(top_left, bottom_right).normalized()

    def _emit_region(self):
        rect = self._get_rect_global()

        if rect.width() < 10 or rect.height() < 10:
            self.cancelled.emit()
            self.close()
            return

        left = rect.left()
        top = rect.top()
        width = rect.width()
        height = rect.height()

        self.region_selected.emit(left, top, width, height)
        self.close()