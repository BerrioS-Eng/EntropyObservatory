"""
Worker de captura de tráfico.

Ofrece tres modos:

  LIVE       — captura en vivo con scapy.AsyncSniffer. Requiere root o
               CAP_NET_RAW en Linux, admin en Windows, root en macOS.

  REPLAY     — reproduce un archivo .pcapng respetando los timestamps
               originales. Útil para desarrollo, pruebas reproducibles
               y demos en sustentación sin tocar la red.

  SIMULATED  — genera estadísticas sintéticas según el escenario
               seleccionado. No requiere permisos. Para iterar la UI.

Diseño:
  - El worker corre en un QThread.
  - Cada paquete observado se inyecta en un RollingEntropyEstimator
    compartido (thread-safe).
  - La GUI consulta el estimator vía snapshot() en su propio timer.
  - El worker emite señales solo para eventos discretos:
      started, stopped, error(str), packet_observed(int)
"""
from __future__ import annotations

import os
import time
import random
import threading
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

# scapy se importa perezosamente para que el módulo cargue aunque
# el usuario no tenga scapy instalado (modo SIMULATED debe funcionar).
try:
    from scapy.all import AsyncSniffer, PcapReader, IP, IPv6, TCP, UDP, ICMP, Raw
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False

from observatory.entropy import RollingEntropyEstimator


class CaptureMode(Enum):
    LIVE = "live"
    REPLAY = "replay"
    SIMULATED = "simulated"


# ─────────────────────────  helpers  ─────────────────────────
def extract_packet_fields(pkt) -> tuple:
    """
    Extrae los campos relevantes de un paquete scapy.
    Returns: (size, proto, src_ip, dst_port, payload_bytes_or_None)
    """
    size = len(pkt)
    proto = 'OTHER'
    src_ip = None
    dst_port = None

    if IP in pkt:
        src_ip = pkt[IP].src
        if TCP in pkt:
            proto, dst_port = 'TCP', int(pkt[TCP].dport)
        elif UDP in pkt:
            proto, dst_port = 'UDP', int(pkt[UDP].dport)
        elif ICMP in pkt:
            proto = 'ICMP'
        else:
            proto = f'IPproto_{pkt[IP].proto}'
    elif IPv6 in pkt:
        src_ip = pkt[IPv6].src
        if TCP in pkt:
            proto, dst_port = 'TCP6', int(pkt[TCP].dport)
        elif UDP in pkt:
            proto, dst_port = 'UDP6', int(pkt[UDP].dport)
        else:
            proto = 'IPv6_OTHER'
    else:
        proto = 'NoIP'

    payload = bytes(pkt[Raw].load) if Raw in pkt else None
    return size, proto, src_ip, dst_port, payload


# ─────────────────────────  Worker base  ─────────────────────────
class CaptureWorker(QThread):
    """
    QThread genérico para alimentar un RollingEntropyEstimator desde
    distintas fuentes (live / replay / simulated).

    Uso:
        est = RollingEntropyEstimator()
        worker = CaptureWorker.create(CaptureMode.REPLAY, est,
                                      pcap_path='/path/to/file.pcapng')
        worker.error.connect(self._on_capture_error)
        worker.started_capture.connect(self._on_started)
        worker.start()
        ...
        worker.stop_capture()
        worker.wait(2000)
    """
    # Señales
    started_capture = pyqtSignal()
    stopped_capture = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # (packets_processed, packets_total_or_-1)

    def __init__(self, estimator: RollingEntropyEstimator):
        super().__init__()
        self.estimator = estimator
        self._stop_flag = threading.Event()
        self._pkts_seen = 0

    @classmethod
    def create(cls, mode: CaptureMode, estimator: RollingEntropyEstimator,
               **kwargs) -> 'CaptureWorker':
        """Factory por modo."""
        if mode == CaptureMode.LIVE:
            return LiveCaptureWorker(estimator, **kwargs)
        if mode == CaptureMode.REPLAY:
            return ReplayCaptureWorker(estimator, **kwargs)
        if mode == CaptureMode.SIMULATED:
            return SimulatedCaptureWorker(estimator, **kwargs)
        raise ValueError(f"Modo desconocido: {mode}")

    def stop_capture(self) -> None:
        """Solicita parar. Llama wait() después para sincronización."""
        self._stop_flag.set()

    # Hooks que las subclases implementan
    def run(self) -> None:                   # pragma: no cover
        raise NotImplementedError


