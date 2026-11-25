"""Teste em sessao viva: discovery + replay UP (bytes reais do pcap).
Uso: python replay_live.py
"""
import os
import socket
import struct
import time

IP = "192.168.1.100"
PORT = 32859
BASE = os.path.dirname(os.path.abspath(__file__))
PCAP = os.path.join(os.path.dirname(BASE), "PCAPdroid_13_out_21_26_31.pcap")


def load_steps(n=17):
    """Primeiros n STEP c010030b do pcap (cluster UP, em ordem)."""
    raw = open(PCAP, "rb").read()
    off = 24
    pk = []
    while off + 16 <= len(raw):
        ts, tu, cap, _ = struct.unpack("<IIII", raw[off:off + 16])
        off += 16
        pk.append((ts + tu / 1e6, raw[off:off + cap]))
        off += cap
    t0 = next(t for t, d in pk if len(d) >= 20 and (d[0] >> 4) == 4
              and IP in (".".join(map(str, d[12:16])), ".".join(map(str, d[16:20]))))
    out = []
    for t, d in pk:
        ip = d
        if len(ip) < 20 or (ip[0] >> 4) != 4 or ip[9] != 17:
            continue
        ihl = (ip[0] & 0xF) * 4
        if ".".join(map(str, ip[16:20])) != IP:
            continue
        pl = ip[ihl + 8:]
        if pl[:4] == bytes.fromhex("c010030b"):
            out.append(pl)
            if len(out) == n:
                break
    return out


def main():
    print("1) discovery 8899...", flush=True)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(3)
    try:
        s.sendto(b"Discovery", ("255.255.255.255", 8899))
        t0 = time.time()
        while time.time() - t0 < 3:
            try:
                data, addr = s.recvfrom(2048)
                print(f"   resposta {addr}: {len(data)}B {data[:60]!r}", flush=True)
            except socket.timeout:
                break
    except Exception as e:
        print("   discovery err:", e, flush=True)
    finally:
        s.close()

    ups = load_steps()
    print(f"2) enviando rajada {len(ups)}x UP @5Hz (equivale segurar 3s)...", flush=True)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i, pl in enumerate(ups):
        s.sendto(pl, (IP, PORT))
        if i < 3 or i >= len(ups) - 1:
            print(f"   up-{i + 1} enviado {len(pl)}B", flush=True)
        time.sleep(0.2)
    s.close()
    print("RAJADA ENVIADA. Verifique a camera agora.", flush=True)


if __name__ == "__main__":
    main()
