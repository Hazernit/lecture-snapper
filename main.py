"""
Lecture Snapper — точка входа.
Запуск: python main.py
"""
import sys
import logging

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.gui.main_window import MainWindow

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

def main():
    # Включить масштабирование DPI на Windows
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Lecture Snapper")
    app.setApplicationVersion("1.0.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
