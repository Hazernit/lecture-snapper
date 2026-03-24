"""
Модуль захвата экрана.
Использует mss для быстрого захвата произвольной области.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
import mss


class ScreenCapture:
    """Захватывает заданную область экрана."""

    def __init__(self):
        pass

    @staticmethod
    def _normalize_region(region: dict) -> dict:
        return {
            "left": int(region["left"]),
            "top": int(region["top"]),
            "width": int(region["width"]),
            "height": int(region["height"]),
        }

    def capture(self, region: dict) -> Image.Image:
        """
        Захватить область экрана.

        region: {"left": int, "top": int, "width": int, "height": int}
        Возвращает PIL.Image в формате RGB.
        """
        monitor = self._normalize_region(region)

        with mss.mss() as sct:
            raw = sct.grab(monitor)

        # mss возвращает BGRA → конвертируем в RGB
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img

    def capture_as_array(self, region: dict) -> np.ndarray:
        """Захватить область и вернуть numpy array (RGB)."""
        img = self.capture(region)
        return np.array(img)

    def get_all_monitors(self) -> list[dict]:
        """Получить список всех мониторов."""
        with mss.mss() as sct:
            return [
                {
                    "left": m["left"],
                    "top": m["top"],
                    "width": m["width"],
                    "height": m["height"],
                }
                for m in sct.monitors[1:]  # [0] — все мониторы вместе
            ]

    def get_primary_monitor(self) -> dict:
        """Получить параметры основного монитора."""
        monitors = self.get_all_monitors()
        return monitors[0] if monitors else {
            "left": 0,
            "top": 0,
            "width": 1920,
            "height": 1080,
        }

    def close(self):
        pass

    def __del__(self):
        pass