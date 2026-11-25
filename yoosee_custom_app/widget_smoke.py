import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
sys.path.insert(0, os.path.dirname(__file__))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
import widget
print("creating app", flush=True)
app = QApplication([])
print("creating widget", flush=True)
w = widget.Widget()
w.show()
print("widget shown, waiting frames", flush=True)
got = []
w.thread.frame.connect(lambda img: got.append((img.width(), img.height())))
def done():
    print(f"SMOKE frames={len(got)} status={w.status.text()}", flush=True)
    w.close_app()
    app.quit()
QTimer.singleShot(8000, done)
app.exec()
print("SMOKE OK", flush=True)
