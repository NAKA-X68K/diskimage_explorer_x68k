from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def color_to_css(color: QColor) -> str:
    if color.alpha() == 255:
        return color.name(QColor.HexRgb)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def blend_colors(base: QColor, overlay: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    inv = 1.0 - ratio
    return QColor(
        int(base.red() * inv + overlay.red() * ratio),
        int(base.green() * inv + overlay.green() * ratio),
        int(base.blue() * inv + overlay.blue() * ratio),
        int(base.alpha() * inv + overlay.alpha() * ratio),
    )


def is_dark_palette(palette: QPalette) -> bool:
    return palette.color(QPalette.Window).lightness() < palette.color(QPalette.WindowText).lightness()


def should_use_dark_mode(app: QApplication) -> bool:
    hints = app.styleHints()
    try:
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return is_dark_palette(app.palette())


def build_dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor(37, 37, 38)
    base = QColor(30, 30, 30)
    alt = QColor(45, 45, 48)
    text = QColor(240, 240, 240)
    dim_text = QColor(180, 180, 180)
    button = QColor(51, 51, 55)
    highlight = QColor(10, 132, 255)

    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, alt)
    palette.setColor(QPalette.ToolTipBase, alt)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, button)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.BrightText, QColor(255, 120, 120))
    palette.setColor(QPalette.Link, QColor(110, 168, 255))
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.PlaceholderText, dim_text)
    palette.setColor(QPalette.Disabled, QPalette.Text, dim_text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, dim_text)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, dim_text)
    return palette


def apply_app_theme(app: QApplication) -> None:
    if should_use_dark_mode(app):
        app.setPalette(build_dark_palette())
    else:
        app.setPalette(app.style().standardPalette())
