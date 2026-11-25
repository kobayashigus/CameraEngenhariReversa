"""Isola rajadas de evento (b780) com timestamps na captura nova."""
import struct
import sys
from collections import Counter

F = sys.argv[1] if len(sys.argv) > 1 else "PCAPdroid_13_out_21_26_31.pcap"
raw = open(F, "rb").read()
off = 24
pk = []
while off + 16 <= len(raw):
    ts, tu, cap, _ = struct.unpack("<IIII", raw[off:off + 16])
    off += 16
    pk.append((ts + tu / 1e6, raw[off:off + cap]))
    off += cap
t0 = next(t for t, d in pk if len(d) >= 20 and (d[0] >> 4) == 4
          and "192.168.1.100" in (".".join(map(str, d[12:16])), ".".join(map(str, d[16:20]))))

ev30, fam7e = [], []
for t, d in pk:
    ip = d
    if len(ip) < 20 or (ip[0] >> 4) != 4 or ip[9] != 17:
        continue
    ihl = (ip[0] & 0xF) * 4
    if ".".join(map(str, ip[16:20])) != "192.168.1.100":
        continue
    pl = ip[ihl + 8:]
    ts = t - t0
    if pl[:4] == bytes.fromhex("c0100603") and len(pl) == 30:
        ev30.append((ts, pl.hex()))
    elif pl[:2] == bytes.fromhex("7eba") or pl[:2] == bytes.fromhex("7eb9"):
        fam7e.append((ts, len(pl), pl[:8].hex()))

print(f"pacotes 30B c010: {len(ev30)}")
sess = Counter(p[12:20] for _, p in ev30)
print("sessoes 30B:", dict(sess))
flags = Counter(p[20:24] for _, p in ev30)
print("flags b7xx:", dict(flags))
print("\n-- SESSAO (bytes6-9) ao longo do tempo --")
cur, tcur = None, None
for ts, p in ev30:
    if p[12:20] != cur:
        print(f"  t={ts:6.2f}s sess={p[12:20]}")
        cur = p[12:20]
print("\n-- rajadas b780 (t, byte16, seq) --")
for ts, p in ev30:
    if p[20:24] == "b780":
        print(f"  t={ts:6.2f}s tipo={p[32:34]} seq={p[28:32]} {p[:24]}...")
print(f"\n-- familia 7e (n={len(fam7e)}) primeiras --")
for ts, ln, pre in fam7e[:14]:
    print(f"  t={ts:6.2f}s len={ln} {pre}")
