"""Yoosee Widget Windows - single cam, moderno, ffmpeg UDP H.265 + audio."""
import json, os, shutil, subprocess, sys, urllib.parse, datetime
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QByteArray
from PySide6.QtGui import QImage, QPixmap, QAction
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox,
    QCheckBox, QFileDialog, QSlider)
try:
    from PySide6.QtMultimedia import QAudioSink, QAudioFormat, QAudio
    HAS_AUDIO = True
except Exception:
    HAS_AUDIO = False

BASE = os.path.dirname(__file__)
CONFIG = os.path.join(BASE, "config.json")
FFMPEG = shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"
W, H = 960, 540  # saida fixa do ffmpeg para o widget (leve)

def load_cam():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)["cameras"][0]

def save_cam(cam):
    with open(CONFIG, encoding="utf-8") as f:
        data = json.load(f)
    data["cameras"][0] = cam
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def rtsp_url(cam, baixa=False):
    pwd = urllib.parse.quote(cam["password"], safe="")
    path = cam["path_baixa"] if baixa else cam["path_alta"]
    return f'rtsp://{cam["user"]}:{pwd}@{cam["ip"]}:{cam["rtsp_port"]}{path}'

class VideoThread(QThread):
    frame = Signal(QImage)
    error = Signal(str)
    def __init__(self, url):
        super().__init__()
        self.url = url
        self._run = True
        self.proc = None
    def run(self):
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error",
               "-rtsp_transport", "udp", "-i", self.url,
               "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-vf", f"scale={W}:{H}", "-"]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            self.error.emit(str(e)); return
        size = W * H * 3
        while self._run:
            raw = self.proc.stdout.read(size) if self.proc.stdout else b""
            if len(raw) != size:
                if not self._run: break
                err = b""
                try: err = self.proc.stderr.read1(1024) if hasattr(self.proc.stderr, "read1") else b""
                except Exception: pass
                self.error.emit(err.decode(errors="ignore")[:300] or "stream cortado - verifique WiFi/IP/senha")
                break
            img = QImage(raw, W, H, W*3, QImage.Format_BGR888).copy()
            self.frame.emit(img)
    def stop(self):
        self._run = False
        try:
            if self.proc: self.proc.kill()
        except Exception: pass
        self.wait(2000)

class AudioThread(QThread):
    error = Signal(str)
    def __init__(self, url, volume=0.8):
        super().__init__()
        self.url = url
        self._run = True
        self.proc = None
        self.sink = None
        self.io = None
        self.volume = volume
    def run(self):
        if not HAS_AUDIO:
            self.error.emit("QtMultimedia ausente"); return
        fmt = QAudioFormat()
        fmt.setSampleRate(16000); fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        self.sink = QAudioSink(fmt)
        self.sink.setVolume(self.volume)
        self.io = self.sink.start()
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error",
               "-rtsp_transport", "udp", "-i", self.url,
               "-vn", "-f", "s16le", "-acodec", "pcm_s16le",
               "-ar", "16000", "-ac", "1", "-"]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            self.error.emit(str(e)); return
        while self._run:
            data = self.proc.stdout.read(4096) if self.proc.stdout else b""
            if not data:
                if not self._run: break
                self.error.emit("audio cortado"); break
            try:
                self.io.write(data)
            except Exception:
                break
    def set_volume(self, v):
        self.volume = v
        if self.sink: self.sink.setVolume(v)
    def stop(self):
        self._run = False
        try:
            if self.proc: self.proc.kill()
        except Exception: pass
        try:
            if self.sink: self.sink.stop()
        except Exception: pass
        self.wait(2000)

