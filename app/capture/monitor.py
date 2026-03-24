"""
Фоновый поток мониторинга экрана.
Работает в отдельном QThread, шлёт сигналы в GUI.
"""
from __future__ import annotations

import time
import logging
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal

from app.capture.screen_capture import ScreenCapture
from app.detection.change_detector import ChangeDetector, DetectionResult
from app.config import AppConfig

logger = logging.getLogger(__name__)


class MonitorThread(QThread):
    """
    QThread, который периодически захватывает экран и определяет изменения.

    Сигналы:
      screenshot_saved(path, index)  — кадр сохранён
      status_update(message)         — статус для лога
      frame_preview(PIL.Image)       — последний кадр для превью
      error(message)                 — ошибка
    """

    screenshot_saved = Signal(str, int)   # путь к файлу, номер
    status_update = Signal(str)
    frame_preview = Signal(object)        # PIL.Image
    error = Signal(str)

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._running = False
        self._capture = ScreenCapture()
        self._detector = ChangeDetector(config)
        self._saved_paths: list[Path] = []
        self._save_count = 0

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def start_monitoring(self):
        """Запустить мониторинг."""
        self._running = True
        self._saved_paths.clear()
        self._save_count = 0
        self._detector.reset()
        self._ensure_output_dir()
        self.start()

    def stop_monitoring(self):
        """Остановить мониторинг (поток завершится после текущей итерации)."""
        self._running = False

    def get_saved_paths(self) -> list[Path]:
        """Список путей сохранённых скриншотов (в порядке захвата)."""
        return list(self._saved_paths)

    def remove_screenshot(self, path: Path):
        """Удалить кадр из списка (и файл с диска, если нужно)."""
        if path in self._saved_paths:
            self._saved_paths.remove(path)
            try:
                path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Не удалось удалить файл {path}: {e}")

    # ------------------------------------------------------------------
    # QThread.run
    # ------------------------------------------------------------------

    def run(self):
        self.status_update.emit("Мониторинг запущен")
        while self._running:
            start = time.time()
            try:
                self._tick()
            except Exception as e:
                logger.exception("Ошибка в потоке мониторинга")
                self.error.emit(f"Ошибка мониторинга: {e}")

            # Ждём до следующей проверки
            elapsed = time.time() - start
            sleep_time = max(0.0, self.config.check_interval - elapsed)
            # Разбиваем сон на маленькие кусочки, чтобы быстро реагировать на stop
            deadline = time.time() + sleep_time
            while time.time() < deadline and self._running:
                time.sleep(0.1)

        self.status_update.emit("Мониторинг остановлен")

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _tick(self):
        """Одна итерация: захват + детекция + (опционально) сохранение."""
        frame_arr = self._capture.capture_as_array(self.config.region)
        self.frame_preview.emit(Image.fromarray(frame_arr))
        result: DetectionResult = self._detector.process_frame(frame_arr)

        self.status_update.emit(
            f"[{time.strftime('%H:%M:%S')}] {result.reason} "
            f"(diff={result.pixel_diff:.2%}, ssim={result.ssim_score:.3f})"
        )

        if result.should_save:
            path = self._save_frame(frame_arr)
            if path:
                self._saved_paths.append(path)
                self._save_count += 1
                self._detector.notify_saved(frame_arr)
                self.screenshot_saved.emit(str(path), self._save_count)
                self.status_update.emit(
                    f"✅ Сохранён кадр #{self._save_count}: {path.name}"
                )
                # Отправить превью
                pil = Image.fromarray(frame_arr)
                self.frame_preview.emit(pil)

    def _save_frame(self, frame_arr: np.ndarray) -> Path | None:
        """Сохранить кадр на диск. Возвращает путь или None при ошибке."""
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"slide_{self._save_count + 1:04d}_{ts}.png"
            out_dir = Path(self.config.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / filename
            img = Image.fromarray(frame_arr)
            img.save(str(path), "PNG")
            return path
        except Exception as e:
            logger.exception("Ошибка сохранения кадра")
            self.error.emit(f"Не удалось сохранить кадр: {e}")
            return None

    def _ensure_output_dir(self):
        try:
            Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.error.emit(f"Не удалось создать папку: {e}")
