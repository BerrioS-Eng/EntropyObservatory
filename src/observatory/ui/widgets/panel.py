"""
Panel base: marco + título tipográfico. Todos los paneles de la UI
heredan de aquí para que el chrome sea consistente.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..theme import Palette


class Panel(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setStyleSheet(
            f"#panel {{ background: {Palette.BG_PANEL}; "
            f"border: 1px solid {Palette.BORDER}; border-radius: 10px; }}"
        )

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(14, 12, 14, 12)
        self._outer.setSpacing(8)

        self._title = QLabel(title.upper())
        self._title.setProperty("role", "title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._outer.addWidget(self._title)

        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        self._outer.addWidget(self.body, 1)

    def set_title(self, title: str) -> None:
        self._title.setText(title.upper())