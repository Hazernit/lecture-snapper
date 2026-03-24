"""
Алгоритм детекции значимых изменений на экране.

Многоуровневый фильтр:
  1. Быстрый пре-скрининг по mean diff (отсев мерцания/курсора)
  2. Попиксельная разница (доля изменённых пикселей)
  3. SSIM — структурное сходство
  4. Устойчивость изменения во времени
  5. Антидубликат — сравнение с последним сохранённым кадром
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

try:
    from skimage.metrics import structural_similarity as ssim
    _HAS_SKIMAGE = True
except ImportError:
    _HAS_SKIMAGE = False
    logging.warning("scikit-image не установлен, SSIM недоступен — используется упрощённая детекция")

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    should_save: bool
    reason: str
    pixel_diff: float = 0.0   # Доля изменённых пикселей
    ssim_score: float = 1.0   # SSIM (1.0 = идентично)
    mean_diff: float = 0.0    # Средняя разница пикселей


class ChangeDetector:
    """
    Определяет, произошло ли значимое изменение на экране.
    Хранит состояние между кадрами.
    """

    def __init__(self, config):
        self.config = config

        # Последний «базовый» кадр (с которым сравниваем)
        self._reference_frame: np.ndarray | None = None
        # Последний сохранённый кадр (для проверки дубликатов)
        self._last_saved_frame: np.ndarray | None = None

        # Момент, когда впервые зафиксировали текущее изменение
        self._change_start_time: float | None = None
        # Момент последнего сохранения
        self._last_save_time: float = 0.0

        # Флаг: идёт ли сейчас «подозрительный» период изменения
        self._change_pending: bool = False

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def reset(self):
        """Сбросить состояние (при старте новой сессии)."""
        self._reference_frame = None
        self._last_saved_frame = None
        self._change_start_time = None
        self._last_save_time = 0.0
        self._change_pending = False

    def process_frame(self, frame: np.ndarray) -> DetectionResult:
        small = self._preprocess(frame)

        if self._reference_frame is None:
            self._reference_frame = small
            return DetectionResult(False, "Инициализация эталонного кадра")

        mean_diff = self._mean_diff(small, self._reference_frame)
        pixel_diff = self._pixel_diff(small, self._reference_frame)
        ssim_score = self._compute_ssim(small, self._reference_frame)

        result = DetectionResult(
            should_save=False,
            reason="",
            pixel_diff=pixel_diff,
            ssim_score=ssim_score,
            mean_diff=mean_diff,
        )
        # Быстрое сохранение для резких изменений (например, скролл)
        fast_save = (
            pixel_diff >= self.config.change_threshold * 2.0
            or ssim_score < (self.config.ssim_threshold - 0.08)
            or mean_diff >= max(0.03, self.config.noise_threshold * 4)
        )

        # Очень маленькие колебания — это шум
        if mean_diff < max(0.0015, self.config.noise_threshold * 0.3):
            self._change_pending = False
            self._change_start_time = None
            result.reason = f"Шум/мерцание (mean_diff={mean_diff:.3f})"
            return result

        # Значимость считаем мягче:
        # либо заметная доля пикселей изменилась,
        # либо картинка структурно уже ощутимо отличается
        significant = (
                pixel_diff >= self.config.change_threshold
                or ssim_score < self.config.ssim_threshold
                or mean_diff >= max(0.01, self.config.noise_threshold * 2)
        )

        if not significant:
            result.reason = (
                f"Изменение незначительное (pixel_diff={pixel_diff:.2%}, "
                f"ssim={ssim_score:.3f}, mean_diff={mean_diff:.3f})"
            )
            return result

        now = time.time()

        # Если изменение очень сильное — сохраняем сразу, без ожидания устойчивости
        if fast_save:
            since_last_save = now - self._last_save_time
            if since_last_save >= max(0.8, self.config.min_pause * 0.25):
                if self._last_saved_frame is not None:
                    dup_ssim = self._compute_ssim(small, self._last_saved_frame)
                    if dup_ssim <= self.config.duplicate_ssim:
                        result.should_save = True
                        result.reason = (
                            f"Быстрое сохранение: pixel_diff={pixel_diff:.2%}, "
                            f"ssim={ssim_score:.3f}, mean_diff={mean_diff:.3f}"
                        )
                        self._reference_frame = small
                        self._last_saved_frame = small
                        self._last_save_time = now
                        self._change_pending = False
                        self._change_start_time = None
                        return result
                else:
                    result.should_save = True
                    result.reason = (
                        f"Быстрое сохранение: pixel_diff={pixel_diff:.2%}, "
                        f"ssim={ssim_score:.3f}, mean_diff={mean_diff:.3f}"
                    )
                    self._reference_frame = small
                    self._last_saved_frame = small
                    self._last_save_time = now
                    self._change_pending = False
                    self._change_start_time = None
                    return result

        if not self._change_pending:
            self._change_pending = True
            self._change_start_time = now
            result.reason = "Обнаружено изменение, ожидаю устойчивости..."
            return result

        elapsed_stable = now - self._change_start_time
        if elapsed_stable < self.config.stability_duration:
            result.reason = (
                f"Ожидание устойчивости: {elapsed_stable:.1f}s / "
                f"{self.config.stability_duration}s"
            )
            return result

        since_last_save = now - self._last_save_time
        if since_last_save < self.config.min_pause:
            result.reason = (
                f"Слишком рано после последнего сохранения "
                f"({since_last_save:.1f}s < {self.config.min_pause}s)"
            )
            return result

        if self._last_saved_frame is not None:
            dup_ssim = self._compute_ssim(small, self._last_saved_frame)
            if dup_ssim > self.config.duplicate_ssim:
                self._reference_frame = small
                self._change_pending = False
                self._change_start_time = None
                result.reason = f"Дубликат предыдущего сохранения (ssim={dup_ssim:.3f})"
                return result

        result.should_save = True
        result.reason = (
            f"Значимое изменение: pixel_diff={pixel_diff:.2%}, "
            f"ssim={ssim_score:.3f}, mean_diff={mean_diff:.3f}, "
            f"устойчивость={elapsed_stable:.1f}s"
        )
        self._reference_frame = small
        self._last_saved_frame = small
        self._last_save_time = now
        self._change_pending = False
        self._change_start_time = None
        return result

    def notify_saved(self, frame: np.ndarray):
        """
        Вызывается после фактического сохранения кадра.
        Обновляет внутренний эталон.
        """
        small = self._preprocess(frame)
        self._last_saved_frame = small
        self._reference_frame = small
        self._last_save_time = time.time()
        self._change_pending = False
        self._change_start_time = None

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Уменьшить и перевести в grayscale для быстрого анализа."""
        w = self.config.analysis_width
        h = self.config.analysis_height
        resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY)
        return gray

    def _mean_diff(self, a: np.ndarray, b: np.ndarray) -> float:
        """Средняя абсолютная разница (нормализованная 0–1)."""
        return float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32)))) / 255.0

    def _pixel_diff(self, a: np.ndarray, b: np.ndarray) -> float:
        """Доля пикселей, отличающихся больше порога."""
        diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
        changed = np.sum(diff > self.config.pixel_diff_threshold)
        return float(changed) / diff.size

    def _compute_ssim(self, a: np.ndarray, b: np.ndarray) -> float:
        """Структурное сходство двух grayscale-изображений."""
        if _HAS_SKIMAGE:
            score, _ = ssim(a, b, full=True)
            return float(score)
        else:
            # Fallback: нормализованная корреляция
            a_f = a.astype(np.float32)
            b_f = b.astype(np.float32)
            num = np.sum(a_f * b_f)
            den = np.sqrt(np.sum(a_f ** 2) * np.sum(b_f ** 2)) + 1e-8
            return float(num / den)
