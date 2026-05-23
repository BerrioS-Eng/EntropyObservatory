"""
Backend Linux: RAPL (energía) + hwmon (temperatura).

RAPL expone contadores de energía acumulada en microjoules:
    /sys/class/powercap/intel-rapl:0/energy_uj
    /sys/class/powercap/intel-rapl:0/max_energy_range_uj   (wrap point)

P = ΔE / Δt diferenciando dos lecturas. El contador hace wrap; usamos
`max_energy_range_uj` para corregirlo.

Temperatura: /sys/class/hwmon/hwmon*/temp*_input (milésimas de °C).
Tomamos la primera entrada con `name` en {coretemp, k10temp, zenpower,
cpu_thermal, k8temp}, preferentemente con label "package"/"tctl"/"tdie".

Permisos: en kernels modernos `energy_uj` requiere root o
`chmod a+r`. Si no se puede leer, reportamos `power_W=None` y la UI
sigue funcionando con solo temperatura.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .base import SensorBackend, SensorReading


RAPL_ROOT = Path("/sys/class/powercap")
HWMON_ROOT = Path("/sys/class/hwmon")

_CPU_HWMON_NAMES = {"coretemp", "k10temp", "zenpower", "cpu_thermal", "k8temp"}


def _read_int(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _find_rapl_package(root: Path = RAPL_ROOT) -> Optional[Path]:
    """
    Primer dominio RAPL de tipo `package-*`.

    En kernels modernos coexisten dos "control types":
      - intel-rapl       (MSR)
      - intel-rapl-mmio  (MMIO)
    Reportan la misma medición. Preferimos el MSR: suele tener permisos
    más laxos y MMIO es opcional. Si solo está disponible MMIO, lo usamos.
    """
    if not root.is_dir():
        return None

    msr: list[Path] = []
    mmio: list[Path] = []
    for entry in sorted(root.iterdir()):
        try:
            name = (entry / "name").read_text().strip()
        except OSError:
            continue
        if not name.startswith("package"):
            continue
        (mmio if "mmio" in entry.name else msr).append(entry)

    if msr:
        return msr[0]
    if mmio:
        return mmio[0]
    return None

def _find_cpu_hwmon_temp(root: Path = HWMON_ROOT) -> Optional[Path]:
    if not root.is_dir():
        return None
    for entry in sorted(root.iterdir()):
        try:
            chip = (entry / "name").read_text().strip().lower()
        except OSError:
            continue
        if chip not in _CPU_HWMON_NAMES:
            continue
        candidates = sorted(entry.glob("temp*_input"))
        if not candidates:
            continue
        for inp in candidates:
            label_file = inp.with_name(inp.name.replace("_input", "_label"))
            try:
                label = label_file.read_text().strip().lower()
            except OSError:
                label = ""
            if "package" in label or "tctl" in label or "tdie" in label:
                return inp
        return candidates[0]
    return None

def _find_fan_input(root: Path = HWMON_ROOT) -> Optional[Path]:
    """Primer `fan*_input` en hwmon. Prefiere etiquetas 'CPU'/'Processor'."""
    if not root.is_dir():
        return None
    candidates: list[Path] = []
    for entry in sorted(root.iterdir()):
        candidates.extend(sorted(entry.glob("fan*_input")))
    if not candidates:
        return None
    for fan in candidates:
        label_file = fan.with_name(fan.name.replace("_input", "_label"))
        try:
            label = label_file.read_text().strip().lower()
        except OSError:
            label = ""
        if "cpu" in label or "processor" in label:
            return fan
    return candidates[0]


class LinuxSensorBackend(SensorBackend):
    """RAPL (energía) + hwmon (temperatura) en sistemas Linux."""

    name = "linux"

    def __init__(self) -> None:
        self._rapl_dir: Optional[Path] = None
        self._energy_file: Optional[Path] = None
        self._max_energy_uj: Optional[int] = None
        self._temp_file: Optional[Path] = None
        self._fan_file: Optional[Path] = None

        self._last_uj: Optional[int] = None
        self._last_ts: Optional[float] = None
        self._cumulative_J: float = 0.0

    @classmethod
    def available(cls) -> bool:
        return _find_rapl_package() is not None or _find_cpu_hwmon_temp() is not None

    def start(self) -> None:
        self._rapl_dir = _find_rapl_package()
        if self._rapl_dir is not None:
            self._energy_file = self._rapl_dir / "energy_uj"
            self._max_energy_uj = _read_int(self._rapl_dir / "max_energy_range_uj")
            initial = _read_int(self._energy_file)
            if initial is None:
                self._energy_file = None
            else:
                self._last_uj = initial
                self._last_ts = time.monotonic()

        self._temp_file = _find_cpu_hwmon_temp()
        self._fan_file = _find_fan_input()
        self._cumulative_J = 0.0

    def stop(self) -> None:
        self._last_uj = None
        self._last_ts = None

    def read(self) -> SensorReading:
        now = time.monotonic()
        temp = self._read_temp()
        fan = self._read_fan()
        power, delta_J = self._read_power_and_delta(now)
        if delta_J > 0:
            self._cumulative_J += delta_J

        sources = []
        if self._energy_file is not None:
            sources.append("rapl")
        if self._temp_file is not None:
            sources.append("hwmon")
        if self._fan_file is not None and "hwmon" not in sources:
            sources.append("hwmon")
        src = "+".join(sources) if sources else "linux_empty"

        return SensorReading(
            timestamp=time.time(),
            cpu_temp_C=temp,
            power_W=power,
            energy_J=self._cumulative_J,
            fan_rpm=fan,
            is_real=bool(sources),
            source=src,
        )

    def _read_temp(self) -> Optional[float]:
        if self._temp_file is None:
            return None
        milliC = _read_int(self._temp_file)
        return None if milliC is None else milliC / 1000.0
    
    def _read_fan(self) -> Optional[float]:
        if self._fan_file is None:
            return None
        rpm = _read_int(self._fan_file)
        return None if rpm is None else float(rpm)

    def _read_power_and_delta(self, now: float) -> tuple[Optional[float], float]:
        if self._energy_file is None or self._last_uj is None or self._last_ts is None:
            return None, 0.0
        current = _read_int(self._energy_file)
        if current is None:
            return None, 0.0

        dt = now - self._last_ts
        if dt <= 0:
            return None, 0.0

        d_uj = current - self._last_uj
        if d_uj < 0 and self._max_energy_uj:
            d_uj += self._max_energy_uj
        # dt > 30 s indica que el sistema durmió; descartar muestra
        if d_uj < 0 or dt > 30.0:
            self._last_uj = current
            self._last_ts = now
            return None, 0.0

        delta_J = d_uj / 1_000_000.0
        power_W = delta_J / dt
        self._last_uj = current
        self._last_ts = now
        return power_W, delta_J