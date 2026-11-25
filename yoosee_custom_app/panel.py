"""Painel estilo LGwebOS-menubar p/ Yoosee single-cam (tray popover)."""
from __future__ import annotations
import datetime
import json
import os
import shutil
import socket
import subprocess
import urllib.parse

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QEvent
from PySide6.QtGui import QPixmap, QAction, QImage
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QSlider, QLineEdit, QListWidget, QListWidgetItem,
    QFormLayout, QMessageBox, QMenu, QGridLayout, QDialog, QDialogButtonBox,
)

from theme import PANEL_W, build_stylesheet, accent_for
from journal import duration_fmt
from motor import MotorDriver

try:
    from widget import VideoThread, AudioThread, rtsp_url, HAS_AUDIO
except Exception:  # pragma: no cover - permite importar store isolado
    VideoThread = AudioThread = None  # type: ignore
    HAS_AUDIO = False

    def rtsp_url(cam, baixa=False):  # type: ignore
        pwd = urllib.parse.quote(cam.get("password", ""), safe="")
        path = cam.get("path_baixa" if baixa else "path_alta", "/onvif1")
        return f'rtsp://{cam.get("user","admin")}:{pwd}@{cam.get("ip","")}:{cam.get("rtsp_port",554)}{path}'

BASE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"
W, H = 960, 540

TABS = [
    ("Ao Vivo", "ðŸ“º"),
    ("Controle", "ðŸŽ®"),
    ("Galeria", "ðŸ–¼"),
    ("Atividade", "ðŸ“Š"),
    ("Ajustes", "âš™"),
]


class DiscoveryThread(QThread):
    found = Signal(str)
    done = Signal(list)

    def __init__(self, base_ip: str):
        super().__init__()
        self.base_ip = base_ip

    def run(self):
        base = ".".join(self.base_ip.split(".")[:3]) if self.base_ip else "192.168.1"
        achou: list[str] = []
        for i in range(1, 255):
            ip = f"{base}.{i}"
            for p in (554, 5000):
                try:
                    s = socket.create_connection((ip, p), timeout=0.25)
                    s.close()
                    if ip not in achou:
                        achou.append(ip)
                        self.found.emit(ip)
                    break
                except Exception:
                    pass
        self.done.emit(achou)


class SnapshotThread(QThread):
    """Foto sem travar a UI (ffmpeg bloqueia segundos com rede ruim)."""
    done = Signal(bool, str)

    def __init__(self, url: str, outfile: str):
        super().__init__()
        self.url = url
        self.outfile = outfile

    def run(self):
        r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-rtsp_transport", "udp",
                            "-i", self.url, "-frames:v", "1", self.outfile])
        self.done.emit(r.returncode == 0, self.outfile)


