"""
Cálculo de entropía de Shannon — funciones puras.

H(X) = − Σ p(i) · log₂(p(i))

Las funciones de este módulo no mantienen estado. Para entropía en ventana
deslizante, ver `observatory.entropy.rolling.RollingEntropyEstimator`.
"""
from __future__ import annotations
import math
from collections import Counter
from typing import Iterable

import numpy as np


def shannon_from_counter(counter: Counter | dict) -> float:
    """H de una distribución categórica representada como Counter/dict."""
    total = sum(counter.values())
    if total == 0:
        return 0.0
    H = 0.0
    for c in counter.values():
        if c <= 0:
            continue
        p = c / total
        H -= p * math.log2(p)
    return H


def shannon_from_counts_array(counts: np.ndarray) -> float:
    """H de un array numpy de conteos. Vectorizado, ~100× más rápido que Counter."""
    total = counts.sum()
    if total == 0:
        return 0.0
    # Solo bins no vacíos (log2(0) sería −inf)
    nz = counts[counts > 0]
    p = nz / total
    return float(-np.sum(p * np.log2(p)))


def shannon_from_bytes(data: bytes | bytearray) -> float:
    """H byte-a-byte de una secuencia binaria, en bits/byte (cota 8)."""
    if not data:
        return 0.0
    arr = np.frombuffer(data, dtype=np.uint8)
    counts = np.bincount(arr, minlength=256)
    return shannon_from_counts_array(counts)


def shannon_normalized(H: float, n_symbols: int) -> float:
    """Normaliza H a [0, 1] dividiendo por log₂(n_símbolos)."""
    if n_symbols <= 1:
        return 0.0
    return H / math.log2(n_symbols)