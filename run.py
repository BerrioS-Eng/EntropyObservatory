#!/usr/bin/env python3
"""
Launcher de conveniencia: `python run.py` desde la raíz del repo.

Equivalente a `python -m observatory` con src/ en PYTHONPATH.
"""
import sys
from pathlib import Path

# Hacer importable src/observatory sin instalar el paquete
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from observatory.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())