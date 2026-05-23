"""
Ventana principal. Cablea:
  - RollingEntropyEstimator + CaptureWorker (LIVE/SIMULADO)
  - SensorBackend (real o mock)
  - 4 paneles en layout 2*2
  - QTimer central a 2 Hz

Comportamiento UX:
  - El combo "Modo" es el estado: cambiarlo reinicia la captura.
  - Al abrir, se inicia automáticamente en el modo por defecto.
  - Si LIVE falla por permisos, cae a SIMULADO y se notifica.
"""
from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox, QGridLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStatusBar, QToolBar, QWidget,
)

from observatory.entropy import RollingEntropyEstimator
from observatory.physics import compute_balance
from observatory.sensors import MockSensorBackend, SensorBackend, detect
from observatory.workers import (
    CaptureMode, CaptureWorker,
    LiveCaptureWorker, SimulatedCaptureWorker,
)

from .widgets import EntropyPanel, SensorPanel, ThermoPanel, TrafficPanel


_TICK_MS = 500
_RATE_SATURATION = 1000.0   # pkts/s que consideramos "100%" para el sensor mock


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Entropy Observatory")
        self.resize(1400, 880)

        self.estimator = RollingEntropyEstimator(window_seconds=10.0)
        self.worker: Optional[CaptureWorker] = None
        self.sensor: SensorBackend = detect()
        self.sensor.start()

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        self.timer = QTimer(self)
        self.timer.setInterval(_TICK_MS)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start()

        # Auto-start en el modo seleccionado por defecto
        self._start_capture()

    # ─────────────────────────  layout  ─────────────────────────
    def _build_toolbar(self) -> None:
        tb = QToolBar("Controles")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addWidget(QLabel("Modo:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("En vivo",  CaptureMode.LIVE)
        self.mode_combo.addItem("Simulado", CaptureMode.SIMULATED)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        tb.addWidget(self.mode_combo)

        tb.addSeparator()

        self.toggle_btn = QPushButton("⏸ Pausar")
        self.toggle_btn.setProperty("role", "danger")
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        tb.addWidget(self.toggle_btn)

        tb.addSeparator()

        tb.addWidget(QLabel("Sensor:"))
        self.sensor_combo = QComboBox()
        self.sensor_combo.addItem("Auto (real si hay)", "auto")
        self.sensor_combo.addItem("Forzar simulado",   "mock")
        self.sensor_combo.currentIndexChanged.connect(self._on_sensor_changed)
        tb.addWidget(self.sensor_combo)

    def _build_central(self) -> None:
        central = QWidget()
        grid = QGridLayout(central)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.traffic_panel = TrafficPanel()
        self.entropy_panel = EntropyPanel()
        self.sensor_panel  = SensorPanel()
        self.thermo_panel  = ThermoPanel()

        grid.addWidget(self.traffic_panel, 0, 0)
        grid.addWidget(self.entropy_panel, 0, 1)
        grid.addWidget(self.sensor_panel,  1, 0)
        grid.addWidget(self.thermo_panel,  1, 1)

        grid.setRowStretch(0, 1); grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)

        self.setCentralWidget(central)

    def _build_statusbar(self) -> None:
        sb = QStatusBar(self)
        self.status_msg = QLabel("Inactivo.")
        sb.addWidget(self.status_msg, 1)
        self.privilege_msg = QLabel(self._privilege_hint())
        self.privilege_msg.setProperty("role", "hint")
        sb.addPermanentWidget(self.privilege_msg)
        self.setStatusBar(sb)

    @staticmethod
    def _privilege_hint() -> str:
        if sys.platform.startswith("linux"):
            import os
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                return "Privilegios: root ✓"
            return "Privilegios: usuario (LIVE requiere sudo o CAP_NET_RAW)"
        if sys.platform == "win32":
            return "Privilegios: ejecutar como Administrador para LIVE"
        if sys.platform == "darwin":
            return "Privilegios: sudo necesario para LIVE"
        return ""

    # ─────────────────────────  capture lifecycle  ─────────────────────────
    def _build_worker(self, mode: CaptureMode) -> CaptureWorker:
        if mode == CaptureMode.LIVE:
            return LiveCaptureWorker(self.estimator)
        if mode == CaptureMode.SIMULATED:
            return SimulatedCaptureWorker(self.estimator, scenario="navegacion")
        raise RuntimeError(f"Modo no soportado: {mode}")

    def _start_capture(self) -> None:
        if self.worker is not None:
            return
        mode: CaptureMode = self.mode_combo.currentData()
        worker = self._build_worker(mode)

        self.estimator.reset()
        self.entropy_panel.reset()
        self.sensor_panel.reset()

        worker.error.connect(self._on_capture_error)
        worker.started_capture.connect(
            lambda m=mode: self.status_msg.setText(f"Captura activa ({m.value}).")
        )
        worker.stopped_capture.connect(
            lambda: self.status_msg.setText("Captura detenida.")
        )

        self.worker = worker
        worker.start()
        self._set_toggle_state(True)

    def _stop_capture(self) -> None:
        worker = self.worker
        if worker is None:
            return
        self.worker = None
        # Desconectar antes de detener: si scapy emite tardíamente,
        # nadie recibe (evita reentrar a la GUI ya cerrada).
        try:
            worker.error.disconnect()
            worker.started_capture.disconnect()
            worker.stopped_capture.disconnect()
        except (TypeError, RuntimeError):
            pass
        worker.stop_capture()
        worker.wait(5000)
        self._set_toggle_state(False)

    def _on_mode_changed(self) -> None:
        """Cambiar el modo = reiniciar la captura en el nuevo modo."""
        if self.worker is not None:
            self._stop_capture()
            self._start_capture()

    def _on_capture_error(self, msg: str) -> None:
        was_live = self.mode_combo.currentData() == CaptureMode.LIVE
        QMessageBox.critical(self, "Error de captura", msg)
        self._stop_capture()
        if was_live:
            # Fallback a Simulado para que la GUI no quede muda
            idx = self.mode_combo.findData(CaptureMode.SIMULATED)
            if idx >= 0:
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentIndex(idx)
                self.mode_combo.blockSignals(False)
            self.status_msg.setText("LIVE no disponible — usando Simulado.")
            self._start_capture()

    def _on_sensor_changed(self) -> None:
        kind = self.sensor_combo.currentData()
        try:
            self.sensor.stop()
        except Exception:
            pass
        self.sensor = MockSensorBackend() if kind == "mock" else detect()
        self.sensor.start()
        self.sensor_panel.reset()

    def _on_toggle_clicked(self) -> None:
        if self.worker is not None:
            self._stop_capture()
        else:
            self._start_capture()

    def _set_toggle_state(self, capturing: bool) -> None:
        """Sincroniza el texto y el rol visual del botón con el estado."""
        self.toggle_btn.setText("⏸ Pausar" if capturing else "⏵ Reanudar")
        self.toggle_btn.setProperty("role", "danger" if capturing else "primary")
        s = self.toggle_btn.style()
        s.unpolish(self.toggle_btn); s.polish(self.toggle_btn)

    # ─────────────────────────  tick  ─────────────────────────
    def _on_tick(self) -> None:
        if self.worker is None:
            return
        snap = self.estimator.snapshot()

        if isinstance(self.sensor, MockSensorBackend):
            self.sensor.set_load(min(1.0, snap.pkt_rate / _RATE_SATURATION))

        reading = self.sensor.read()

        bits = snap.total_bytes * 8.0
        T = reading.cpu_temp_C + 273.15 if reading.cpu_temp_C is not None else 300.0
        balance = compute_balance(
            bits_processed=bits,
            energy_real_J=reading.energy_J,
            temperature_K=T,
        )

        self.traffic_panel.update_from(snap)
        self.entropy_panel.update_from(snap)
        self.sensor_panel.update_from(reading)
        self.thermo_panel.update_from(balance)

    # ─────────────────────────  shutdown  ─────────────────────────
    def closeEvent(self, event) -> None: 
        # Orden importa: parar el timer ANTES de destruir paneles,
        # luego el worker, luego el sensor, luego super.
        self.timer.stop()
        self._stop_capture()
        try:
            self.sensor.stop()
        except Exception:
            pass
        super().closeEvent(event)
