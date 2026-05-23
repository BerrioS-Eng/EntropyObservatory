"""
Backend simulado — usado cuando ningún backend real está disponible o
cuando el usuario elige explícitamente "Simulado" en la UI.

T y P se derivan de `load` (0..1) que la UI calcula a partir de `pkt_rate`.
Suavizado exponencial para evitar saltos visuales.

No es física fiel: es un placeholder visualmente honesto (`is_real=False`).
"""
from __future__ import annotations

import random
import threading
import time
from typing import Optional

from .base import SensorBackend, SensorReading


class MockSensorBackend(SensorBackend):
    name = "mock"

    def __init__(
        self,
        t_idle_C: float = 38.0,
        t_max_C: float = 78.0,
        p_idle_W: float = 6.0,
        p_max_W: float = 35.0,
        smoothing: float = 0.15,
    ):
        self.t_idle = t_idle_C
        self.t_max = t_max_C
        self.p_idle = p_idle_W
        self.p_max = p_max_W
        self.smoothing = smoothing

        self._lock = threading.Lock()
        self._load: float = 0.0
        self._cur_T: float = t_idle_C
        self._cur_P: float = p_idle_W
        self._cumulative_J: float = 0.0
        self._last_ts: Optional[float] = None

    @classmethod
    def available(cls) -> bool:
        return True

    def set_load(self, load: float) -> None:
        """Carga normalizada (0..1) — la fija la UI con base en pkt_rate."""
        with self._lock:
            self._load = max(0.0, min(1.0, float(load)))

    def start(self) -> None:
        with self._lock:
            self._cur_T = self.t_idle
            self._cur_P = self.p_idle
            self._cumulative_J = 0.0
            self._last_ts = time.monotonic()

    def read(self) -> SensorReading:
        with self._lock:
            now = time.monotonic()
            target_T = self.t_idle + (self.t_max - self.t_idle) * self._load
            target_P = self.p_idle + (self.p_max - self.p_idle) * self._load

            self._cur_T += self.smoothing * (target_T - self._cur_T) + random.uniform(-0.2, 0.2)
            self._cur_P += self.smoothing * (target_P - self._cur_P) + random.uniform(-0.3, 0.3)
            self._cur_P = max(0.1, self._cur_P)

            if self._last_ts is not None:
                dt = now - self._last_ts
                if 0 < dt < 30.0:
                    self._cumulative_J += self._cur_P * dt
            self._last_ts = now

            return SensorReading(
                timestamp=time.time(),
                cpu_temp_C=self._cur_T,
                power_W=self._cur_P,
                energy_J=self._cumulative_J,
                fan_rpm=900.0 + 2000.0 * self._load,
                is_real=False,
                source="mock",
            )