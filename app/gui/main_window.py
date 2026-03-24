"""
Главное окно приложения Lecture Snapper.
Содержит:
  - Панель настроек
  - Кнопки управления (Старт / Стоп)
  - Лог событий
  - Превью последнего кадра
  - Кнопки "Экспорт PDF" и "Открыть папку"
"""
from __future__ import annotations

import os
import subprocess
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Slot
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QIcon, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QTextEdit, QFileDialog, QMessageBox, QGroupBox,
    QScrollArea, QFrame, QSizePolicy, QStatusBar,
)

from app.config import AppConfig
from app.capture.monitor import MonitorThread
from app.export.pdf_exporter import build_pdf
from app.gui.region_selector import RegionSelector
from app.gui.preview_widget import PreviewWidget

logger = logging.getLogger(__name__)

# Тёмная тема
STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 8px;
    padding-top: 12px;
    font-weight: bold;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton#btn_start {
    background-color: #a6e3a1;
    color: #1e1e2e;
    font-weight: bold;
    border: none;
}
QPushButton#btn_start:hover { background-color: #94e2d5; }
QPushButton#btn_stop {
    background-color: #f38ba8;
    color: #1e1e2e;
    font-weight: bold;
    border: none;
}
QPushButton#btn_stop:hover { background-color: #eba0ac; }
QPushButton#btn_pdf {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
    border: none;
}
QPushButton#btn_pdf:hover { background-color: #b4befe; }
QPushButton:disabled {
    background-color: #2a2a3a;
    color: #585b70;
    border-color: #313244;
}
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    color: #cdd6f4;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #89b4fa;
}
QTextEdit {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #a6adc8;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #45475a;
    background: #313244;
}
QCheckBox::indicator:checked {
    background: #89b4fa;
    border-color: #89b4fa;
}
QScrollBar:vertical {
    background: #1e1e2e;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 4px;
}
QLabel#lbl_count {
    font-size: 28px;
    font-weight: bold;
    color: #a6e3a1;
}
QLabel#lbl_region_info {
    color: #89dceb;
    font-size: 11px;
}
QStatusBar {
    background: #181825;
    color: #6c7086;
    border-top: 1px solid #313244;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AppConfig()
        self._monitor: MonitorThread | None = None
        self._is_running = False
        self._region_selector: RegionSelector | None = None

        self.setWindowTitle("Lecture Snapper")
        self.setMinimumSize(900, 680)
        self.setStyleSheet(STYLESHEET)

        self._build_ui()
        self._connect_shortcuts()
        self._update_region_label()

    # ------------------------------------------------------------------
    # Построение UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(12)
        root.setContentsMargins(14, 14, 14, 14)

        # Левая колонка: настройки + кнопки управления
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(self._build_settings_group())
        left.addWidget(self._build_control_group())
        left.addWidget(self._build_actions_group())
        left.addStretch()
        root.addLayout(left, stretch=2)

        # Правая колонка: счётчик + превью + лог
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self._build_counter_group())
        right.addWidget(self._build_preview_group(), stretch=2)
        right.addWidget(self._build_log_group(), stretch=3)
        root.addLayout(right, stretch=3)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Готов к работе")

    def _build_settings_group(self) -> QGroupBox:
        grp = QGroupBox("Настройки")
        grid = QGridLayout(grp)
        grid.setSpacing(8)
        grid.setColumnMinimumWidth(1, 90)

        row = 0

        # --- Область ---
        grid.addWidget(QLabel("Область:"), row, 0)
        self.lbl_region = QLabel()
        self.lbl_region.setObjectName("lbl_region_info")
        grid.addWidget(self.lbl_region, row, 1)
        btn_sel = QPushButton("Выбрать…")
        btn_sel.setFixedWidth(90)
        btn_sel.clicked.connect(self._on_select_region)
        grid.addWidget(btn_sel, row, 2)
        row += 1

        # --- Порог изменения ---
        grid.addWidget(QLabel("Порог (%):"), row, 0)
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(1.0, 80.0)
        self.spin_threshold.setSingleStep(1.0)
        self.spin_threshold.setValue(self.config.change_threshold * 100)
        self.spin_threshold.setToolTip("Минимальный процент изменённых пикселей для захвата")
        grid.addWidget(self.spin_threshold, row, 1, 1, 2)
        row += 1

        # --- Интервал проверки ---
        grid.addWidget(QLabel("Интервал (с):"), row, 0)
        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setRange(0.5, 30.0)
        self.spin_interval.setSingleStep(0.5)
        self.spin_interval.setValue(self.config.check_interval)
        self.spin_interval.setToolTip("Как часто проверять экран")
        grid.addWidget(self.spin_interval, row, 1, 1, 2)
        row += 1

        # --- Минимальная пауза ---
        grid.addWidget(QLabel("Мин. пауза (с):"), row, 0)
        self.spin_pause = QDoubleSpinBox()
        self.spin_pause.setRange(1.0, 120.0)
        self.spin_pause.setSingleStep(1.0)
        self.spin_pause.setValue(self.config.min_pause)
        self.spin_pause.setToolTip("Минимальная пауза между сохранениями")
        grid.addWidget(self.spin_pause, row, 1, 1, 2)
        row += 1

        # --- Устойчивость ---
        grid.addWidget(QLabel("Устойчивость (с):"), row, 0)
        self.spin_stable = QDoubleSpinBox()
        self.spin_stable.setRange(0.5, 10.0)
        self.spin_stable.setSingleStep(0.5)
        self.spin_stable.setValue(self.config.stability_duration)
        self.spin_stable.setToolTip("Изменение должно держаться столько секунд")
        grid.addWidget(self.spin_stable, row, 1, 1, 2)
        row += 1

        # --- Папка ---
        grid.addWidget(QLabel("Папка:"), row, 0)
        self.edit_dir = QLineEdit(str(self.config.output_dir))
        grid.addWidget(self.edit_dir, row, 1)
        btn_dir = QPushButton("…")
        btn_dir.setFixedWidth(30)
        btn_dir.clicked.connect(self._on_choose_dir)
        grid.addWidget(btn_dir, row, 2)
        row += 1

        # --- Имя PDF ---
        grid.addWidget(QLabel("Имя PDF:"), row, 0)
        self.edit_pdf_name = QLineEdit(self.config.pdf_name)
        grid.addWidget(self.edit_pdf_name, row, 1, 1, 2)
        row += 1

        # --- Флажки ---
        self.chk_save_png = QCheckBox("Сохранять PNG отдельно")
        self.chk_save_png.setChecked(self.config.save_png)
        grid.addWidget(self.chk_save_png, row, 0, 1, 3)
        row += 1

        self.chk_timestamp = QCheckBox("Добавлять время в PDF")
        self.chk_timestamp.setChecked(self.config.add_timestamp)
        grid.addWidget(self.chk_timestamp, row, 0, 1, 3)

        return grp

    def _build_control_group(self) -> QGroupBox:
        grp = QGroupBox("Управление")
        layout = QHBoxLayout(grp)

        self.btn_start = QPushButton("▶  Старт  [F5]")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self._on_start)

        self.btn_stop = QPushButton("■  Стоп  [F6]")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)

        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_stop)
        return grp

    def _build_actions_group(self) -> QGroupBox:
        grp = QGroupBox("Действия")
        layout = QVBoxLayout(grp)
        layout.setSpacing(6)

        self.btn_pdf = QPushButton("📄  Экспорт в PDF")
        self.btn_pdf.setObjectName("btn_pdf")
        self.btn_pdf.clicked.connect(self._on_export_pdf)

        btn_folder = QPushButton("📂  Открыть папку")
        btn_folder.clicked.connect(self._on_open_folder)

        self.btn_clear = QPushButton("🗑  Очистить список кадров")
        self.btn_clear.clicked.connect(self._on_clear_frames)

        layout.addWidget(self.btn_pdf)
        layout.addWidget(btn_folder)
        layout.addWidget(self.btn_clear)
        return grp

    def _build_counter_group(self) -> QGroupBox:
        grp = QGroupBox("Сохранено кадров")
        layout = QHBoxLayout(grp)
        self.lbl_count = QLabel("0")
        self.lbl_count.setObjectName("lbl_count")
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_count)
        return grp

    def _build_preview_group(self) -> QGroupBox:
        grp = QGroupBox("Последний кадр")
        layout = QVBoxLayout(grp)
        self.preview = PreviewWidget()
        layout.addWidget(self.preview)
        return grp

    def _build_log_group(self) -> QGroupBox:
        grp = QGroupBox("Лог событий")
        layout = QVBoxLayout(grp)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        btn_clear_log = QPushButton("Очистить лог")
        btn_clear_log.setFixedHeight(24)
        btn_clear_log.clicked.connect(self.log_view.clear)
        layout.addWidget(btn_clear_log)
        return grp

    def _connect_shortcuts(self):
        QShortcut(QKeySequence("F5"), self, self._on_start)
        QShortcut(QKeySequence("F6"), self, self._on_stop)

    # ------------------------------------------------------------------
    # Обработчики кнопок
    # ------------------------------------------------------------------

    @Slot()
    def _on_select_region(self):
        """Открыть оверлей выбора области."""
        if self._is_running:
            return
        self._region_selector = RegionSelector()
        self._region_selector.region_selected.connect(self._on_region_set)
        self._region_selector.cancelled.connect(lambda: self._log("Выбор области отменён"))
        self.hide()
        self._region_selector.show()

    @Slot(int, int, int, int)
    def _on_region_set(self, left, top, width, height):
        self.config.region = {"left": left, "top": top, "width": width, "height": height}
        self._update_region_label()
        self._log(f"Выбрана область: {left},{top}  {width}×{height}")
        self.show()

    @Slot()
    def _on_start(self):
        if self._is_running:
            return
        self._apply_settings()
        self._start_monitor()

    @Slot()
    def _on_stop(self):
        if not self._is_running:
            return
        if self._monitor:
            self._monitor.stop_monitoring()
        self._set_running(False)

    @Slot()
    def _on_export_pdf(self):
        if not self._monitor or not self._monitor.get_saved_paths():
            QMessageBox.warning(self, "Нет кадров", "Нет сохранённых кадров для экспорта.")
            return

        out_dir = Path(self.config.output_dir)
        pdf_name = self.edit_pdf_name.text().strip() or "lecture.pdf"
        if not pdf_name.lower().endswith(".pdf"):
            pdf_name += ".pdf"
        out_path = out_dir / pdf_name

        paths = self._monitor.get_saved_paths()
        self._log(f"Сборка PDF: {len(paths)} кадров → {out_path}")
        try:
            final = build_pdf(
                paths,
                out_path,
                add_timestamp=self.chk_timestamp.isChecked(),
                page_numbers=True,
            )
            self._log(f"✅ PDF готов: {final}")
            QMessageBox.information(
                self, "Готово",
                f"PDF сохранён:\n{final}\n\n({len(paths)} страниц)"
            )
        except PermissionError as e:
            QMessageBox.critical(self, "Ошибка доступа", str(e))
        except Exception as e:
            logger.exception("Ошибка экспорта PDF")
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать PDF:\n{e}")

    @Slot()
    def _on_open_folder(self):
        out_dir = Path(self.config.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(out_dir))  # Windows
        except AttributeError:
            subprocess.Popen(["xdg-open", str(out_dir)])  # Linux/Mac

    @Slot()
    def _on_choose_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Выберите папку сохранения", str(self.config.output_dir)
        )
        if d:
            self.edit_dir.setText(d)

    @Slot()
    def _on_clear_frames(self):
        if not self._monitor:
            return
        reply = QMessageBox.question(
            self, "Очистить список",
            "Удалить все сохранённые кадры из списка?\n(файлы на диске останутся)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._monitor._saved_paths.clear()
            self._monitor._save_count = 0
            self.lbl_count.setText("0")
            self._log("Список кадров очищен")

    # ------------------------------------------------------------------
    # Слоты монитора
    # ------------------------------------------------------------------

    @Slot(str, int)
    def _on_screenshot_saved(self, path: str, index: int):
        self.lbl_count.setText(str(index))
        self.statusBar().showMessage(f"Сохранён кадр #{index}: {Path(path).name}")

    @Slot(str)
    def _on_status_update(self, msg: str):
        self._log(msg)

    @Slot(object)
    def _on_frame_preview(self, pil_image):
        self.preview.set_image(pil_image)

    @Slot(str)
    def _on_error(self, msg: str):
        self._log(f"⚠️ {msg}")
        self.statusBar().showMessage(f"Ошибка: {msg}")

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _apply_settings(self):
        """Считать значения из виджетов в config."""
        self.config.change_threshold = self.spin_threshold.value() / 100.0
        self.config.check_interval = self.spin_interval.value()
        self.config.min_pause = self.spin_pause.value()
        self.config.stability_duration = self.spin_stable.value()
        self.config.output_dir = Path(self.edit_dir.text().strip() or str(self.config.output_dir))
        self.config.pdf_name = self.edit_pdf_name.text().strip() or "lecture.pdf"
        self.config.save_png = self.chk_save_png.isChecked()
        self.config.add_timestamp = self.chk_timestamp.isChecked()

    def _start_monitor(self):
        self._monitor = MonitorThread(self.config)
        self._monitor.screenshot_saved.connect(self._on_screenshot_saved)
        self._monitor.status_update.connect(self._on_status_update)
        self._monitor.frame_preview.connect(self._on_frame_preview)
        self._monitor.error.connect(self._on_error)
        self._monitor.start_monitoring()
        self._set_running(True)

    def _set_running(self, running: bool):
        self._is_running = running
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.statusBar().showMessage("Мониторинг запущен…" if running else "Остановлен")

    def _update_region_label(self):
        r = self.config.region
        self.lbl_region.setText(
            f"{r['left']}, {r['top']}  —  {r['width']}×{r['height']}"
        )

    def _log(self, message: str):
        self.log_view.append(message)
        # Автопрокрутка вниз
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, event):
        if self._monitor and self._is_running:
            self._monitor.stop_monitoring()
            self._monitor.wait(3000)
        event.accept()
