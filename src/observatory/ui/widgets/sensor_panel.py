"""Panel de sensores: temperatura, potencia, energía + badge real/mock."""
from __future__ import annotations

from collections import deque
from typing import Deque

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QWidget

from observatory.sensors import SensorReading

from ..theme import Palette
from .panel import Panel


class SensorPanel(Panel):
    HISTORY_POINTS = 240

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Hardware", parent)

        header = QHBoxLayout()
        self.source_label = QLabel("Fuente: —")
        self.source_label.setProperty("role", "hint")
        self.badge = QLabel("MOCK")
        self.badge.setProperty("role", "badge_mock")
        header.addWidget(self.source_label)
        header.addStretch(1)
        header.addWidget(self.badge)
        self.body_layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)

        def metric(title: str, unit: str) -> QLabel:
            t = QLabel(title.upper()); t.setProperty("role", "title")
            v = QLabel("—");           v.setProperty("role", "metric")
            u = QLabel(unit);          u.setProperty("role", "unit")
            col = grid.columnCount()
            grid.addWidget(t, 0, col)
            grid.addWidget(v, 1, col)
            grid.addWidget(u, 2, col, alignment=Qt.AlignmentFlag.AlignTop)
            return v

        self.temp_value   = metric("CPU temp", "°C")
        self.power_value  = metric("Potencia", "W")
        self.energy_value = metric("Energía", "J")
        self.fan_value    = metric("Ventilador", "rpm")
        grid.setColumnStretch(grid.columnCount(), 1)
        self.body_layout.addLayout(grid)

        self.plot = pg.PlotWidget()
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setMenuEnabled(False)
        self.plot.setBackground(Palette.BG_PANEL_ALT)
        self.plot.getAxis("left").setLabel("T (°C)")
        self.plot.getAxis("bottom").setLabel("t (s, rel.)")
        self._legend = self.plot.addLegend(offset=(10, 5))

        self._t: Deque[float]    = deque(maxlen=self.HISTORY_POINTS)
        self._temp: Deque[float] = deque(maxlen=self.HISTORY_POINTS)
        self._pow: Deque[float]  = deque(maxlen=self.HISTORY_POINTS)
        self._t0: float | None = None

        self._curve_T = self.plot.plot([], [], pen=pg.mkPen(Palette.SERIES[2], width=2), name="T (°C)")
        # Eje secundario para potencia
        self.p_axis = pg.ViewBox()
        self.plot.scene().addItem(self.p_axis)
        self.plot.getAxis("right").linkToView(self.p_axis)
        self.plot.showAxis("right")
        self.plot.getAxis("right").setLabel("P (W)")
        self.p_axis.setXLink(self.plot.getViewBox())
        self._curve_P = pg.PlotDataItem([], [], pen=pg.mkPen(Palette.SERIES[3], width=2))
        self.p_axis.addItem(self._curve_P)
        self._legend.addItem(self._curve_P, "P (W)")
        self.plot.getViewBox().sigResized.connect(self._sync_views)

        self.body_layout.addWidget(self.plot, 1)

    def _sync_views(self) -> None:
        self.p_axis.setGeometry(self.plot.getViewBox().sceneBoundingRect())
        self.p_axis.linkedViewChanged(self.plot.getViewBox(), self.p_axis.XAxis)

    def update_from(self, reading: SensorReading) -> None:
        self.source_label.setText(f"Fuente: {reading.source}")
        self.badge.setText("REAL" if reading.is_real else "MOCK")
        self.badge.setProperty("role", "badge_real" if reading.is_real else "badge_mock")
        # Re-aplicar QSS al badge para refrescar color
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

        self.temp_value.setText(f"{reading.cpu_temp_C:.1f}" if reading.cpu_temp_C is not None else "—")
        self.power_value.setText(f"{reading.power_W:.2f}" if reading.power_W is not None else "—")
        self.energy_value.setText(f"{reading.energy_J:.2f}")
        self.fan_value.setText(f"{reading.fan_rpm:.0f}" if reading.fan_rpm is not None else "—")

        if self._t0 is None:
            self._t0 = reading.timestamp
        self._t.append(reading.timestamp - self._t0)
        self._temp.append(reading.cpu_temp_C if reading.cpu_temp_C is not None else float("nan"))
        self._pow.append(reading.power_W if reading.power_W is not None else float("nan"))

        xs = list(self._t)
        self._curve_T.setData(xs, list(self._temp))
        self._curve_P.setData(xs, list(self._pow))

    def reset(self) -> None:
        self._t.clear(); self._temp.clear(); self._pow.clear()
        self._t0 = None
        self._curve_T.setData([], [])
        self._curve_P.setData([], [])