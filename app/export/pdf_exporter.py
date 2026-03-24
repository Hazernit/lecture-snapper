"""
Сборка PDF из набора PNG-скриншотов.
Каждый скриншот → отдельная страница PDF.
При необходимости добавляет метку времени.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Шрифт для меток времени (fallback на стандартный)
_TIMESTAMP_FONT_SIZE = 22


def build_pdf(
    image_paths: list[Path],
    output_path: Path,
    add_timestamp: bool = True,
    page_numbers: bool = True,
) -> Path:
    """
    Собрать PDF из списка PNG-файлов.

    image_paths:  список путей к PNG (в порядке захвата)
    output_path:  куда сохранять PDF
    add_timestamp: добавлять метку времени на каждую страницу
    page_numbers:  добавлять номер страницы

    Возвращает финальный путь к PDF.
    """
    if not image_paths:
        raise ValueError("Список изображений пуст — нечего собирать в PDF")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pages: list[Image.Image] = []

    for idx, img_path in enumerate(image_paths, start=1):
        try:
            img = Image.open(str(img_path)).convert("RGB")
        except Exception as e:
            logger.warning(f"Не удалось открыть {img_path}: {e} — пропускаю")
            continue

        if add_timestamp or page_numbers:
            img = _annotate(img, img_path, idx, len(image_paths), add_timestamp, page_numbers)

        pages.append(img)

    if not pages:
        raise ValueError("Все изображения оказались недоступны")

    first, rest = pages[0], pages[1:]
    try:
        first.save(
            str(output_path),
            format="PDF",
            save_all=True,
            append_images=rest,
            resolution=150,
        )
    except PermissionError:
        raise PermissionError(
            f"Файл PDF уже открыт или нет прав на запись: {output_path}"
        )

    logger.info(f"PDF сохранён: {output_path} ({len(pages)} страниц)")
    return output_path


# ----------------------------------------------------------------------
# Вспомогательные функции
# ----------------------------------------------------------------------

def _annotate(
    img: Image.Image,
    source_path: Path,
    page_num: int,
    total: int,
    add_timestamp: bool,
    add_page_num: bool,
) -> Image.Image:
    """Добавить на изображение метку времени и/или номер страницы."""
    draw = ImageDraw.Draw(img)
    font = _get_font(_TIMESTAMP_FONT_SIZE)

    w, h = img.size
    margin = 10
    parts: list[str] = []

    if add_page_num:
        parts.append(f"Стр. {page_num}/{total}")

    if add_timestamp:
        ts = _extract_timestamp(source_path)
        if ts:
            parts.append(ts)

    if not parts:
        return img

    text = "  |  ".join(parts)
    # Полупрозрачный фон под текстом
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        tw, th = len(text) * 12, 20

    x = margin
    y = h - th - margin * 2

    # Тёмный прямоугольник-подложка
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle(
        [x - 4, y - 4, x + tw + 8, y + th + 8],
        fill=(0, 0, 0, 160),
    )
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    draw.text((x, y), text, fill=(255, 255, 220), font=font)
    return img


def _get_font(size: int):
    """Загрузить шрифт или вернуть дефолтный."""
    # Пробуем Windows-шрифты
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    from PIL import ImageFont
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _extract_timestamp(path: Path) -> str:
    """Извлечь временную метку из имени файла (slide_0001_20240115_143022.png)."""
    name = path.stem
    # Ищем паттерн YYYYMMDD_HHMMSS
    m = re.search(r"(\d{8})_(\d{6})", name)
    if m:
        try:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            return dt.strftime("%d.%m.%Y %H:%M:%S")
        except ValueError:
            pass
    # Fallback — дата модификации файла
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return ""