class FullscreenView(QWidget):
    """Video em tela cheia (duplo-clique/Esc sai). Recebe os frames do painel."""

    def __init__(self):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background: #000;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 16)
        lay.setSpacing(8)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: #000;")
        lay.addWidget(self.label, 1)
        self.hint = QLabel("duplo-clique / Esc para sair")
        self.hint.setObjectName("fsHint")
        self.hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.hint)

    def show_frame(self, img: QImage):
        pix = QPixmap.fromImage(img).scaled(self.label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(pix)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()

    def mouseDoubleClickEvent(self, e):
        self.hide()


class TrayPanel(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.thread = None
        self.audio = None
        self._shot = None
        self.rec_proc = None
        self.period_days = 1
        self._drag = None
        self.disc = None
        self._accent = ""
        self._badge = ""
        self._act_sig = None
        # auto-retry: 1a falha de WiFi nao pode travar o painel em erro
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._do_retry)
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog)
        self.retry_delay = 5
        self.retry_max = 5
        self.watchdog_s = 15
        self._retries = 0
        self._frames_seen = 0
        # zoom digital (a camera anuncia PTZ mas o servico nao responde: ptz_probe.py)
        self.zoom = 1.0
        self.cx = 0.5
        self.cy = 0.5
        self._mode = "onvif1 1920x1080"
        self.presets = self._load_presets()
        self.motor = MotorDriver(log=self.store.log)
        self.fs = FullscreenView()

        self.setObjectName("panelWindow")
        self.setWindowTitle("Yoosee")
        self.setMinimumSize(PANEL_W, 620)
        self.resize(PANEL_W, 700)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.build_ui()
        self.refresh_theme()
        self.wire_store()
        self.start_video()

        self.tick = QTimer(self)
        self.tick.timeout.connect(self.on_tick)
        self.tick.start(1000)
        self.jtick = QTimer(self)
        self.jtick.timeout.connect(lambda: self.store.journal.save())
        self.jtick.start(30000)

    # ---------- ui ----------
    def build_ui(self):
        # Janela externa transparente (cantos arredondados) + container solido.
        # O QSS nao pinta fundo em subclass de QWidget (era a causa do fundo
        # transparente); QWidget puro como container resolve.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.container = QWidget()
        self.container.setObjectName("panelRoot")
        root.addWidget(self.container)
        box = QVBoxLayout(self.container)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(10)

        # header
        head = QHBoxLayout()
        self.dot = QLabel("â—")
        self.dot.setObjectName("dot")
        tt = QVBoxLayout()
        self.title = QLabel(self.store.cam.get("nome", "Yoosee"))
        self.title.setObjectName("title")
        self.subtitle = QLabel("Yoosee Â· ONVIF LAN")
        self.subtitle.setObjectName("subtitle")
        tt.addWidget(self.title)
        tt.addWidget(self.subtitle)
        tt.setSpacing(0)
        head.addWidget(self.dot)
        head.addLayout(tt, 1)
        self.btn_power = QPushButton("â»")
        self.btn_power.setObjectName("ghost")
        self.btn_power.setFixedSize(34, 32)
        self.btn_power.setToolTip("Reconectar")
        self.btn_power.clicked.connect(self.reconnect)
        self.btn_menu = QPushButton("â‹¯")
        self.btn_menu.setObjectName("ghost")
        self.btn_menu.setFixedSize(34, 32)
        self.btn_menu.clicked.connect(self.open_menu)
        head.addWidget(self.btn_power)
        head.addWidget(self.btn_menu)
        box.addLayout(head)

        # tabbar
        bar = QWidget()
        bar.setObjectName("tabbar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(4, 4, 4, 4)
        bl.setSpacing(2)
        self.tab_btns: list[QPushButton] = []
        for i, (name, icon) in enumerate(TABS):
            b = QPushButton(f"{icon}\n{name}")
            b.setCheckable(True)
            b.setObjectName("tabBtnActive" if i == 0 else "tabBtn")
            b.clicked.connect(lambda _=False, idx=i: self.set_tab(idx))
            bl.addWidget(b, 1)
            self.tab_btns.append(b)
        self.tab_btns[0].setChecked(True)
        box.addWidget(bar)

        # stack
        self.stack = QStackedWidget()
        self.page_live = self.build_live()
        self.page_ctrl = self.build_control()
        self.page_gallery = self.build_gallery()
        self.page_activity = self.build_activity()
        self.page_settings = self.build_settings()
        for p in (self.page_live, self.page_ctrl, self.page_gallery, self.page_activity, self.page_settings):
            self.stack.addWidget(p)
        box.addWidget(self.stack, 1)

        # footer
        foot = QHBoxLayout()
        self.foot_dot = QLabel("â—")
        self.foot_dot.setObjectName("dot")
        self.foot_status = QLabel("desconectado")
        self.foot_status.setObjectName("status")
        self.foot_model = QLabel("YOOSEE")
        self.foot_model.setObjectName("subtitle")
        self.btn_gear = QPushButton("âš™")
        self.btn_gear.setObjectName("ghost")
        self.btn_gear.setFixedSize(30, 26)
        self.btn_gear.clicked.connect(lambda: self.set_tab(4))
        foot.addWidget(self.foot_dot)
        foot.addWidget(self.foot_status, 1)
        foot.addWidget(self.foot_model)
        foot.addWidget(self.btn_gear)
        box.addLayout(foot)

    def card(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        w.setObjectName("card")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        return w, lay

    def build_live(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        hero, hl = self.card()
        top = QHBoxLayout()
        self.hero_badge = QLabel("CONECTANDO")
        self.hero_badge.setObjectName("heroBadge")
        self.hero_quality = QLabel("onvif1 Â· 1080p Â· UDP")
        self.hero_quality.setObjectName("status")
        top.addWidget(self.hero_badge)
        top.addWidget(self.hero_quality, 1)
        self.btn_fs = QPushButton("â›¶")
        self.btn_fs.setObjectName("btn")
        self.btn_fs.setFixedSize(40, 28)
        self.btn_fs.setToolTip("Tela cheia (ou duplo-clique no vÃ­deo)")
        self.btn_fs.clicked.connect(self._toggle_fs)
        top.addWidget(self.btn_fs)
        hl.addLayout(top)
        self.video = QLabel("aguardando vÃ­deoâ€¦")
        self.video.setObjectName("video")
        self.video.setMinimumSize(QSize(352, 198))
        self.video.setAlignment(Qt.AlignCenter)
        self.video.installEventFilter(self)
        self._build_ptz_overlay()
        hl.addWidget(self.video)
        self.hero_info = QLabel("")
        self.hero_info.setObjectName("info")
        hl.addWidget(self.hero_info)
        lay.addWidget(hero)

        audio, al = self.card()
        r1 = QHBoxLayout()
        t = QLabel("ðŸŽ™ Ãudio da cÃ¢mera")
        t.setStyleSheet("font-weight:700;")
        self.audio_state = QLabel("mudo")
        self.audio_state.setObjectName("status")
        r1.addWidget(t, 1)
        r1.addWidget(self.audio_state)
        al.addLayout(r1)
        r2 = QHBoxLayout()
        self.btn_sound = QPushButton("ðŸ”‡ Ouvir")
        self.btn_sound.setObjectName("btn")
        self.btn_sound.setCheckable(True)
        self.btn_sound.clicked.connect(self.toggle_sound)
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.valueChanged.connect(self.on_vol)
        self.btn_talk = QPushButton("ðŸŽ¤ Falar")
        self.btn_talk.setObjectName("btn")
        self.btn_talk.clicked.connect(self.talk_info)
        r2.addWidget(self.btn_sound)
        r2.addWidget(self.vol, 1)
        r2.addWidget(self.btn_talk)
        al.addLayout(r2)
        lay.addWidget(audio)

        row = QHBoxLayout()
        self.btn_play = QPushButton("â¸ Pausar")
        self.btn_play.setObjectName("btn")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_q = QPushButton("HD")
        self.btn_q.setObjectName("btn")
        self.btn_q.clicked.connect(self.toggle_quality)
        self.btn_shot = QPushButton("ðŸ“· Foto")
        self.btn_shot.setObjectName("btn")
        self.btn_shot.clicked.connect(self.snapshot)
        self.btn_rec = QPushButton("âº Gravar")
        self.btn_rec.setObjectName("btnDanger")
        self.btn_rec.clicked.connect(self.toggle_rec)
        row.addWidget(self.btn_play)
        row.addWidget(self.btn_q)
        row.addWidget(self.btn_shot)
        row.addWidget(self.btn_rec)
        lay.addLayout(row)

        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("info")
        self.lbl_info.setWordWrap(True)
        lay.addWidget(self.lbl_info)
        lay.addStretch(1)
        return page

    # ---------- zoom digital + overlay ----------
    def _wire_hold(self, btn: QPushButton, slot):
        btn.setAutoRepeat(True)
        btn.setAutoRepeatDelay(280)
        btn.setAutoRepeatInterval(90)
        btn.clicked.connect(slot)
        btn.released.connect(self.motor.stop)

    def _build_ptz_overlay(self):
        ov = QWidget(self.video)
        ov.setObjectName("ptzOverlay")
        lay = QVBoxLayout(ov)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        self.zoom_badge = QLabel("1.0x")
        self.zoom_badge.setObjectName("zoomBadge")
        self.zoom_badge.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.zoom_badge)
        grid = QGridLayout()
        grid.setSpacing(3)
        for txt, r, c in [("â–²", 0, 1), ("â—€", 1, 0), ("â—", 1, 1), ("â–¶", 1, 2), ("â–¼", 2, 1)]:
            b = QPushButton(txt)
            b.setObjectName("ptzBtn")
            b.setFixedSize(34, 30)
            if txt == "â—":
                b.setToolTip("Centralizar (zoom 1x)")
                b.clicked.connect(self._reset_view)
            else:
                dx, dy = {"â–²": (0, -1), "â–¼": (0, 1), "â—€": (-1, 0), "â–¶": (1, 0)}[txt]
                b.setToolTip(f"Navegar {txt} (segurar repete)")
                self._wire_hold(b, lambda _=False, dx=dx, dy=dy: self._pan(dx, dy))
            grid.addWidget(b, r, c)
        lay.addLayout(grid)
        zrow = QHBoxLayout()
        zrow.setSpacing(3)
        self.btn_zin = QPushButton("+")
        self.btn_zin.setObjectName("ptzBtn")
        self.btn_zin.setFixedSize(34, 28)
        self.btn_zin.setToolTip("Aproximar")
        self._wire_hold(self.btn_zin, lambda _=False: self._zoom(1.25))
        self.btn_zout = QPushButton("âˆ’")
        self.btn_zout.setObjectName("ptzBtn")
        self.btn_zout.setFixedSize(34, 28)
        self.btn_zout.setToolTip("Afastar")
        self._wire_hold(self.btn_zout, lambda _=False: self._zoom(1 / 1.25))
        zrow.addWidget(self.btn_zin)
        zrow.addWidget(self.btn_zout)
        lay.addLayout(zrow)
        self.ptz_overlay = ov
        ov.hide()  # aparece no primeiro frame
        self._update_ptz_ui("")

    def _clamp_view(self):
        self.zoom = min(4.0, max(1.0, self.zoom))
        if self.zoom <= 1.0:
            self.cx, self.cy = 0.5, 0.5
            return
        mx = 0.5 - 0.5 / self.zoom
        my = 0.5 - (0.5 / self.zoom)
        self.cx = min(0.5 + mx, max(0.5 - mx, self.cx))
        self.cy = min(0.5 + my, max(0.5 - my, self.cy))

    def _pan(self, dx: int, dy: int):
        self.motor.move(dx, dy)
        if self.zoom <= 1.0:
            self.zoom = 2.0
            self._clamp_view()
            self._update_ptz_ui("+" if dy < 0 else ("â–²" if dy else ("â—€" if dx < 0 else "â–¶")))
            return
        step = 0.15 / self.zoom
        self.cx += dx * step
        self.cy += dy * step
        self._clamp_view()
        arrow = "â–²" if dy < 0 else ("â–¼" if dy > 0 else ("â—€" if dx < 0 else "â–¶"))
        self._update_ptz_ui(arrow)

    def _zoom(self, factor: float):
        self.motor.zoom_cmd(factor)
        self.zoom *= factor
        self._clamp_view()
        self._update_ptz_ui("+" if factor > 1 else "âˆ’")

    def _reset_view(self):
        self.motor.send("center", "zoom 1x")
        self.zoom, self.cx, self.cy = 1.0, 0.5, 0.5
        self._update_ptz_ui("â—")

    def _update_ptz_ui(self, last: str):
        if hasattr(self, "zoom_badge"):
            self.zoom_badge.setText(f"{self.zoom:.1f}x")
        hint = f"{self._mode} Â· UDP H.265"
        if self.zoom > 1.0:
            hint += f" Â· zoom {self.zoom:.1f}x â€” â—€â–²â–¼â–¶ navega, â— centraliza"
        if last:
            hint += f" Â· [{last}]"
        if hasattr(self, "hero_info"):
            self.hero_info.setText(hint)
        if hasattr(self, "fs") and self.fs.isVisible():
            self.fs.hint.setText(f"zoom {self.zoom:.1f}x Â· duplo-clique / Esc para sair")

    def _view_image(self, img: QImage) -> QImage:
        if self.zoom <= 1.0:
            return img
        w, h = img.width(), img.height()
        vw, vh = max(80, int(w / self.zoom)), max(45, int(h / self.zoom))
        x = min(max(int(self.cx * w) - vw // 2, 0), w - vw)
        y = min(max(int(self.cy * h) - vh // 2, 0), h - vh)
        return img.copy(x, y, vw, vh)

    # ---------- presets digitais ----------
    def _presets_path(self) -> str:
        try:
            from journal import appdata_dir
            return os.path.join(appdata_dir(), "ptz_presets.json")
        except Exception:
            return os.path.join(BASE, "ptz_presets.json")

    def _load_presets(self) -> dict:
        try:
            with open(self._presets_path(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_presets(self):
        try:
            with open(self._presets_path(), "w", encoding="utf-8") as f:
                json.dump(self.presets, f)
        except Exception:
            pass

    def _recall_preset(self, key: str):
        p = self.presets.get(key)
        if not p:
            self.lbl_info.setText(f"preset {key} vazio â€” ajuste a vista e salve com ðŸ’¾{key}")
            return
        self.zoom, self.cx, self.cy = float(p[0]), float(p[1]), float(p[2])
        self._clamp_view()
        self._update_ptz_ui(f"P{key}")
        self.motor.send(f"preset-{key}", f"zoom {self.zoom:.1f}x")

    def _store_preset(self, key: str):
        self.presets[key] = [round(self.zoom, 2), round(self.cx, 3), round(self.cy, 3)]
        self._save_presets()
        self.lbl_info.setText(f"preset {key} salvo (zoom {self.zoom:.1f}x)")
        self.store.log("Preset salvo", f"P{key}")
        self._refresh_preset_labels()

    def _refresh_preset_labels(self):
        for key, btn in getattr(self, "preset_btns", {}).items():
            btn.setText(f"P{key} Â· {self.presets[key][0]:.1f}x" if key in self.presets else f"P{key} Â· Livre")

    # ---------- overlay / fullscreen plumbing ----------
    def eventFilter(self, obj, event):
        if obj is getattr(self, "video", None) and event.type() == QEvent.MouseButtonDblClick:
            self._toggle_fs()
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_overlay()

    def _place_overlay(self):
        ov = getattr(self, "ptz_overlay", None)
        if ov is None or not hasattr(self, "video"):
            return
        ov.adjustSize()
        vw, vh = self.video.width(), self.video.height()
        if vw <= 0 or vh <= 0:
            return
        x = min(max(0, vw - ov.width() - 8), max(0, vw - ov.width()))
        y = min(max(0, vh - ov.height() - 8), max(0, vh - ov.height()))
        if ov.pos().x() != x or ov.pos().y() != y:
            ov.move(x, y)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and getattr(self, "fs", None) is not None and self.fs.isVisible():
            self.fs.hide()
        else:
            super().keyPressEvent(e)

    def _toggle_fs(self):
        if self.fs.isVisible():
            self.fs.hide()
        else:
            self.fs.showFullScreen()
            self._update_ptz_ui("")

    def build_control(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        sec = QLabel("ZOOM DIGITAL")
        sec.setObjectName("section")
        lay.addWidget(sec)
        box, bl = self.card()
        grid = QGridLayout()
        grid.setSpacing(8)
        self.ptz_btns = []
        for (txt, r, c, tip) in [("â–²", 0, 1, "Navegar para cima"), ("â—€", 1, 0, "Navegar para a esquerda"),
                                 ("â—", 1, 1, "Centralizar (zoom 1x)"), ("â–¶", 1, 2, "Navegar para a direita"),
                                 ("â–¼", 2, 1, "Navegar para baixo")]:
            b = QPushButton(txt)
            b.setObjectName("btn")
            b.setFixedSize(64, 40)
            b.setToolTip(f"{tip} â€” segurar repete")
            if txt == "â—":
                b.clicked.connect(self._reset_view)
            else:
                dx, dy = {"â–²": (0, -1), "â–¼": (0, 1), "â—€": (-1, 0), "â–¶": (1, 0)}[txt]
                self._wire_hold(b, lambda _=False, dx=dx, dy=dy: self._pan(dx, dy))
            grid.addWidget(b, r, c, Qt.AlignCenter)
            self.ptz_btns.append(b)
        bl.addLayout(grid)
        zrow = QHBoxLayout()
        self.btn_zin2 = QPushButton("+ Aproximar")
        self.btn_zin2.setObjectName("btn")
        self._wire_hold(self.btn_zin2, lambda _=False: self._zoom(1.25))
        self.btn_zout2 = QPushButton("âˆ’ Afastar")
        self.btn_zout2.setObjectName("btn")
        self._wire_hold(self.btn_zout2, lambda _=False: self._zoom(1 / 1.25))
        zrow.addWidget(self.btn_zin2)
        zrow.addWidget(self.btn_zout2)
        bl.addLayout(zrow)
        note = QLabel("Zoom digital na imagem (foto/gravaÃ§Ã£o usam a imagem cheia). Cada toque envia comando ao MotorDriver e aparece no log da Atividade â€” a lente sÃ³ move com driver CloudLink futuro (ver motor.py: ONVIF/HTTP/UDP esgotados).")
        note.setObjectName("info")
        note.setWordWrap(True)
        bl.addWidget(note)
        lay.addWidget(box)

        sec2 = QLabel("PRESETS")
        sec2.setObjectName("section")
        lay.addWidget(sec2)
        box2, bl2 = self.card()
        grid2 = QGridLayout()
        grid2.setSpacing(8)
        self.preset_btns = {}
        for i in range(1, 5):
            key = str(i)
            b = QPushButton(f"P{key} Â· Livre")
            b.setObjectName("btn")
            b.setToolTip(f"Abrir vista P{key}")
            b.clicked.connect(lambda _=False, k=key: self._recall_preset(k))
            grid2.addWidget(b, (i - 1) // 2, (i - 1) % 2)
            self.preset_btns[key] = b
        bl2.addLayout(grid2)
        srow = QHBoxLayout()
        slabel = QLabel("Salvar vista atual:")
        slabel.setObjectName("info")
        srow.addWidget(slabel)
        for i in range(1, 5):
            key = str(i)
            s = QPushButton(f"ðŸ’¾{key}")
            s.setObjectName("btn")
            s.setFixedSize(44, 28)
            s.setToolTip(f"Salvar zoom/posiÃ§Ã£o em P{key}")
            s.clicked.connect(lambda _=False, k=key: self._store_preset(k))
            srow.addWidget(s)
        bl2.addLayout(srow)
        lay.addWidget(box2)
        self._refresh_preset_labels()
        lay.addStretch(1)
        return page

    def build_gallery(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        sec = QLabel("GALERIA LOCAL")
        sec.setObjectName("section")
        lay.addWidget(sec)
        row = QHBoxLayout()
        self.gal_search = QLineEdit()
        self.gal_search.setPlaceholderText(f"Buscar em {len(self.store.photos)+len(self.store.videos)} arquivosâ€¦")
        self.gal_search.textChanged.connect(self.refresh_gallery_ui)
        self.btn_gal_refresh = QPushButton("â†»")
        self.btn_gal_refresh.setObjectName("btn")
        self.btn_gal_refresh.setFixedSize(40, 32)
        self.btn_gal_refresh.clicked.connect(lambda: (self.store.refresh_gallery(), self.refresh_gallery_ui()))
        row.addWidget(self.gal_search, 1)
        row.addWidget(self.btn_gal_refresh)
        lay.addLayout(row)
        self.gal_list = QListWidget()
        self.gal_list.itemDoubleClicked.connect(self.open_gallery_item)
        lay.addWidget(self.gal_list, 1)
        r2 = QHBoxLayout()
        self.gal_count = QLabel("")
        self.gal_count.setObjectName("info")
        self.btn_folder = QPushButton("ðŸ“ Pasta")
        self.btn_folder.setObjectName("btn")
        self.btn_folder.clicked.connect(lambda: os.startfile(BASE))
        r2.addWidget(self.gal_count, 1)
        r2.addWidget(self.btn_folder)
        lay.addLayout(r2)
        self.refresh_gallery_ui()
        return page

    def build_activity(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        sec = QLabel("ATIVIDADE")
        sec.setObjectName("section")
        lay.addWidget(sec)
        prow = QHBoxLayout()
        self.period_btns = []
        for label, days in [("Hoje", 1), ("7 dias", 7), ("30 dias", 30)]:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(days == 1)
            b.setObjectName("btnAccent" if days == 1 else "btn")
            b.clicked.connect(lambda _=False, d=days: self.set_period(d))
            prow.addWidget(b, 1)
            self.period_btns.append(b)
        lay.addLayout(prow)

        hero, hl = self.card()
        t = QLabel("TEMPO ONLINE")
        t.setObjectName("section")
        self.big_number = QLabel("0 s")
        self.big_number.setObjectName("bigNumber")
        self.act_sub = QLabel(" sessÃµes Â· fotos Â· vÃ­deos")
        self.act_sub.setObjectName("info")
        hl.addWidget(t)
        hl.addWidget(self.big_number)
        hl.addWidget(self.act_sub)
        lay.addWidget(hero)

        box, bl = self.card()
        self.act_stats = QLabel("")
        self.act_stats.setObjectName("info")
        self.act_stats.setWordWrap(True)
        bl.addWidget(self.act_stats)
        self.event_list = QListWidget()
        self.event_list.setMaximumHeight(190)
        bl.addWidget(self.event_list)
        r = QHBoxLayout()
        info = QLabel("HistÃ³rico local, sem nuvem.")
        info.setObjectName("info")
        self.btn_ev_clear = QPushButton("Limpar")
        self.btn_ev_clear.setObjectName("btn")
        self.btn_ev_clear.clicked.connect(self.clear_events)
        r.addWidget(info, 1)
        r.addWidget(self.btn_ev_clear)
        bl.addLayout(r)
        lay.addWidget(box, 1)
        self.refresh_activity()
        return page

    def build_settings(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        sec = QLabel("CONEXÃƒO")
        sec.setObjectName("section")
        lay.addWidget(sec)
        box, bl = self.card()
        form = QFormLayout()
        form.setSpacing(8)
        cam = self.store.cam
        self.e_nome = QLineEdit(cam.get("nome", ""))
        self.e_ip = QLineEdit(cam.get("ip", ""))
        self.e_user = QLineEdit(cam.get("user", "admin"))
        self.e_pass = QLineEdit(cam.get("password", ""))
        self.e_pass.setEchoMode(QLineEdit.Password)
        self.e_alta = QLineEdit(cam.get("path_alta", "/onvif1"))
        self.e_baixa = QLineEdit(cam.get("path_baixa", "/onvif2"))
        for label, w in [("Nome", self.e_nome), ("IP", self.e_ip), ("UsuÃ¡rio", self.e_user),
                         ("Senha RTSP", self.e_pass), ("Path HD", self.e_alta), ("Path SD", self.e_baixa)]:
            form.addRow(label, w)
        bl.addLayout(form)
        self.btn_save = QPushButton("Salvar e reconectar")
        self.btn_save.setObjectName("btnAccent")
        self.btn_save.clicked.connect(self.save_settings)
        bl.addWidget(self.btn_save)
        lay.addWidget(box)

        box2, bl2 = self.card()
        self.btn_disc = QPushButton("Procurar cÃ¢meras na rede")
        self.btn_disc.setObjectName("btn")
        self.btn_disc.clicked.connect(self.run_discovery)
        bl2.addWidget(self.btn_disc)
        self.disc_list = QListWidget()
        self.disc_list.setMaximumHeight(90)
        self.disc_list.itemClicked.connect(self.pick_discovery)
        bl2.addWidget(self.disc_list)
        note = QLabel("Mesmo Wi-Fi 2.4 GHz do PC. Varre portas 554/5000.")
        note.setObjectName("info")
        bl2.addWidget(note)
        lay.addWidget(box2)
        lay.addStretch(1)
        return page

    # ---------- comportamento ----------
    def wire_store(self):
        self.store.statusChanged.connect(self.on_status)
        self.store.statsChanged.connect(self.refresh_activity)
        self.store.galleryChanged.connect(self.refresh_gallery_ui)

    def set_tab(self, idx: int):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.tab_btns):
            b.setChecked(i == idx)
            b.setObjectName("tabBtnActive" if i == idx else "tabBtn")
            b.style().unpolish(b)
            b.style().polish(b)
        if idx == 3:
            self.refresh_activity()
        if idx == 2:
            self.store.refresh_gallery()

    def set_period(self, days: int):
        self.period_days = days
        for b, (_, d) in zip(self.period_btns, [("Hoje", 1), ("7 dias", 7), ("30 dias", 30)]):
            on = (d == days)
            b.setChecked(on)
            b.setObjectName("btnAccent" if on else "btn")
            b.style().unpolish(b)
            b.style().polish(b)
        self.refresh_activity()

    def refresh_theme(self, force=False):
        # Reparse de QSS inteiro congela a UI; so reaplica se o acento mudou.
        accent = accent_for(self.store.status, self.store.recording)
        if force or accent != self._accent:
            self._accent = accent
            self.setStyleSheet(build_stylesheet(accent))
        self.dot.setStyleSheet(f"color:{accent};")
        self.foot_dot.setStyleSheet(f"color:{accent};")

    def on_status(self, status: str):
        self.foot_status.setText(status)
        s = status.lower()
        if "vivo" in s or "gravando" in s:
            self.hero_badge.setText("â— GRAVANDO" if self.store.recording else "â— AO VIVO")
        elif "paus" in s:
            self.hero_badge.setText("PAUSADO")
        elif "erro" in s:
            self.hero_badge.setText("SEM SINAL")
        else:
            self.hero_badge.setText("CONECTANDO")
        self.refresh_theme()

    def on_tick(self):
        if self.store.recording:
            self.store.rec_secs += 1
            self.lbl_info.setText(f"â— gravando {self.store.rec_secs//60:02d}:{self.store.rec_secs%60:02d} â€” {os.path.basename(self.store.rec_file)}")
            if self._badge != "rec":
                self._badge = "rec"
                self.hero_badge.setText("â— GRAVANDO")
                self.refresh_theme()

    # ----- video/audio (reaproveita threads do widget.py) -----
    def start_video(self):
        if VideoThread is None:
            self.store.set_status("erro", "VideoThread indisponÃ­vel")
            return
        self.stop_video()
        self._frames_seen = 0
        self.store.set_status("conectandoâ€¦")
        url = rtsp_url(self.store.cam, self.store.low_quality)
        self.thread = VideoThread(url)
        self.thread.frame.connect(self.on_frame)
        self.thread.error.connect(self.on_error)
        self.thread.start()
        self.btn_play.setText("â¸ Pausar")
        self._watchdog.start(self.watchdog_s * 1000)

    def _do_retry(self):
        if self.store.status == "pausado":
            return
        self.store.log("Reconectar (auto)", f"tentativa {self._retries}/{self.retry_max}")
        self.start_video()

    def _on_watchdog(self):
        # ffmpeg pendurado sem frame nem erro: trata como erro p/ cair no retry
        if self._frames_seen == 0 and self.store.status == "conectandoâ€¦":
            self.on_error(f"tempo esgotado (sem frames em {self.watchdog_s}s)")

    @staticmethod
    def _stop_thread_nb(thread, timeout=400):
        # thread.stop() faz wait(2000) na thread da UI = congela. Mata o
        # processo e espera no maximo `timeout` ms.
        try:
            thread._run = False
            proc = getattr(thread, "proc", None)
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
            sink = getattr(thread, "sink", None)
            if sink:
                try:
                    sink.stop()
                except Exception:
                    pass
            thread.wait(timeout)
        except Exception:
            pass

    def stop_video(self):
        if self.thread:
            self._stop_thread_nb(self.thread)
            self.thread = None
        self._retry_timer.stop()
        self._watchdog.stop()

    def toggle_play(self):
        if self.thread:
            self.stop_video()
            self.btn_play.setText("â–¶ Retomar")
            self.store.set_status("pausado")
            self.hero_badge.setText("PAUSADO")
        else:
            self.start_video()

    def toggle_quality(self):
        self.store.low_quality = not self.store.low_quality
        self.btn_q.setText("SD" if not self.store.low_quality else "HD")
        self._mode = "onvif2 640x360" if self.store.low_quality else "onvif1 1920x1080"
        self.hero_quality.setText(f"{self._mode} Â· UDP")
        self._update_ptz_ui("")
        self.start_video()

    def on_frame(self, img: QImage):
        self.store.set_status("gravando" if self.store.recording else "ao vivo Â· UDP H.265")
        self._frames_seen += 1
        if self._frames_seen == 1:
            self._retries = 0
            self._retry_timer.stop()
            self._watchdog.stop()
            if hasattr(self, "ptz_overlay"):
                self.ptz_overlay.show()
        view = self._view_image(img)
        # Nao renderiza quando oculto ou em outra aba: era o maior custo/frame.
        if not self.isVisible() or self.stack.currentIndex() != 0:
            if self.fs.isVisible():
                self.fs.show_frame(view)
            return
        pix = QPixmap.fromImage(view).scaled(self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video.setPixmap(pix)
        self._place_overlay()
        if self.fs.isVisible():
            self.fs.show_frame(view)

    def on_error(self, msg: str):
        self._watchdog.stop()
        was_paused = (self.store.status == "pausado")
        self.store.set_status("erro", msg)
        self.video.setText(f"sem sinal\n{msg}\nverifique IP/senha/WiFi")
        self.store.log("Erro stream", msg[:160])
        if was_paused:
            self.store.set_status("pausado")
            return
        if self._retries < self.retry_max:
            self._retries += 1
            self.lbl_info.setText(f"{msg[:120]} â€” nova tentativa em {self.retry_delay}s ({self._retries}/{self.retry_max})")
            self._retry_timer.start(self.retry_delay * 1000)
        else:
            self.lbl_info.setText(f"{msg[:120]} â€” toque em Reconectar â»")

    def snapshot(self):
        if self._shot is not None and self._shot.isRunning():
            return
        url = rtsp_url(self.store.cam, self.store.low_quality)
        fn = os.path.join(BASE, f"foto_{datetime.datetime.now():%Y%m%d_%H%M%S}.jpg")
        self.btn_shot.setEnabled(False)
        self.lbl_info.setText("capturando fotoâ€¦")
        self._shot = SnapshotThread(url, fn)
        self._shot.done.connect(self._on_snapshot_done)
        self._shot.finished.connect(lambda: self.btn_shot.setEnabled(True))
        self._shot.start()

    def _on_snapshot_done(self, ok: bool, fn: str):
        self.btn_shot.setEnabled(True)
        if ok:
            self.lbl_info.setText(f"foto salva: {os.path.basename(fn)}")
            self.store.log("Foto", os.path.basename(fn))
            self.store.refresh_gallery()
        else:
            self.lbl_info.setText("falha na foto")

    def toggle_rec(self):
        if self.rec_proc:
            try:
                self.rec_proc.terminate()
                self.rec_proc.wait(timeout=3)
            except Exception:
                try:
                    self.rec_proc.kill()
                except Exception:
                    pass
            self.rec_proc = None
            self.store.recording = False
            self.btn_rec.setText("âº Gravar")
            self.btn_rec.setObjectName("btnDanger")
            self.btn_rec.style().unpolish(self.btn_rec)
            self.btn_rec.style().polish(self.btn_rec)
            self.lbl_info.setText(f"gravado: {os.path.basename(self.store.rec_file)}")
            self.store.log("GravaÃ§Ã£o parada", os.path.basename(self.store.rec_file))
            self.store.set_status("ao vivo Â· UDP H.265")
            self.store.refresh_gallery()
            return
        url = rtsp_url(self.store.cam, self.store.low_quality)
        self.store.rec_file = os.path.join(BASE, f"video_{datetime.datetime.now():%Y%m%d_%H%M%S}.mp4")
        self.rec_proc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-rtsp_transport", "udp",
                                          "-i", url, "-c", "copy", self.store.rec_file])
        self.store.recording = True
        self.store.rec_secs = 0
        self.btn_rec.setText("â¹ Parar")
        self.btn_rec.setObjectName("btnDangerRecording")
        self.btn_rec.style().unpolish(self.btn_rec)
        self.btn_rec.style().polish(self.btn_rec)
        self.store.log("GravaÃ§Ã£o iniciada", os.path.basename(self.store.rec_file))
        self.store.set_status("gravando")

    def toggle_sound(self):
        if self.audio:
            self._stop_thread_nb(self.audio)
            self.audio = None
            self.store.sound_on = False
            self.btn_sound.setText("ðŸ”‡ Ouvir")
            self.btn_sound.setChecked(False)
            self.audio_state.setText("mudo")
            return
        if not HAS_AUDIO or AudioThread is None:
            QMessageBox.warning(self, "Ãudio", "QtMultimedia nÃ£o disponÃ­vel.")
            self.btn_sound.setChecked(False)
            return
        url = rtsp_url(self.store.cam, self.store.low_quality)
        self.audio = AudioThread(url, volume=self.vol.value() / 100)
        self.audio.error.connect(lambda m: self.lbl_info.setText(f"Ã¡udio: {m}"))
        self.audio.start()
        self.store.sound_on = True
        self.btn_sound.setText("ðŸ”Š Ouvindo")
        self.btn_sound.setChecked(True)
        self.audio_state.setText("ouvindo PCMA 16k")

    def on_vol(self):
        if self.audio:
            try:
                self.audio.set_volume(self.vol.value() / 100)
            except Exception:
                pass

    def talk_info(self):
        QMessageBox.information(
            self, "Falar (autofalante)",
            "Sua cÃ¢mera declara via ONVIF: AudioSources=1, AudioOutputs=0.\n\n"
            "Ela manda Ã¡udio por RTSP, mas NÃƒO tem autofalante via LAN.\n"
            "O botÃ£o Falar do app Yoosee usa P2P proprietÃ¡rio.\n\n"
            "No painel dÃ¡ para ouvir e gravar com Ã¡udio.")

    # ----- galeria -----
    def refresh_gallery_ui(self):
        if not hasattr(self, "gal_list"):
            return
        q = (self.gal_search.text() if hasattr(self, "gal_search") else "").lower()
        self.gal_list.clear()
        items = ([("ðŸŽ¬ " + v["name"], v["path"]) for v in self.store.videos] +
                 [("ðŸ“· " + p["name"], p["path"]) for p in self.store.photos])
        n = 0
        for label, path in items:
            if q and q not in label.lower():
                continue
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, path)
            self.gal_list.addItem(it)
            n += 1
        self.gal_count.setText(f"{len(self.store.photos)} fotos Â· {len(self.store.videos)} vÃ­deos")
        if hasattr(self, "gal_search"):
            total = len(self.store.photos) + len(self.store.videos)
            self.gal_search.setPlaceholderText(f"Buscar em {total} arquivosâ€¦")

    def open_gallery_item(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except Exception as e:
                self.lbl_info.setText(f"nÃ£o abriu: {e}")

    # ----- atividade -----
    def refresh_activity(self):
        if not hasattr(self, "big_number"):
            return
        t = self.store.journal.totals(self.period_days)
        self.big_number.setText(duration_fmt(t["online"]))
        self.act_sub.setText(f"{t['sessions']} sessÃµes Â· {len(self.store.photos)} fotos Â· {len(self.store.videos)} vÃ­deos")
        t1 = self.store.journal.totals(1)["online"]
        t7 = self.store.journal.totals(7)["online"]
        t30 = self.store.journal.totals(30)["online"]
        self.act_stats.setText(
            f"Hoje {duration_fmt(t1)} Â· 7d {duration_fmt(t7)} Â· 30d {duration_fmt(t30)}\n"
            f"Status: {self.store.status}" + (f" Â· erro: {self.store.last_error[:120]}" if "erro" in self.store.status.lower() else ""))
        # Rebuild da lista e o custo; textos acima sao baratos e atualizam sempre.
        evs = self.store.events.events[:80]
        sig = (self.period_days, len(self.store.events.events),
               evs[0]["ts"] if evs else "", int(t["online"]))
        if sig == self._act_sig:
            return
        self._act_sig = sig
        self.event_list.clear()
        for ev in evs:
            self.event_list.addItem(f"{ev.get('ts','')} â€” {ev.get('title','')}: {ev.get('detail','')[:100]}")

    def clear_events(self):
        self.store.events.clear()
        self.refresh_activity()

    # ----- ajustes -----
    def save_settings(self):
        cam = dict(self.store.cam)
        cam.update(nome=self.e_nome.text(), ip=self.e_ip.text(), user=self.e_user.text(),
                   password=self.e_pass.text(), path_alta=self.e_alta.text(), path_baixa=self.e_baixa.text())
        self.store.save_cam(cam)
        self.title.setText(cam.get("nome", "Yoosee"))
        self.start_video()
        self.set_tab(0)

    def run_discovery(self):
        base_ip = self.e_ip.text().strip() or self.store.cam.get("ip", "192.168.1.100")
        self.btn_disc.setEnabled(False)
        self.btn_disc.setText("Procurandoâ€¦")
        self.disc_list.clear()
        self.disc = DiscoveryThread(base_ip)
        self.disc.found.connect(lambda ip: self.disc_list.addItem(ip))
        self.disc.done.connect(self.on_disc_done)
        self.disc.start()

    def on_disc_done(self, achou: list):
        self.btn_disc.setEnabled(True)
        self.btn_disc.setText("Procurar cÃ¢meras na rede")
        if not achou:
            self.disc_list.addItem("Nada achado â€” mesmo Wi-Fi 2.4 GHz?")
        self.store.log("Discovery", f"{len(achou)} host(s): {', '.join(achou[:5])}")

    def pick_discovery(self, item: QListWidgetItem):
        ip = item.text().strip()
        if ip and ip[0].isdigit():
            self.e_ip.setText(ip)

    # ----- header/menu -----
    def open_menu(self):
        m = QMenu(self)
        a_re = QAction("Reconectar", self)
        a_re.triggered.connect(self.reconnect)
        a_folder = QAction("Abrir pasta", self)
        a_folder.triggered.connect(lambda: os.startfile(BASE))
        a_hide = QAction("Ocultar painel", self)
        a_hide.triggered.connect(self.hide)
        m.addAction(a_re)
        m.addAction(a_folder)
        m.addSeparator()
        m.addAction(a_hide)
        m.exec(self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomLeft()))

    def reconnect(self):
        self._retries = 0
        self.store.log("Reconectar", self.store.cam.get("ip", ""))
        self.start_video()

    # ----- frameless drag + toggle -----
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def toggle_near(self, pos=None):
        if self.isVisible():
            self.hide()
            return
        screen = QApplication.primaryScreen().availableGeometry()
        x = min(max((pos.x() if pos else screen.right() - PANEL_W - 16) - PANEL_W // 2, screen.left() + 8),
                screen.right() - PANEL_W - 8)
        y = max(screen.bottom() - self.height() - 48, screen.top() + 8)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def close_app(self):
        try:
            if self.rec_proc:
                self.rec_proc.terminate()
        except Exception:
            pass
        if self.audio:
            self._stop_thread_nb(self.audio)
            self.audio = None
        self.stop_video()
        if getattr(self, "fs", None) is not None:
            self.fs.hide()
        self.store.journal.pause()
        self.store.journal.save()
        self.close()
