"""Arranque de la aplicación PyQt6."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from observatory.ui import MainWindow
from observatory.ui.theme import QSS, apply_pyqtgraph_defaults


def run() -> int:
    apply_pyqtgraph_defaults()
    app = QApplication(sys.argv)
    app.setApplicationName("Entropy Observatory")
    app.setStyleSheet(QSS)

    win = MainWindow()
    win.show()
    code = app.exec()

    # pyqtgraph recomienda esto en Linux para evitar segfaults durante
    # el shutdown del intérprete (objetos QObject que se destruyen en
    # orden no determinista). Es una salida explícita: no retorna.
    import pyqtgraph as pg
    pg.exit()
    return code   # inalcanzable; queda por simetría con el tipo declarado