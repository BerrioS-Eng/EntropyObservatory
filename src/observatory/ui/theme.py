"""
Tema oscuro central: paleta + QSS.

Cualquier color de la UI debe vivir aquí, no hardcodeado en widgets.
"""
from __future__ import annotations


class Palette:
    # Fondo
    BG_DEEP = "#0e1116"          # ventana
    BG_PANEL = "#161b22"         # paneles
    BG_PANEL_ALT = "#1c2230"     # zonas hundidas (plots)

    # Bordes y separadores
    BORDER = "#262d3a"
    BORDER_STRONG = "#3a4356"

    # Texto
    FG = "#e6edf3"
    FG_DIM = "#8b96a8"
    FG_MUTED = "#5a6478"

    # Acentos
    ACCENT = "#58a6ff"           # azul info
    ACCENT_2 = "#a371f7"         # violeta
    OK = "#3fb950"
    WARN = "#d29922"
    ERROR = "#f85149"

    # Series para los plots (4 entropías + extras)
    SERIES = ("#58a6ff", "#3fb950", "#f0883e", "#a371f7", "#f85149", "#39c5cf")


QSS = f"""
QMainWindow, QWidget {{
    background-color: {Palette.BG_DEEP};
    color: {Palette.FG};
    font-family: "Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 12px;
}}

QToolBar {{
    background: {Palette.BG_PANEL};
    border: none;
    border-bottom: 1px solid {Palette.BORDER};
    padding: 6px 8px;
    spacing: 8px;
}}

QStatusBar {{
    background: {Palette.BG_PANEL};
    border-top: 1px solid {Palette.BORDER};
    color: {Palette.FG_DIM};
}}

QPushButton {{
    background: {Palette.BG_PANEL_ALT};
    border: 1px solid {Palette.BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 14px;
    color: {Palette.FG};
}}
QPushButton:hover {{ background: #232b3b; }}
QPushButton:pressed {{ background: #1a2030; }}
QPushButton:disabled {{ color: {Palette.FG_MUTED}; border-color: {Palette.BORDER}; }}
QPushButton[role="primary"] {{
    background: {Palette.ACCENT};
    border: 1px solid {Palette.ACCENT};
    color: #0b0f15;
    font-weight: 600;
}}
QPushButton[role="primary"]:hover  {{ background: #79b8ff; }}
QPushButton[role="danger"] {{
    background: {Palette.ERROR};
    border: 1px solid {Palette.ERROR};
    color: white;
    font-weight: 600;
}}

QComboBox {{
    background: {Palette.BG_PANEL_ALT};
    border: 1px solid {Palette.BORDER_STRONG};
    border-radius: 6px;
    padding: 4px 10px;
    color: {Palette.FG};
    min-width: 110px;
}}
QComboBox QAbstractItemView {{
    background: {Palette.BG_PANEL};
    border: 1px solid {Palette.BORDER_STRONG};
    selection-background-color: {Palette.ACCENT};
    selection-color: #0b0f15;
}}

QLabel[role="title"] {{
    color: {Palette.FG_DIM};
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 1.5px;
    font-weight: 600;
}}
QLabel[role="metric"] {{
    color: {Palette.FG};
    font-size: 22px;
    font-weight: 600;
}}
QLabel[role="unit"]   {{ color: {Palette.FG_DIM}; font-size: 11px; }}
QLabel[role="hint"]   {{ color: {Palette.FG_MUTED}; font-size: 11px; }}
QLabel[role="badge_real"] {{
    color: {Palette.OK};
    border: 1px solid {Palette.OK};
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 600;
}}
QLabel[role="badge_mock"] {{
    color: {Palette.WARN};
    border: 1px solid {Palette.WARN};
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 600;
}}
"""


def apply_pyqtgraph_defaults() -> None:
    """Configura pyqtgraph para que herede el tema oscuro."""
    import pyqtgraph as pg
    pg.setConfigOption("background", Palette.BG_PANEL_ALT)
    pg.setConfigOption("foreground", Palette.FG_DIM)
    pg.setConfigOption("antialias", True)