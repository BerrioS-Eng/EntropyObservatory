"""Panel de entropías: 4 H actuales + serie temporal."""
from __future__ import annotations

from collections import deque
from typing import Deque

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QLabel, QWidget

from observatory.entropy import CaptureSnapshot

from ..theme import Palette
from .panel import Panel


_SERIES = [
    ("h_payload", "H payload",  "bits/byte"),
    ("h_ip_src",  "H IP src",   "bits"),
    ("h_port_dst","H port dst", "bits"),
    ("h_proto",   "H proto",    "bits"),
]


class EntropyPanel(Panel):
    HISTORY_POINTS = 240   # 240 * 0.5 s = 120 s

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Entropía", parent)

        # Métricas grandes en una fila
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)
        self._value_labels: dict[str, QLabel] = {}
        for col, (key, title, unit) in enumerate(_SERIES):
            t = QLabel(title.upper())
            t.setProperty("role", "title")
            v = QLabel("—")
            v.setProperty("role", "metric")
            u = QLabel(unit)
            u.setProperty("role", "unit")
            grid.addWidget(t, 0, col)
            grid.addWidget(v, 1, col)
            grid.addWidget(u, 2, col, alignment=Qt.AlignmentFlag.AlignTop)
            self._value_labels[key] = v
        grid.setColumnStretch(len(_SERIES), 1)
        self.body_layout.addLayout(grid)

        # Plot temporal
        self.plot = pg.PlotWidget()
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setMenuEnabled(False)
        self.plot.setBackground(Palette.BG_PANEL_ALT)
        self.plot.setYRange(0, 8)
        self.plot.getAxis("left").setLabel("H")
        self.plot.getAxis("bottom").setLabel("t (s, rel.)")
        self.plot.addLegend(offset=(10, 5))

        self._t: Deque[float] = deque(maxlen=self.HISTORY_POINTS)
        self._series: dict[str, Deque[float]] = {
            k: deque(maxlen=self.HISTORY_POINTS) for k, _, _ in _SERIES
        }
        self._curves: dict[str, pg.PlotDataItem] = {}
        for i, (key, title, _) in enumerate(_SERIES):
            color = Palette.SERIES[i % len(Palette.SERIES)]
            pen = pg.mkPen(color=color, width=2)
            self._curves[key] = self.plot.plot([], [], pen=pen, name=title)

        self.body_layout.addWidget(self.plot, 1)
        self._t0: float | None = None

    def update_from(self, snap: CaptureSnapshot) -> None:
        for key, label in self._value_labels.items():
            label.setText(f"{getattr(snap, key):.3f}")

        if self._t0 is None:
            self._t0 = snap.timestamp
        self._t.append(snap.timestamp - self._t0)
        for key, _, _ in _SERIES:
            self._series[key].append(float(getattr(snap, key)))

        xs = list(self._t)
        for key, _, _ in _SERIES:
            self._curves[key].setData(xs, list(self._series[key]))

    def reset(self) -> None:
        self._t.clear()
        self._t0 = None
        for d in self._series.values():
            d.clear()
        for c in self._curves.values():
            c.setData([], [])
        for label in self._value_labels.values():
            label.setText("—")