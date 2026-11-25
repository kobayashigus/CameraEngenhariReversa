"""Replay experimental: reenvia pacotes b780 (candidatos a comando) e mede
movimento via snapshots. Seguro: so pacotes 30B de evento, nada de config."""
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.parse

import cv2
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"
CAM = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))["cameras"][0]


def rtsp():
    pwd = urllib.parse.quote(CAM["password"], safe="")
    return f'rtsp://{CAM["user"]}:{pwd}@{CAM["ip"]}:{CAM["rtsp_port"]}{CAM["path_alta"]}'


def snap(path):
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-rtsp_transport", "udp",
                        "-i", rtsp(), "-frames:v", "1", path],
                       timeout=25)
    return r.returncode == 0


def diff(a, b):
    ia = cv2.imread(a, cv2.IMREAD_GRAYSCALE)
    ib = cv2.imread(b, cv2.IMREAD_GRAYSCALE)
    if ia is None or ib is None or ia.shape != ib.shape:
        return -1.0
    ia = cv2.resize(ia, (320, 180))
    ib = cv2.resize(ib, (320, 180))
    return float(np.mean(cv2.absdiff(ia.astype(np.int16), ib.astype(np.int16))))


def load_burst(pcap, t_lo=15.5, t_hi=17.6):
    raw = open(pcap, "rb").read()
    off = 24
    t0 = None
    pkts = []
    while off + 16 <= len(raw):
        ts_s, ts_u, cap, _ = struct.unpack("<IIII", raw[off:off + 16])
        off += 16
        data = raw[off:off + cap]
        off += cap
        pkts.append((ts_s + ts_u / 1e6, data))
    # t0 = primeiro pacote envolvendo a camera (igual dump_flow.py)
    for ts, data in pkts:
        ip = data
        if len(ip) >= 20 and (ip[0] >> 4) == 4:
            s = ".".join(map(str, ip[12:16]))
            d = ".".join(map(str, ip[16:20]))
            if CAM["ip"] in (s, d):
                t0 = ts
                break
    out = []
    for ts_abs, data in pkts:
        ts = ts_abs - t0
        if not (t_lo <= ts <= t_hi):
            continue
        ip = data
        if len(ip) < 20 or ip[9] != 17:
            continue
        ihl = (ip[0] & 0xF) * 4
        if ".".join(map(str, ip[16:20])) != CAM["ip"]:
            continue
        seg = ip[ihl:]
        pl = seg[8:]
        if len(pl) == 30 and pl[6:10] == bytes.fromhex("4469b780"):
            out.append(pl)
    # unicos preservando ordem
    uniq = list(dict.fromkeys(out))
    return uniq


def send(payloads, rounds=4, gap=0.2):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for _ in range(rounds):
        for pl in payloads:
            try:
                s.sendto(pl, (CAM["ip"], 32859))
            except Exception as e:
                print("send err", e)
            time.sleep(gap)
    s.close()


def main():
    pcap = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(BASE), "PCAPdroid_13_out_21_16_11.pcap")
    cands = load_burst(pcap)
    print(f"candidatos b780 na rajada: {len(cands)}")
    if not cands:
        print("sem candidatos")
        return
    a1 = os.path.join(BASE, ".replay_a1.jpg")
    a2 = os.path.join(BASE, ".replay_a2.jpg")
    b = os.path.join(BASE, ".replay_b.jpg")
    print("baseline snap1...", flush=True)
    snap(a1)
    time.sleep(2)
    print("baseline snap2...", flush=True)
    snap(a2)
    base = diff(a1, a2)
    print(f"ruido-base (sem comando): {base:.2f}")
    print(f"enviando {len(cands)} pacotes x4 para {CAM['ip']}:32859...", flush=True)
    send(cands)
    print("snap pos-comando...", flush=True)
    snap(b)
    d = diff(a2, b)
    print(f"diff pos-comando: {d:.2f} (base {base:.2f})")
    if base >= 0 and d > max(3 * base, base + 6):
        print("VEREDITO: MOVEU (diff muito acima do ruido)")
    else:
        print("VEREDITO: nao moveu (sessao provavelmente exigida)")
    for f in (a1, a2, b):
        try:
            os.remove(f)
        except OSError:
            pass


if __name__ == "__main__":
    main()
