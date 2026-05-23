"""
Estimador de entropía sobre ventana deslizante temporal.

Diseñado para alimentarse desde un hilo de captura (scapy) y ser consultado
desde el hilo de GUI a través de `snapshot()`. La estructura es thread-safe.

Estrategia:
- `observe(pkt)` se llama por cada paquete (hot path → debe ser rápido).
  Solo agrega a colas y acumuladores; no hace cálculos pesados.
- `snapshot()` se llama por la GUI a 2 Hz típico. Aquí ocurre el trim de
  datos viejos y el cálculo de las cuatro H.
"""
from __future__ import annotations
import time
import threading
from collections import deque, Counter
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .shannon import shannon_from_counter, shannon_from_counts_array


@dataclass
class CaptureSnapshot:
    """Estado instantáneo expuesto a la GUI."""
    timestamp: float = 0.0
    # Entropías
    h_payload: float = 0.0          # bits / byte (0..8)
    h_ip_src: float = 0.0           # bits
    h_port_dst: float = 0.0         # bits
    h_proto: float = 0.0            # bits
    # Flujo
    pkt_rate: float = 0.0           # paquetes / segundo (ventana)
    total_pkts: int = 0
    total_bytes: int = 0
    payload_bytes_window: int = 0
    # Distribución de protocolos en ventana
    proto_breakdown: dict = field(default_factory=dict)
    # Diagnóstico
    bytes_payload_dropped: int = 0  # bytes que cayeron del buffer por cap


class RollingEntropyEstimator:
    """
    Mantiene estadísticas sobre los últimos `window_seconds` segundos de tráfico.

    Limita el payload acumulado a `max_payload_bytes` (default 5 MB) para acotar
    consumo de memoria bajo cargas altas (DDoS, descargas masivas).
    """

    def __init__(
        self,
        window_seconds: float = 10.0,
        max_payload_bytes: int = 5_000_000,
    ):
        self.window_seconds = window_seconds
        self.max_payload_bytes = max_payload_bytes

        self._lock = threading.Lock()

        # Cola de paquetes en ventana: (ts, size, proto, src_ip, dst_port)
        self._packets: deque = deque()
        # Cola de payloads en ventana: (ts, np.ndarray uint8)
        self._payloads: deque = deque()
        self._payload_size = 0

        # Conteo de bytes vectorizado (cumulativo sobre ventana)
        self._byte_counts = np.zeros(256, dtype=np.int64)

        # Conteos categóricos sobre ventana
        self._ip_counts: Counter = Counter()
        self._port_counts: Counter = Counter()
        self._proto_counts: Counter = Counter()

        # Acumulados desde inicio de sesión (no se reciclan)
        self.total_pkts = 0
        self.total_bytes = 0
        self.bytes_payload_dropped = 0

    # ─────────────────────────  hot path  ─────────────────────────
    def observe(
        self,
        ts: float,
        size: int,
        proto: str,
        src_ip: Optional[str],
        dst_port: Optional[int],
        payload: Optional[bytes],
    ) -> None:
        """Registra un paquete. Diseñado para llamarse 1000+ veces/s."""
        with self._lock:
            self.total_pkts += 1
            self.total_bytes += size

            self._packets.append((ts, size, proto, src_ip, dst_port))
            self._proto_counts[proto] += 1
            if src_ip is not None:
                self._ip_counts[src_ip] += 1
            if dst_port is not None:
                self._port_counts[dst_port] += 1

            if payload:
                arr = np.frombuffer(payload, dtype=np.uint8)
                self._payloads.append((ts, arr))
                self._payload_size += len(arr)
                self._byte_counts += np.bincount(arr, minlength=256)

                # Cap duro de memoria — descarta los más viejos
                while self._payload_size > self.max_payload_bytes and self._payloads:
                    _, old = self._payloads.popleft()
                    self._byte_counts -= np.bincount(old, minlength=256)
                    self._payload_size -= len(old)
                    self.bytes_payload_dropped += len(old)

    # ─────────────────────────  consult path  ─────────────────────────
    def snapshot(self) -> CaptureSnapshot:
        """Computa H sobre la ventana actual. Llamado a ~2 Hz por la GUI."""
        with self._lock:
            now = time.time()
            self._trim_locked(now)

            h_payload = shannon_from_counts_array(self._byte_counts) if self._payload_size else 0.0
            h_ip = shannon_from_counter(self._ip_counts)
            h_port = shannon_from_counter(self._port_counts)
            h_proto = shannon_from_counter(self._proto_counts)

            n_window = len(self._packets)
            rate = n_window / self.window_seconds if n_window else 0.0

            return CaptureSnapshot(
                timestamp=now,
                h_payload=h_payload,
                h_ip_src=h_ip,
                h_port_dst=h_port,
                h_proto=h_proto,
                pkt_rate=rate,
                total_pkts=self.total_pkts,
                total_bytes=self.total_bytes,
                payload_bytes_window=self._payload_size,
                proto_breakdown=dict(self._proto_counts),
                bytes_payload_dropped=self.bytes_payload_dropped,
            )

    def reset(self) -> None:
        with self._lock:
            self._packets.clear()
            self._payloads.clear()
            self._payload_size = 0
            self._byte_counts.fill(0)
            self._ip_counts.clear()
            self._port_counts.clear()
            self._proto_counts.clear()
            self.total_pkts = 0
            self.total_bytes = 0
            self.bytes_payload_dropped = 0

    # ─────────────────────────  internal  ─────────────────────────
    def _trim_locked(self, now: float) -> None:
        """Elimina datos más viejos que la ventana. Asume lock adquirido."""
        cutoff = now - self.window_seconds

        # Paquetes (categóricos)
        while self._packets and self._packets[0][0] < cutoff:
            _, _, p_proto, p_ip, p_port = self._packets.popleft()
            self._dec_counter(self._proto_counts, p_proto)
            if p_ip is not None:
                self._dec_counter(self._ip_counts, p_ip)
            if p_port is not None:
                self._dec_counter(self._port_counts, p_port)

        # Payloads
        while self._payloads and self._payloads[0][0] < cutoff:
            _, old = self._payloads.popleft()
            self._byte_counts -= np.bincount(old, minlength=256)
            self._payload_size -= len(old)

    @staticmethod
    def _dec_counter(c: Counter, key) -> None:
        c[key] -= 1
        if c[key] <= 0:
            del c[key]