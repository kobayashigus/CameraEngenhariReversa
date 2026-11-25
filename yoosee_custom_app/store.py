"""CameraStore: estado unico do painel (espelha RemoteStore do LG, versao camera)."""
from __future__ import annotations
import glob
import json
import os
from PySide6.QtCore import QObject, Signal

from journal import Journal, EventLog

try:
    from widget import load_cam as _load_cam, save_cam as _save_cam
except Exception:  # fallback p/ testes sem Qt
    _load_cam = _save_cam = None

BASE = os.path.dirname(os.path.abspath(__file__))

STATUS_IDLE = "desconectado"
STATUS_CONNECTING = "conectandoâ€¦"
STATUS_LIVE = "ao vivo Â· UDP H.265"
STATUS_PAUSED = "pausado"
STATUS_ERROR = "erro"
STATUS_RECORDING = "gravando"


class CameraStore(QObject):
    statusChanged = Signal(str)
    statsChanged = Signal()
    galleryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cam = _load_cam() if _load_cam else {"nome": "Minha Yoosee", "ip": "192.168.1.100"}
        self.status = STATUS_IDLE
        self.last_error = ""
        self.recording = False
        self.rec_file = ""
        self.rec_secs = 0
        self.sound_on = False
        self.low_quality = False  # False=HD onvif1, True=SD onvif2
        self.journal = Journal()
        self.events = EventLog()
        self.photos: list[dict] = []
        self.videos: list[dict] = []
        self.refresh_gallery()

    # ---- estado ----
    def set_status(self, status: str, error: str = ""):
        changed = (status != self.status) or (bool(error) and error != self.last_error)
        self.status = status
        if error:
            self.last_error = error
        self.journal.observe(self._journal_state())
        if not changed:
            return
        self.statusChanged.emit(status)
        self.statsChanged.emit()

    def _journal_state(self) -> str:
        s = self.status.lower()
        if "gravando" in s or "rec" in s:
            return "gravando"
        if "vivo" in s or "live" in s:
            return "live"
        return "paused"

    def log(self, title: str, detail: str = ""):
        self.events.log(title, detail)
        self.statsChanged.emit()

    # ---- camera ----
    def reload(self):
        if _load_cam:
            self.cam = _load_cam()
        self.statsChanged.emit()

    def save_cam(self, cam: dict):
        self.cam = dict(cam)
        if _save_cam:
            _save_cam(self.cam)
        self.log("Config", f"{self.cam.get('nome','')} Â· {self.cam.get('ip','')}")
        self.statsChanged.emit()

    # ---- galeria local ----
    def refresh_gallery(self):
        photos, videos = [], []
        for p in sorted(glob.glob(os.path.join(BASE, "*.jpg")) + glob.glob(os.path.join(BASE, "*.jpeg")),
                        key=os.path.getmtime, reverse=True)[:60]:
            try:
                photos.append({"name": os.path.basename(p), "path": p,
                               "size": os.path.getsize(p), "mtime": os.path.getmtime(p)})
            except OSError:
                pass
        for p in sorted(glob.glob(os.path.join(BASE, "*.mp4")),
                        key=os.path.getmtime, reverse=True)[:60]:
            try:
                videos.append({"name": os.path.basename(p), "path": p,
                               "size": os.path.getsize(p), "mtime": os.path.getmtime(p)})
            except OSError:
                pass
        self.photos, self.videos = photos, videos
        self.galleryChanged.emit()

    def to_dict(self) -> dict:
        # p/ debug/smoke sem expor senha
        c = dict(self.cam)
        c.pop("password", None)
        return {"cam": c, "status": self.status, "recording": self.recording,
                "photos": len(self.photos), "videos": len(self.videos),
                "events": len(self.events.events)}
