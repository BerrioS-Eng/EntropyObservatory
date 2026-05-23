"""
Sensores de temperatura y energía del CPU.

Uso típico:
    from observatory.sensors import detect
    backend = detect()
    backend.start()
    reading = backend.read()   # SensorReading
"""
from __future__ import annotations

import sys

from .base import SensorBackend, SensorReading
from .mock import MockSensorBackend

if sys.platform.startswith("linux"):
    from .linux import LinuxSensorBackend
else:
    LinuxSensorBackend = None  # type: ignore[assignment]


def detect(force_mock: bool = False) -> SensorBackend:
    """Backend más adecuado para la plataforma; cae a mock si no hay nada."""
    if force_mock:
        return MockSensorBackend()
    if LinuxSensorBackend is not None and LinuxSensorBackend.available():
        return LinuxSensorBackend()
    return MockSensorBackend()


__all__ = [
    "SensorBackend",
    "SensorReading",
    "MockSensorBackend",
    "LinuxSensorBackend",
    "detect",
]