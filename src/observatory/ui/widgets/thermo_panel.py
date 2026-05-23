"""
Panel termodinámico: balance de Landauer.

Diseño:
  - Headline: factor de ineficiencia como m × 10ⁿ (el "resultado" del experimento).
  - LogScaleGauge: barra log10 con marcadores de referencia (Landauer,
    biológico, hipotético, CMOS) — convierte el número adimensional en
    una posición visual interpretable.
  - Métricas auxiliares: bits, energías y temperatura en unidades humanas.
  - Mensaje cualitativo con interpretación contextual.
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from observatory.physics import ThermodynamicBalance

from ..theme import Palette
from .panel import Panel


# ─────────────────────────  helpers de formato  ─────────────────────────
def _format_bits(n: float) -> str:
    if n < 1e3:   return f"{n:.0f} bits"
    if n < 1e6:   return f"{n / 1e3:.2f} kbits"
    if n < 1e9:   return f"{n / 1e6:.2f} Mbits"
    if n < 1e12:  return f"{n / 1e9:.2f} Gbits"
    return f"{n / 1e12:.2f} Tbits"


def _format_energy(j: float) -> str:
    if j == 0:
        return "0 J"
    a = abs(j)
    if a < 1e-15: return f"{j * 1e18:.2f} aJ"
    if a < 1e-12: return f"{j * 1e15:.2f} fJ"
    if a < 1e-9:  return f"{j * 1e12:.2f} pJ"
    if a < 1e-6:  return f"{j * 1e9:.2f} nJ"
    if a < 1e-3:  return f"{j * 1e6:.2f} µJ"
    if a < 1:     return f"{j * 1e3:.2f} mJ"
    if a < 1e3:   return f"{j:.2f} J"
    return f"{j / 1e3:.2f} kJ"


def _split_mantissa_exp(x: float) -> tuple[float, int]:
    """x ≈ m × 10^e con 1 ≤ |m| < 10."""
    if x == 0 or not math.isfinite(x):
        return 0.0, 0
    e = int(math.floor(math.log10(abs(x))))
    return x / (10 ** e), e


_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _superscript(n: int) -> str:
    return str(n).translate(_SUP)


# ─────────────────────────  Gauge  ─────────────────────────
class LogScaleGauge(QWidget):
    """Barra horizontal log10 con marcadores fijos e indicador móvil."""

    # (exponente, etiqueta, color)
    REFERENCES = (
        (0,  "Landauer",   Palette.OK),
        (5,  "Biológico",  Palette.SERIES[5]),
        (10, "Hipotético", Palette.ACCENT),
        (14, "CMOS",       Palette.WARN),
    )

    MIN_EXP = -1
    MAX_EXP = 18

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._exp: float = float("nan")
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_exponent(self, exp: float) -> None:
        self._exp = exp
        self.update()

    def _x_of(self, exp: float, bar_left: int, bar_width: int) -> int:
        t = (exp - self.MIN_EXP) / (self.MAX_EXP - self.MIN_EXP)
        return bar_left + int(round(t * bar_width))

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        margin = 18
        bar_left = margin
        bar_right = rect.width() - margin
        bar_width = bar_right - bar_left
        bar_top = 26
        bar_height = 10

        # Track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(Palette.BG_DEEP))
        p.drawRoundedRect(bar_left, bar_top, bar_width, bar_height, 5, 5)

        # Marcadores
        small = QFont(); small.setPointSize(8)
        p.setFont(small)
        for exp, label, color in self.REFERENCES:
            x = self._x_of(exp, bar_left, bar_width)
            p.setPen(QPen(QColor(color), 1, Qt.PenStyle.DashLine))
            p.drawLine(x, bar_top - 7, x, bar_top + bar_height + 7)
            # exponente arriba
            p.setPen(QPen(QColor(Palette.FG_DIM)))
            p.drawText(x - 30, bar_top - 22, 60, 14,
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                       f"10{_superscript(exp)}")
            # etiqueta abajo
            p.setPen(QPen(QColor(color)))
            p.drawText(x - 50, bar_top + bar_height + 8, 100, 14,
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       label)

        # Indicador
        if math.isfinite(self._exp):
            clamped = max(self.MIN_EXP, min(self.MAX_EXP, self._exp))
            x = self._x_of(clamped, bar_left, bar_width)
            radius = 8
            p.setPen(QPen(QColor(Palette.BG_DEEP), 2))
            p.setBrush(QColor(Palette.ACCENT))
            p.drawEllipse(x - radius, bar_top + bar_height // 2 - radius,
                          radius * 2, radius * 2)


# ─────────────────────────  ThermoPanel  ─────────────────────────
class ThermoPanel(Panel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Balance termodinámico", parent)

        # ── Headline (subtítulo + número grande) ──
        headline = QVBoxLayout()
        headline.setSpacing(2)
        headline.setContentsMargins(0, 4, 0, 4)

        sub = QLabel("FACTOR DE INEFICIENCIA")
        sub.setProperty("role", "title")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.addWidget(sub)

        self.factor_label = QLabel()
        self.factor_label.setTextFormat(Qt.TextFormat.RichText)
        self.factor_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.factor_label.setText(self._headline_html(None))
        headline.addWidget(self.factor_label)

        self.body_layout.addLayout(headline)

        # ── Gauge log ──
        self.gauge = LogScaleGauge()
        self.body_layout.addWidget(self.gauge)

        # ── Métricas auxiliares ──
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(2)
        grid.setContentsMargins(0, 6, 0, 0)

        def aux(col: int, label: str) -> QLabel:
            t = QLabel(label.upper()); t.setProperty("role", "title")
            v = QLabel("—")
            v.setStyleSheet(f"color: {Palette.FG}; font-size: 13px; font-weight: 500;")
            grid.addWidget(t, 0, col)
            grid.addWidget(v, 1, col)
            return v

        self.bits_value       = aux(0, "Bits procesados")
        self.e_real_value     = aux(1, "Energía real")
        self.e_landauer_value = aux(2, "Mínimo de Landauer")
        self.temp_value       = aux(3, "Temperatura")
        grid.setColumnStretch(4, 1)
        self.body_layout.addLayout(grid)

        # ── Mensaje cualitativo ──
        self.msg = QLabel("Esperando datos…")
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(
            f"color: {Palette.FG_DIM}; font-size: 11px; padding-top: 8px;"
            f"border-top: 1px solid {Palette.BORDER}; margin-top: 4px;"
        )
        self.body_layout.addWidget(self.msg)
        self.body_layout.addStretch(1)

    @staticmethod
    def _headline_html(balance: Optional[ThermodynamicBalance]) -> str:
        if balance is None or balance.inefficiency_factor <= 0:
            return (
                f'<span style="font-size:40px; font-weight:700;'
                f' color:{Palette.FG_MUTED};">—</span>'
            )
        m, e = _split_mantissa_exp(balance.inefficiency_factor)
        return (
            f'<span style="font-size:42px; font-weight:700; color:{Palette.FG};">{m:.2f}</span>'
            f'&nbsp;<span style="font-size:22px; color:{Palette.FG_DIM};">× 10</span>'
            f'<sup style="font-size:18px; font-weight:700; color:{Palette.FG};">{e}</sup>'
        )

    def update_from(self, balance: ThermodynamicBalance) -> None:
        # Métricas auxiliares siempre
        self.bits_value.setText(_format_bits(balance.bits_processed))
        self.e_real_value.setText(_format_energy(balance.energy_real_J))
        self.e_landauer_value.setText(_format_energy(balance.energy_landauer_J))
        T_C = balance.temperature_K - 273.15
        self.temp_value.setText(f"{balance.temperature_K:.1f} K  ({T_C:.1f} °C)")

        # Sin bits / sin energía → headline vacío con mensaje específico
        if balance.bits_processed <= 0:
            self.factor_label.setText(self._headline_html(None))
            self.gauge.set_exponent(float("nan"))
            self.msg.setText("Esperando paquetes para empezar el balance.")
            return
        if balance.energy_real_J <= 0:
            self.factor_label.setText(self._headline_html(None))
            self.gauge.set_exponent(float("nan"))
            self.msg.setText(
                "Sin energía medida. En Linux habilita RAPL: "
                "sudo chmod a+r /sys/class/powercap/intel-rapl:*/energy_uj"
            )
            return

        # Headline + gauge
        self.factor_label.setText(self._headline_html(balance))
        self.gauge.set_exponent(math.log10(balance.inefficiency_factor))

        # Mensaje con interpretación contextual
        ratio = balance.inefficiency_factor
        _, e = _split_mantissa_exp(ratio)
        if ratio > 1e14:
            band = "Régimen CMOS típico"
        elif ratio > 1e11:
            band = "Hardware en su rango habitual de eficiencia"
        elif ratio > 1e6:
            band = "Eficiencia inusualmente alta — revisar instrumentación"
        else:
            band = "Cerca del límite cuántico — resultado sospechoso"

        self.msg.setText(
            f"{band}. Tu hardware disipa ~10{_superscript(e)} veces el mínimo "
            f"termodinámico de Landauer para procesar este tráfico."
        )
