"""
Ventana principal. Cablea:
  - RollingEntropyEstimator + CaptureWorker (LIVE/REPLAY/SIMULADO)
  - SensorBackend (real o mock)
  - 4 paneles en layout 2×2
  - QTimer central a 2 Hz que llama snapshot() + sensor.read() y
    propaga al UI.

Hilos:
  - El estimator es thread-safe; el worker corre en su propio QThread.
  - El sensor backend se lee desde el hilo Qt (read() es <5 ms).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStatusBar, QToolBar, QWidget,
)

from observatory.entropy import RollingEntropyEstimator
from observatory.physics import compute_balance
from observatory.sensors import MockSensorBackend, SensorBackend, detect
from observatory.workers import (
    CaptureMode, CaptureWorker,
    LiveCaptureWorker, ReplayCaptureWorker, SimulatedCaptureWorker,
)

from .theme import Palette, apply_pyqtgraph_defaults
from .widgets import EntropyPanel, SensorPanel, ThermoPanel, TrafficPanel


_TICK_MS = 500
# pkts/s que consideramos "100% de carga" para el sensor mock
_RATE_SATURATION = 1000.0


class MainWindow(QMainWindow):
    def __init__(self, default_pcap: Optional[Path] = None):
        super().__init__()
        self.setWindowTitle("Entropy Observatory")
        self.resize(1400, 880)

        self._default_pcap = default_pcap

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

    # ─────────────────────────  layout  ─────────────────────────
    def _build_toolbar(self) -> None:
        tb = QToolBar("Controles")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addWidget(QLabel("Modo:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Simulado", CaptureMode.SIMULATED)
        self.mode_combo.addItem("Replay",   CaptureMode.REPLAY)
        self.mode_combo.addItem("En vivo",  CaptureMode.LIVE)
        tb.addWidget(self.mode_combo)

        tb.addSeparator()

        self.start_btn = QPushButton("● Capturar")
        self.start_btn.setProperty("role", "primary")
        self.start_btn.clicked.connect(self._on_start_clicked)
        tb.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ Detener")
        self.stop_btn.setProperty("role", "danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        tb.addWidget(self.stop_btn)

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
    def _on_start_clicked(self) -> None:
        mode: CaptureMode = self.mode_combo.currentData()
        try:
            worker = self._build_worker(mode)
        except RuntimeError as e:
            QMessageBox.warning(self, "No se pudo iniciar", str(e))
            return
        if worker is None:
            return

        self.estimator.reset()
        self.entropy_panel.reset()
        self.sensor_panel.reset()

        worker.error.connect(self._on_capture_error)
        worker.started_capture.connect(lambda: self.status_msg.setText(f"Captura activa ({mode.value})."))
        worker.stopped_capture.connect(lambda: self.status_msg.setText("Captura detenida."))

        self.worker = worker
        worker.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.mode_combo.setEnabled(False)

    def _build_worker(self, mode: CaptureMode) -> Optional[CaptureWorker]:
        if mode == CaptureMode.SIMULATED:
            return SimulatedCaptureWorker(self.estimator, scenario="navegacion")
        if mode == CaptureMode.LIVE:
            return LiveCaptureWorker(self.estimator)
        if mode == CaptureMode.REPLAY:
            pcap = self._default_pcap
            if pcap is None:
                path, _ = QFileDialog.getOpenFileName(
                    self, "Selecciona un archivo .pcap/.pcapng",
                    filter="PCAP (*.pcap *.pcapng);;Todos (*)",
                )
                if not path:
                    return None
                pcap = Path(path)
            return ReplayCaptureWorker(self.estimator, pcap_path=pcap, speed=1.0)
        raise RuntimeError(f"Modo no soportado: {mode}")

    def _on_stop_clicked(self) -> None:
        if self.worker is None:
            return
        self.worker.stop_capture()
        self.worker.wait(3000)
        self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.mode_combo.setEnabled(True)

    def _on_capture_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Error de captura", msg)
        self._on_stop_clicked()

    def _on_sensor_changed(self) -> None:
        kind = self.sensor_combo.currentData()
        try:
            self.sensor.stop()
        except Exception:
            pass
        self.sensor = MockSensorBackend() if kind == "mock" else detect()
        self.sensor.start()
        self.sensor_panel.reset()

    # ─────────────────────────  tick  ─────────────────────────
    def _on_tick(self) -> None:
        snap = self.estimator.snapshot()

        # Si el sensor es mock, alimentarle la carga real de paquetes
        if isinstance(self.sensor, MockSensorBackend):
            self.sensor.set_load(min(1.0, snap.pkt_rate / _RATE_SATURATION))

        reading = self.sensor.read()

        # Bits procesados = total_bytes * 8 (proxy crudo);
        # T de referencia = temperatura medida o 300 K.
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
    def closeEvent(self, event) -> None:  # noqa: N802
        if self.worker is not None:
            self.worker.stop_capture()
            self.worker.wait(3000)
        try:
            self.sensor.stop()
        except Exception:
            pass
        super().closeEvent(event)