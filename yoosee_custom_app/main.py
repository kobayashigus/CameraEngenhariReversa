"""App base Yoosee LAN - viewer + gravacao + snapshot.
Uso:
  python main.py --list
  python main.py --view 0
  python main.py --view 0 --baixa
  python main.py --record 0 --segundos 30 --saida video.mp4
  python main.py --snapshot 0 --saida foto.jpg
  python main.py --discover
Nao usa nuvem Yoosee, so RTSP/ONVIF local (verificado via engenharia reversa).
Requer: ffmpeg + ffprobe no PATH (voce ja tem em C:\\ffmpeg\\bin).
"""
import argparse, json, socket, subprocess, shutil, sys, urllib.parse, os

FFMPEG = shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"
FFPROBE = shutil.which("ffprobe") or r"C:\ffmpeg\bin\ffprobe.exe"
FFPLAY = shutil.which("ffplay") or r"C:\ffmpeg\bin\ffplay.exe"
CONFIG = os.path.join(os.path.dirname(__file__), "config.json")

def load():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)["cameras"]

def rtsp_url(cam, baixa=False):
    pwd = urllib.parse.quote(cam["password"], safe="")
    path = cam["path_baixa"] if baixa else cam["path_alta"]
    return f'rtsp://{cam["user"]}:{pwd}@{cam["ip"]}:{cam["rtsp_port"]}{path}'

def cmd_list():
    for i, c in enumerate(load()):
        print(f"[{i}] {c['nome']} {c['ip']}:{c['rtsp_port']} user={c['user']} onvif={c['onvif_port']}")

def cmd_discover(timeout=1.5):
    # varre 192.168.1.1-254 procurando 554/5000 abertas (ajuste rede se preciso)
    base = ".".join(load()[0]["ip"].split(".")[:3]) if load() else "192.168.1"
    print(f"Procurando cameras em {base}.0/24 (554/5000)...")
    achou = []
    for i in range(1, 255):
        ip = f"{base}.{i}"
        for p in (554, 5000):
            try:
                s = socket.create_connection((ip, p), timeout=0.3)
                s.close()
                if ip not in achou:
                    print(f"  {ip} porta {p} aberta")
                    achou.append(ip)
                break
            except Exception:
                pass
    if not achou:
        print("Nada achado. Confira se PC e camera estao no mesmo WiFi 2.4GHz.")
    return achou

def cmd_view(idx, baixa=False):
    cam = load()[idx]
    url = rtsp_url(cam, baixa)
    print(f"Abrindo {cam['nome']} {'(baixa)' if baixa else '(alta)'} via {cam['transport']}...")
    print(url.replace(cam["password"], "***"))
    # ffplay entende H.265 + UDP que o ODM nao entende
    subprocess.run([FFPLAY, "-rtsp_transport", cam["transport"], "-i", url])

def cmd_record(idx, segundos, saida):
    cam = load()[idx]
    url = rtsp_url(cam)
    print(f"Gravando {segundos}s em {saida} ...")
    subprocess.run([FFMPEG, "-y", "-rtsp_transport", cam["transport"],
                    "-i", url, "-c", "copy", "-t", str(segundos), saida])

def cmd_snapshot(idx, saida):
    cam = load()[idx]
    url = rtsp_url(cam)
    print(f"Snapshot em {saida} ...")
    subprocess.run([FFMPEG, "-y", "-rtsp_transport", cam["transport"],
                    "-i", url, "-frames:v", "1", saida])

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--view", type=int, default=None)
    ap.add_argument("--baixa", action="store_true")
    ap.add_argument("--record", type=int, default=None)
    ap.add_argument("--segundos", type=int, default=30)
    ap.add_argument("--saida", default="saida.mp4")
    ap.add_argument("--snapshot", type=int, default=None)
    a = ap.parse_args()
    if a.list: cmd_list()
    elif a.discover: cmd_discover()
    elif a.view is not None: cmd_view(a.view, a.baixa)
    elif a.record is not None: cmd_record(a.record, a.segundos, a.saida)
    elif a.snapshot is not None: cmd_snapshot(a.snapshot, a.saida)
    else: ap.print_help()