# ─────────────────────────  Live  ─────────────────────────
class LiveCaptureWorker(CaptureWorker):
    """Captura en vivo con scapy.AsyncSniffer."""

    def __init__(
        self,
        estimator: RollingEntropyEstimator,
        interface: Optional[str] = None,
        bpf_filter: str = "",
    ):
        super().__init__(estimator)
        self.interface = interface          # None = todas / 'any' en Linux
        self.bpf_filter = bpf_filter or None
        self._sniffer = None

    def run(self) -> None:
        if not SCAPY_AVAILABLE:
            self.error.emit("scapy no está instalado. Ejecuta: pip install scapy")
            return

        # En Linux comprobamos privilegios temprano para dar mejor error
        if hasattr(os, 'geteuid') and os.geteuid() != 0:
            # No abortamos: intenta de todas formas (puede tener CAP_NET_RAW)
            pass

        try:
            self._sniffer = AsyncSniffer(
                iface=self.interface,
                filter=self.bpf_filter,
                prn=self._on_packet,
                store=False,
            )
            self._sniffer.start()
            self.started_capture.emit()

            # Loop de espera; el callback _on_packet hace todo el trabajo
            while not self._stop_flag.wait(0.1):
                pass

            self._sniffer.stop()
            self.stopped_capture.emit()

        except PermissionError:
            self.error.emit(
                "Permiso denegado para captura en vivo. Ejecuta con sudo o "
                "concede CAP_NET_RAW al intérprete de Python."
            )
        except OSError as e:
            self.error.emit(f"Error de red: {e}")
        except Exception as e:
            self.error.emit(f"Error de captura: {type(e).__name__}: {e}")

    def _on_packet(self, pkt) -> None:
        try:
            size, proto, src_ip, dst_port, payload = extract_packet_fields(pkt)
            self.estimator.observe(
                ts=time.time(),
                size=size, proto=proto,
                src_ip=src_ip, dst_port=dst_port,
                payload=payload,
            )
            self._pkts_seen += 1
            if self._pkts_seen % 100 == 0:
                self.progress.emit(self._pkts_seen, -1)
        except Exception:
            # Nunca dejar que un paquete malformado mate al sniffer
            pass


# ─────────────────────────  Replay  ─────────────────────────
class ReplayCaptureWorker(CaptureWorker):
    """
    Reproduce un .pcapng respetando timestamps relativos.

    `speed`:
        1.0  — tiempo real
        >1.0 — más rápido (5.0 = 5×, 60.0 = 1 minuto/segundo)
        0.0  — tan rápido como pueda (sin sleep)
    `loop`: vuelve a empezar al terminar.
    """

    def __init__(
        self,
        estimator: RollingEntropyEstimator,
        pcap_path: str | Path,
        speed: float = 1.0,
        loop: bool = False,
    ):
        super().__init__(estimator)
        self.pcap_path = Path(pcap_path)
        self.speed = max(0.0, speed)
        self.loop = loop

    def run(self) -> None:
        if not SCAPY_AVAILABLE:
            self.error.emit("scapy no está instalado.")
            return
        if not self.pcap_path.exists():
            self.error.emit(f"Archivo no encontrado: {self.pcap_path}")
            return

        try:
            self.started_capture.emit()
            while not self._stop_flag.is_set():
                self._replay_once()
                if not self.loop:
                    break
                self.estimator.reset()
            self.stopped_capture.emit()
        except Exception as e:
            self.error.emit(f"Error de replay: {type(e).__name__}: {e}")

    def _replay_once(self) -> None:
        first_pcap_ts: Optional[float] = None
        replay_start = time.time()

        with PcapReader(str(self.pcap_path)) as pr:
            for pkt in pr:
                if self._stop_flag.is_set():
                    return
                pcap_ts = float(pkt.time)
                if first_pcap_ts is None:
                    first_pcap_ts = pcap_ts

                # Calcular cuánto esperar para mantener timing original
                if self.speed > 0:
                    target_elapsed = (pcap_ts - first_pcap_ts) / self.speed
                    actual_elapsed = time.time() - replay_start
                    sleep_for = target_elapsed - actual_elapsed
                    if sleep_for > 0:
                        # interruptible sleep
                        if self._stop_flag.wait(sleep_for):
                            return

                try:
                    size, proto, src_ip, dst_port, payload = extract_packet_fields(pkt)
                    self.estimator.observe(
                        ts=time.time(),
                        size=size, proto=proto,
                        src_ip=src_ip, dst_port=dst_port,
                        payload=payload,
                    )
                    self._pkts_seen += 1
                    if self._pkts_seen % 200 == 0:
                        self.progress.emit(self._pkts_seen, -1)
                except Exception:
                    pass


