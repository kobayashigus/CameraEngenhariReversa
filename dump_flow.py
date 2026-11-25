"""Extrai payloads do fluxo telefone<->camera: clusters + timeline. So estrutura."""
import struct
import sys
from collections import Counter

F = sys.argv[1] if len(sys.argv) > 1 else "PCAPdroid_13_out_21_16_11.pcap"
raw = open(F, "rb").read()
off = 24
pkts = []
while off + 16 <= len(raw):
    ts_s, ts_u, cap, _ = struct.unpack("<IIII", raw[off:off + 16])
    off += 16
    pkts.append((ts_s + ts_u / 1e6, raw[off:off + cap]))
    off += cap

CAM = "192.168.1.100"
flow = []
for ts, data in pkts:
    ip = data  # linktype 101 = raw
    if len(ip) < 20 or (ip[0] >> 4) != 4 or ip[9] != 17:
        continue
    ihl = (ip[0] & 0xF) * 4
    src = ".".join(map(str, ip[12:16]))
    dst = ".".join(map(str, ip[16:20]))
    seg = ip[ihl:]
    sp, dp = struct.unpack(">HH", seg[:4])
    if CAM not in (src, dst):
        continue
    d = ">>" if dst == CAM else "<<"
    flow.append((ts, d, sp, dp, seg[8:]))
t0 = flow[0][0]
print(f"pacotes no fluxo: {len(flow)}")

# cluster por (dir, len, prefixo16)
clus = Counter()
ex = {}
for ts, d, sp, dp, pl in flow:
    k = (d, len(pl), pl[:16].hex())
    clus[k] += 1
    ex.setdefault(k, pl)
print("\n-- clusters (dir, len, prefixo, count) --")
for k, n in clus.most_common(30):
    print(f"  {k[0]} len={k[1]:4d} n={n:4d} {k[2][:48]}")

# timeline dos pequenos (<70B) vindos do telefone: candidatos a comando
print("\n-- timeline pequenos telefone->camera --")
for ts, d, sp, dp, pl in flow:
    if d == ">>" and len(pl) <= 70:
        print(f"  t={ts-t0:6.2f}s len={len(pl):3d} {pl.hex()}")
