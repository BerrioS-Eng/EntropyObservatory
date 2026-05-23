"""
Interfaz común para backends de sensores térmicos / de energía.

Todos los backends de plataforma (Linux RAPL, Windows LHM, macOS powermetrics)
devuelven el mismo `SensorReading`, de modo que la UI no necesita saber de
dónde viene el dato.

Convenciones:
    - `cpu_temp_C`: temperatura del paquete CPU. `None` si no disponible.
    - `power_W`: potencia instantánea (J/s) sobre el último intervalo entre
      reads. `None` si no disponible.
    - `energy_J`: energía total acumulada desde `start()`. Monótono creciente.
    - `fan_rpm`: RPM del ventilador principal si el backend lo expone.
    - `is_real`: True si proviene de hardware, False si es simulador.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SensorReading:
    timestamp: float
    cpu_temp_C: Optional[float] = None
    power_W: Optional[float] = None
    energy_J: float = 0.0
    fan_rpm: Optional[float] = None
    is_real: bool = False
    source: str = "unknown"     # "rapl", "hwmon", "mock", "lhm", "powermetrics"


class SensorBackend(ABC):
    """Backend abstracto. `read()` debe ser barato (<5 ms)."""

    name: str = "base"

    def start(self) -> None:
        """Inicializa estado interno (offsets de energía, file handles, etc.)."""

    def stop(self) -> None:
        """Libera recursos. Idempotente."""

    @abstractmethod
    def read(self) -> SensorReading:
        """Devuelve una lectura instantánea. Nunca lanza — usa `None` si falla."""

    @classmethod
    @abstractmethod
    def available(cls) -> bool:
        """True si este backend puede inicializarse en la plataforma actual."""