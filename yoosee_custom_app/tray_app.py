"""Entrada tray + popover. Uso: python tray_app.py [--standalone]"""
from __future__ import annotations
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from store import CameraStore
from panel import TrayPanel


def make_icon(recording: bool = False) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    color = QColor("#ff5470") if recording else QColor("#35d07f")
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawEllipse(6, 6, 52, 52)
    p.setBrush(QColor("#06130c"))
    p.drawEllipse(22, 22, 20, 20)
    p.end()
    return QIcon(pm)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Yoosee")

    store = CameraStore()
    panel = TrayPanel(store)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        panel.show()
        return app.exec()

    tray = QSystemTrayIcon(make_icon(False))
    tray.setToolTip("Yoosee — clique para abrir")
    menu = QMenu()
    a_open = QAction("Abrir painel", menu)
    a_open.triggered.connect(lambda: panel.toggle_near())
    a_folder = QAction("Abrir pasta", menu)
    a_folder.triggered.connect(lambda: os.startfile(BASE))
    a_quit = QAction("Sair", menu)
    a_quit.triggered.connect(lambda: (panel.close_app(), app.quit()))
    menu.addAction(a_open)
    menu.addAction(a_folder)
    menu.addSeparator()
    menu.addAction(a_quit)
    tray.setContextMenu(menu)
    tray.show()

    def on_status(_s):
        tray.setIcon(make_icon(store.recording))
        tray.setToolTip(f"Yoosee — {store.status}")

    store.statusChanged.connect(on_status)

    def activated(reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick, QSystemTrayIcon.MiddleClick):
            from PySide6.QtGui import QCursor
            panel.toggle_near(QCursor.pos())

    tray.activated.connect(activated)

    if "--standalone" in sys.argv or "--show" in sys.argv:
        panel.show()

    store.log("App", "tray iniciado")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
