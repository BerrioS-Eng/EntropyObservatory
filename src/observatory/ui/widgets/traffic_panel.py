"""Panel de tráfico: tasa, totales, distribución de protocolos."""
from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QLabel, QWidget

from observatory.entropy import CaptureSnapshot

from ..theme import Palette
from .panel import Panel


def _human_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PiB"


class TrafficPanel(Panel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Tráfico", parent)

        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(2)

        self.rate_value = QLabel("0")
        self.rate_value.setProperty("role", "metric")
        rate_unit = QLabel("pkts/s")
        rate_unit.setProperty("role", "unit")

        self.total_pkts = QLabel("0")
        self.total_pkts.setProperty("role", "metric")
        total_pkts_unit = QLabel("paquetes totales")
        total_pkts_unit.setProperty("role", "unit")

        self.total_bytes = QLabel("0 B")
        self.total_bytes.setProperty("role", "metric")
        total_bytes_unit = QLabel("bytes totales")
        total_bytes_unit.setProperty("role", "unit")

        grid.addWidget(self.rate_value,     0, 0)
        grid.addWidget(rate_unit,           1, 0, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.total_pkts,     0, 1)
        grid.addWidget(total_pkts_unit,     1, 1, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.total_bytes,    0, 2)
        grid.addWidget(total_bytes_unit,    1, 2, alignment=Qt.AlignmentFlag.AlignTop)
        grid.setColumnStretch(3, 1)

        self.body_layout.addLayout(grid)

        # Gráfico de barras de protocolos
        self.plot = pg.PlotWidget()
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setMenuEnabled(False)
        self.plot.getAxis("left").setLabel("paquetes (ventana)")
        self.plot.getAxis("bottom").setStyle(tickFont=None)
        self.plot.setBackground(Palette.BG_PANEL_ALT)

        self._bars: pg.BarGraphItem | None = None
        self.body_layout.addWidget(self.plot, 1)

    def update_from(self, snap: CaptureSnapshot) -> None:
        self.rate_value.setText(f"{snap.pkt_rate:.0f}")
        self.total_pkts.setText(f"{snap.total_pkts:,}".replace(",", " "))
        self.total_bytes.setText(_human_bytes(snap.total_bytes))

        breakdown = snap.proto_breakdown or {}
        items = sorted(breakdown.items(), key=lambda kv: -kv[1])[:6]
        xs = list(range(len(items)))
        ys = [c for _, c in items]
        labels = [p for p, _ in items]

        self.plot.clear()
        if not items:
            return
        bars = pg.BarGraphItem(x=xs, height=ys, width=0.6, brush=Palette.ACCENT)
        self.plot.addItem(bars)
        ax = self.plot.getAxis("bottom")
        ax.setTicks([list(zip(xs, labels))])