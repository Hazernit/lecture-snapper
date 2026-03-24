"""
Конфигурация по умолчанию для Lecture Snapper.
Все параметры могут быть переопределены через GUI.
"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppConfig:
    # --- Параметры детекции ---
    check_interval: float = 1.5        # Интервал проверки экрана (сек)
    change_threshold: float = 0.13     # Порог изменения (0.0–1.0, ~13%)
    stability_duration: float = 2.0    # Изменение должно держаться (сек)
    min_pause: float = 8.0             # Минимальная пауза между сохранениями (сек)
    ssim_threshold: float = 0.92       # Порог SSIM для детекции изменения
    duplicate_ssim: float = 0.88       # Порог SSIM для дубликата
    pixel_diff_threshold: int = 25     # Порог разницы пикселей (0–255)
    noise_threshold: float = 0.02      # Порог шума (мерцание/курсор)

    # --- Параметры сохранения ---
    output_dir: Path = field(default_factory=lambda: Path.home() / "LectureSnapper")
    pdf_name: str = "lecture.pdf"
    save_png: bool = True              # Сохранять PNG отдельно
    add_timestamp: bool = True         # Добавлять время на страницу PDF

    # --- Область экрана ---
    region: dict = field(default_factory=lambda: {"left": 0, "top": 0, "width": 1920, "height": 1080})

    # --- Размер для анализа (меньше = быстрее) ---
    analysis_width: int = 320
    analysis_height: int = 240