class SettingsDialog(QDialog):
    def __init__(self, cam, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar câmera")
        self.cam = dict(cam)
        lay = QFormLayout(self)
        self.e_nome = QLineEdit(cam["nome"]); self.e_ip = QLineEdit(cam["ip"])
        self.e_user = QLineEdit(cam["user"]); self.e_pass = QLineEdit(cam["password"])
        self.e_pass.setEchoMode(QLineEdit.Password)
        self.e_alta = QLineEdit(cam["path_alta"]); self.e_baixa = QLineEdit(cam["path_baixa"])
        for k, w in [("Nome", self.e_nome), ("IP", self.e_ip), ("Usuário", self.e_user),
                     ("Senha RTSP", self.e_pass), ("Path HD", self.e_alta), ("Path SD", self.e_baixa)]:
            lay.addRow(k, w)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay.addWidget(btns)
    def result_cam(self):
        c = dict(self.cam)
        c.update(nome=self.e_nome.text(), ip=self.e_ip.text(), user=self.e_user.text(),
                 password=self.e_pass.text(), path_alta=self.e_alta.text(), path_baixa=self.e_baixa.text())
        return c

class Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.cam = load_cam()
        self.thread = None
        self.audio = None
        self.sound_on = False
        self.rec_proc = None
        self.rec_file = ""
        self.baixa = False
        self.setWindowTitle("Yoosee Widget")
        self.setMinimumSize(500, 560)
        self.resize(520, 620)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag = None
        self.build_ui()
        self.apply_style()
        self.start_video()

    def build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(14, 14, 14, 14); root.setSpacing(10)
        card = QWidget(); card.setObjectName("card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 14, 14, 14); lay.setSpacing(10)

        top = QHBoxLayout()
        self.dot = QLabel("●"); self.dot.setObjectName("dot_ok")
        self.title = QLabel(self.cam["nome"]); self.title.setObjectName("title")
        self.status = QLabel("conectando…"); self.status.setObjectName("status")
        top.addWidget(self.dot); top.addWidget(self.title, 1); top.addWidget(self.status)
        self.btn_pin = QPushButton("📌"); self.btn_pin.setCheckable(True); self.btn_pin.setChecked(True)
        self.btn_pin.setFixedSize(34, 30); self.btn_pin.clicked.connect(self.toggle_pin)
        self.btn_min = QPushButton("—"); self.btn_min.setFixedSize(34, 30); self.btn_min.clicked.connect(self.showMinimized)
        self.btn_x = QPushButton("✕"); self.btn_x.setFixedSize(34, 30); self.btn_x.clicked.connect(self.close_app)
        for b in (self.btn_pin, self.btn_min, self.btn_x):
            b.setObjectName("ghost")
        top.addWidget(self.btn_pin); top.addWidget(self.btn_min); top.addWidget(self.btn_x)
        lay.addLayout(top)

        self.video = QLabel("aguardando vídeo…"); self.video.setObjectName("video")
        self.video.setMinimumSize(QSize(472, 265)); self.video.setAlignment(Qt.AlignCenter)
        self.video.setScaledContents(False)
        lay.addWidget(self.video)

        row = QHBoxLayout()
        self.btn_play = QPushButton("⏸ Pausar"); self.btn_play.clicked.connect(self.toggle_play)
        self.btn_q = QPushButton("SD"); self.btn_q.clicked.connect(self.toggle_quality)
        self.btn_shot = QPushButton("📷 Foto"); self.btn_shot.clicked.connect(self.snapshot)
        self.btn_rec = QPushButton("⏺ Gravar"); self.btn_rec.clicked.connect(self.toggle_rec)
        self.btn_cfg = QPushButton("⚙"); self.btn_cfg.setFixedSize(40, 34); self.btn_cfg.clicked.connect(self.open_settings)
        for b in (self.btn_play, self.btn_q, self.btn_shot, self.btn_rec, self.btn_cfg):
            b.setObjectName("btn")
        self.btn_rec.setObjectName("btn_rec")
        row.addWidget(self.btn_play); row.addWidget(self.btn_q); row.addWidget(self.btn_shot)
        row.addWidget(self.btn_rec); row.addWidget(self.btn_cfg)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        self.btn_sound = QPushButton("🔇 Ouvir"); self.btn_sound.setCheckable(True)
        self.btn_sound.clicked.connect(self.toggle_sound)
        self.vol = QSlider(Qt.Horizontal); self.vol.setRange(0, 100); self.vol.setValue(80)
        self.vol.valueChanged.connect(self.on_vol)
        self.btn_talk = QPushButton("🎤 Falar"); self.btn_talk.clicked.connect(self.talk_info)
        for b in (self.btn_sound, self.btn_talk):
            b.setObjectName("btn")
        self.vol.setObjectName("vol")
        self.vol.setFixedWidth(120)
        row2.addWidget(self.btn_sound); row2.addWidget(self.vol, 1); row2.addWidget(self.btn_talk)
        lay.addLayout(row2)

        bot = QHBoxLayout()
        self.lbl_info = QLabel(""); self.lbl_info.setObjectName("info")
        self.btn_folder = QPushButton("📁 Pasta"); self.btn_folder.setObjectName("ghost2")
        self.btn_folder.clicked.connect(lambda: os.startfile(BASE))
        bot.addWidget(self.lbl_info, 1); bot.addWidget(self.btn_folder)
        lay.addLayout(bot)

        root.addWidget(card)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick_rec); self.rec_secs = 0

    def apply_style(self):
        self.setStyleSheet("""
        QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #e8ecf1; }
        #card { background: #141821; border: 1px solid #2a3342; border-radius: 18px; }
        #title { font-size: 15px; font-weight: 700; }
        #status { color: #9aa7b8; font-size: 12px; }
        #dot_ok { color: #35d07f; font-size: 16px; }
        #dot_err { color: #ff5470; font-size: 16px; }
        #video { background: #000; border-radius: 12px; border: 1px solid #262f3d; }
        #btn { background: #1e2532; border: 1px solid #2d3748; border-radius: 10px; padding: 8px 10px; }
        #btn:hover { background: #28324a; }
        #btn_rec { background: #2a1d22; border: 1px solid #5a2b35; border-radius: 10px; padding: 8px 10px; }
        #btn_rec:on, #btn_rec:checked { background: #a1253a; }
        #ghost, #ghost2 { background: transparent; border: none; color: #9aa7b8; border-radius: 8px; }
        #ghost:hover, #ghost2:hover { background: #232c3d; color: white; }
        #info { color: #8b98ab; font-size: 11px; }
        #vol { max-height: 20px; }
        QDialog { background: #141821; }
        QLineEdit { background: #0f131b; border: 1px solid #2d3748; border-radius: 8px; padding: 6px; }
        """)

    # janela arrastavel (widget sem borda)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag = e.globalPosition().toPoint() - self.pos()
    def mouseMoveEvent(self, e):
        if self._drag is not None: self.move(e.globalPosition().toPoint() - self._drag)
    def mouseReleaseEvent(self, e): self._drag = None

    def toggle_pin(self):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.btn_pin.isChecked())
        self.show()

    def start_video(self):
        self.stop_video()
        url = rtsp_url(self.cam, self.baixa)
        self.status.setText("conectando…")
        self.thread = VideoThread(url)
        self.thread.frame.connect(self.on_frame)
        self.thread.error.connect(self.on_error)
        self.thread.start()
        self.btn_play.setText("⏸ Pausar")

    def stop_video(self):
        if self.thread:
            self.thread.stop(); self.thread = None

    def toggle_play(self):
        if self.thread: self.stop_video(); self.btn_play.setText("▶ Retomar"); self.status.setText("pausado")
        else: self.start_video()

    def toggle_quality(self):
        self.baixa = not self.baixa
        self.btn_q.setText("SD" if not self.baixa else "HD")
        self.start_video()
        self.lbl_info.setText(f"{'onvif2 640x360' if self.baixa else 'onvif1 1920x1080'} · UDP H.265")

    def on_frame(self, img):
        self.status.setText("ao vivo · UDP H.265")
        self.dot.setObjectName("dot_ok"); self.dot.setStyleSheet("")
        pix = QPixmap.fromImage(img).scaled(self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video.setPixmap(pix)

    def on_error(self, msg):
        self.status.setText("erro")
        self.dot.setObjectName("dot_err"); self.dot.setStyleSheet("color:#ff5470;font-size:16px;")
        self.video.setText(f"sem sinal\n{msg}\nverifique IP/senha/WiFi")
        self.lbl_info.setText(msg[:120])

    def snapshot(self):
        url = rtsp_url(self.cam, self.baixa)
        fn = os.path.join(BASE, f"foto_{datetime.datetime.now():%Y%m%d_%H%M%S}.jpg")
        r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-rtsp_transport", "udp",
                            "-i", url, "-frames:v", "1", fn])
        self.lbl_info.setText(f"foto salva: {os.path.basename(fn)}" if r.returncode == 0 else "falha na foto")

    def toggle_rec(self):
        if self.rec_proc:
            self.rec_proc.terminate()
            try: self.rec_proc.wait(timeout=3)
            except Exception: self.rec_proc.kill()
            self.rec_proc = None; self.timer.stop()
            self.btn_rec.setText("⏺ Gravar"); self.lbl_info.setText(f"gravado: {os.path.basename(self.rec_file)}")
            return
        url = rtsp_url(self.cam, self.baixa)
        self.rec_file = os.path.join(BASE, f"video_{datetime.datetime.now():%Y%m%d_%H%M%S}.mp4")
        self.rec_proc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-rtsp_transport", "udp",
                                          "-i", url, "-c", "copy", self.rec_file])
        self.rec_secs = 0; self.timer.start(1000)
        self.btn_rec.setText("⏹ Parar")

    def tick_rec(self):
        self.rec_secs += 1
        self.lbl_info.setText(f"● gravando {self.rec_secs//60:02d}:{self.rec_secs%60:02d} — {os.path.basename(self.rec_file)}")

    def open_settings(self):
        d = SettingsDialog(self.cam, self)
        if d.exec():
            self.cam = d.result_cam(); save_cam(self.cam)
            self.title.setText(self.cam["nome"]); self.start_video()

    def toggle_sound(self):
        if not HAS_AUDIO:
            QMessageBox.warning(self, "Áudio", "QtMultimedia não disponível.")
            self.btn_sound.setChecked(False); return
        if self.sound_on:
            self.stop_sound()
        else:
            url = rtsp_url(self.cam, self.baixa)
            self.audio = AudioThread(url, volume=self.vol.value()/100)
            self.audio.error.connect(lambda m: self.lbl_info.setText(f"áudio: {m}"))
            self.audio.start()
            self.sound_on = True
            self.btn_sound.setText("🔊 Ouvindo"); self.btn_sound.setChecked(True)
            self.lbl_info.setText("ouvindo microfone da câmera (PCMA 16k)…")

    def stop_sound(self):
        if self.audio: self.audio.stop(); self.audio = None
        self.sound_on = False
        self.btn_sound.setText("🔇 Ouvir"); self.btn_sound.setChecked(False)

    def on_vol(self):
        if self.audio: self.audio.set_volume(self.vol.value()/100)

    def talk_info(self):
        QMessageBox.information(self, "Falar (autofalante)",
            "Sua câmera declara via ONVIF: AudioSources=1, AudioOutputs=0.\n\n"
            "Ou seja: ela manda áudio (microfone) por RTSP, mas NÃO tem autofalante via ONVIF/RTSP.\n"
            "O botão Falar do app Yoosee usa P2P proprietário (nStartIntercom / GwMonitorPlayer),\n"
            "não o RTSP aberto. Só portas 554 e 5000 abertas, sem canal de voz LAN.\n\n"
            "Para falar, continue usando o app Yoosee. No widget dá para ouvir e gravar com áudio.")

    def close_app(self):
        if self.rec_proc:
            try: self.rec_proc.terminate()
            except Exception: pass
        self.stop_sound()
        self.stop_video(); self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Widget(); w.show()
    sys.exit(app.exec())