# ─────────────────────────  Simulated  ─────────────────────────
class SimulatedCaptureWorker(CaptureWorker):
    """
    Genera paquetes sintéticos en una de seis regiones del espacio de
    escenarios. Útil para iterar UI sin red ni archivos.

    El escenario puede cambiarse en caliente con set_scenario().
    """

    SCENARIOS = {
        'idle':       {'rate':   5,  'h_target': 7.55, 'proto_mix': {'TCP': 0.5, 'UDP': 0.3, 'ICMP': 0.2}},
        'navegacion': {'rate': 150,  'h_target': 7.95, 'proto_mix': {'TCP': 0.99, 'UDP': 0.01}},
        'streaming':  {'rate': 280,  'h_target': 7.99, 'proto_mix': {'TCP': 0.95, 'UDP': 0.05}},
        'descarga':   {'rate': 220,  'h_target': 7.97, 'proto_mix': {'TCP': 1.0}},
        'cifrado':    {'rate': 200,  'h_target': 7.9999, 'proto_mix': {'TCP': 1.0}},
        'ddos':       {'rate': 1500, 'h_target': 6.5, 'proto_mix': {'TCP': 1.0}},
    }

    def __init__(self, estimator: RollingEntropyEstimator,
                 scenario: str = 'navegacion'):
        super().__init__(estimator)
        self._scenario_lock = threading.Lock()
        self.set_scenario(scenario)

    def set_scenario(self, scenario: str) -> None:
        with self._scenario_lock:
            self._scenario = scenario if scenario in self.SCENARIOS else 'idle'

    def run(self) -> None:
        self.started_capture.emit()
        next_pkt_t = time.time()

        while not self._stop_flag.is_set():
            with self._scenario_lock:
                cfg = self.SCENARIOS[self._scenario]

            interval = 1.0 / cfg['rate']
            now = time.time()
            if now < next_pkt_t:
                if self._stop_flag.wait(min(0.05, next_pkt_t - now)):
                    break
                continue

            # Sintetizar paquete
            size = random.randint(60, 1500)
            proto = self._pick_proto(cfg['proto_mix'])
            src_ip = self._fake_ip(self._scenario)
            dst_port = self._fake_port(self._scenario)
            payload = self._fake_payload(size - 40, cfg['h_target'])

            self.estimator.observe(
                ts=now,
                size=size, proto=proto,
                src_ip=src_ip, dst_port=dst_port,
                payload=payload,
            )
            self._pkts_seen += 1
            next_pkt_t += interval

        self.stopped_capture.emit()

    @staticmethod
    def _pick_proto(mix: dict) -> str:
        r = random.random()
        cum = 0.0
        for p, w in mix.items():
            cum += w
            if r <= cum:
                return p
        return list(mix.keys())[-1]

    @staticmethod
    def _fake_ip(scenario: str) -> str:
        if scenario == 'ddos':
            # entropía baja: muchos paquetes desde misma IP
            return f"10.0.0.{random.choice([7, 7, 7, 7, 8])}"
        if scenario == 'navegacion':
            # entropía alta: muchas IPs distintas
            return f"104.{random.randint(16,31)}.{random.randint(0,255)}.{random.randint(0,255)}"
        # cifrado: pocas IPs concentradas
        return f"203.0.113.{random.choice([10, 11, 12])}"

    @staticmethod
    def _fake_port(scenario: str) -> int:
        if scenario == 'navegacion':
            return random.choice([443, 443, 443, 80, 8080, random.randint(1024, 65535)])
        if scenario == 'cifrado':
            return random.choice([443, 51820])  # https + wireguard
        return random.choice([80, 443])

    @staticmethod
    def _fake_payload(size: int, h_target: float) -> bytes:
        """Genera bytes con H_payload aproximadamente igual al target."""
        if size <= 0:
            return b''
        if h_target > 7.99:
            return os.urandom(size)
        if h_target < 4.0:
            # baja entropía: bytes muy repetitivos
            return bytes([random.randint(65, 90)] * size)
        # entropía media: mezcla
        random_part = os.urandom(int(size * (h_target / 8.0)))
        repeated_part = bytes([0x20] * (size - len(random_part)))
        return random_part + repeated_part