"""Panel termodinámico: balance de Landauer."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QLabel, QWidget

from observatory.physics import ThermodynamicBalance

from .panel import Panel


class ThermoPanel(Panel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Balance termodinámico", parent)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)

        def metric(col: int, title: str, unit: str) -> QLabel:
            t = QLabel(title.upper()); t.setProperty("role", "title")
            v = QLabel("—");           v.setProperty("role", "metric")
            u = QLabel(unit);          u.setProperty("role", "unit")
            grid.addWidget(t, 0, col)
            grid.addWidget(v, 1, col)
            grid.addWidget(u, 2, col, alignment=Qt.AlignmentFlag.AlignTop)
            return v

        self.bits_value      = metric(0, "Bits procesados", "bits")
        self.e_real_value    = metric(1, "Energía real",    "J")
        self.e_landauer_value= metric(2, "Energía Landauer","J")
        self.ratio_value     = metric(3, "Ineficiencia",    "E_real / E_min")
        self.temp_value      = metric(4, "T referencia",    "K")
        grid.setColumnStretch(5, 1)

        self.body_layout.addLayout(grid)

        self.msg = QLabel("Sin datos.")
        self.msg.setWordWrap(True)
        self.msg.setProperty("role", "hint")
        self.body_layout.addWidget(self.msg)
        self.body_layout.addStretch(1)

    def update_from(self, balance: ThermodynamicBalance) -> None:
        self.bits_value.setText(f"{balance.bits_processed:.3e}")
        self.e_real_value.setText(f"{balance.energy_real_J:.3e}")
        self.e_landauer_value.setText(f"{balance.energy_landauer_J:.3e}")
        self.ratio_value.setText(f"{balance.inefficiency_factor:.2e}")
        self.temp_value.setText(f"{balance.temperature_K:.1f}")
        self.msg.setText(balance.qualitative_message())