"""Smoke offscreen do novo painel tray (sem rede/camera)."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

import theme
import journal
import store as store_mod
from panel import TrayPanel

print("theme accent:", theme.accent_for("ao vivo · UDP H.265"), theme.accent_for("erro"), theme.accent_for("pausado"), flush=True)
j = journal.Journal(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".smoke_usage.json"))
j.observe("live"); j.observe("paused")
print("journal totals:", j.totals(1), flush=True)
print("duration:", journal.duration_fmt(65), journal.duration_fmt(3700), flush=True)

app = QApplication([])
st = store_mod.CameraStore()
print("store:", st.to_dict(), flush=True)
p = TrayPanel(st)
p.show()
print("panel visible tabs:", p.stack.count(), "gallery items:", p.gal_list.count(), flush=True)
for i in range(5):
    p.set_tab(i)
    app.processEvents()
    assert p.stack.currentIndex() == i, i
    print(f"tab {i} ok: {p.stack.currentWidget() is not None}", flush=True)
p.set_period(7)
app.processEvents()
print("big_number:", p.big_number.text(), "| stats:", p.act_stats.text()[:80], flush=True)
p.set_tab(0)
p.toggle_near()
print("toggle hide ok:", not p.isVisible(), flush=True)
p.close_app()
print("SMOKE PANEL OK", flush=True)
app.quit()
