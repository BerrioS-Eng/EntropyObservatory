"""Arranque de la aplicación PyQt6."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication

from observatory.ui import MainWindow
from observatory.ui.theme import QSS, apply_pyqtgraph_defaults


def run(default_pcap: Optional[Path] = None) -> int:
    apply_pyqtgraph_defaults()
    app = QApplication(sys.argv)
    app.setApplicationName("Entropy Observatory")
    app.setStyleSheet(QSS)

    win = MainWindow(default_pcap=default_pcap)
    win.show()
    return app.exec()