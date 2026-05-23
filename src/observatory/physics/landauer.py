"""
Física: límite de Landauer y métricas derivadas.

Landauer (1961): borrar 1 bit de información a temperatura T cuesta como
mínimo E_min = kT · ln(2) joules de energía disipada.

Para N bits procesados, la energía mínima total es:
    E_landauer = N · kT · ln(2)

Esta es una cota inferior fundamental, no un valor alcanzable por el silicio
actual (que opera ~10¹³–10¹⁵ veces por encima).
"""
import math
from dataclasses import dataclass

K_BOLTZMANN = 1.380649e-23  # J / K, valor SI exacto desde 2019


@dataclass
class ThermodynamicBalance:
    bits_processed: float
    energy_real_J: float
    energy_landauer_J: float
    inefficiency_factor: float    # E_real / E_landauer (adimensional)
    temperature_K: float

    def qualitative_message(self) -> str:
        r = self.inefficiency_factor
        if r <= 0 or not math.isfinite(r):
            return "Sin datos suficientes para estimar ineficiencia."
        if r > 1e14:
            return ("Disipación >10¹⁴ veces el mínimo termodinámico — "
                    "régimen típico del silicio CMOS.")
        if r > 1e11:
            return "Hardware operando en su rango habitual de eficiencia."
        if r > 1e6:
            return "Eficiencia inusualmente alta — revisar instrumentación."
        return "Eficiencia cercana al límite cuántico — resultado sospechoso."


def landauer_minimum(n_bits: float, temperature_K: float = 300.0) -> float:
    """Energía mínima teórica para procesar n_bits a temperatura T (J)."""
    if n_bits <= 0:
        return 0.0
    return n_bits * K_BOLTZMANN * temperature_K * math.log(2)


def compute_balance(
    bits_processed: float,
    energy_real_J: float,
    temperature_K: float = 300.0,
) -> ThermodynamicBalance:
    e_min = landauer_minimum(bits_processed, temperature_K)
    if e_min > 0:
        ratio = energy_real_J / e_min
    else:
        ratio = 0.0
    return ThermodynamicBalance(
        bits_processed=bits_processed,
        energy_real_J=energy_real_J,
        energy_landauer_J=e_min,
        inefficiency_factor=ratio,
        temperature_K=temperature_K,
    )