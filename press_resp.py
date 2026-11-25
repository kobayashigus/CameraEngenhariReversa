"""Pre-janela (press?) + respostas da camera (telemetria?) por janela."""
import struct
import sys

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

ev = []
for t, d in pk:
    ip = d
    if len(ip) < 20 or (ip[0] >> 4) != 4 or ip[9] != 17:
        continue
    ihl = (ip[0] & 0xF) * 4
    s = ".".join(map(str, ip[12:16]))
    dst = ".".join(map(str, ip[16:20]))
    if "192.168.1.100" not in (s, dst):
        continue
    ev.append((t - t0, "<<" if s == "192.168.1.100" else ">>", ip[ihl + 8:]))

print("-- 1.5s antes de cada janela (press?) --")
for lo in (8.5, 20.0):
    print(f" [t {lo}-{lo+1.5}]")
    for ts, dr, pl in ev:
        if lo <= ts <= lo + 1.5 and dr == ">>":
            print(f"  t={ts:6.2f}s len={len(pl):4d} {pl[:40].hex()}")
print("\n-- respostas << durante janelas (telemetria?) --")
for lo, hi in ((10.0, 13.4), (21.4, 24.7)):
    print(f" [t {lo}-{hi}]")
    for ts, dr, pl in ev:
        if lo <= ts <= hi and dr == "<<":
            print(f"  t={ts:6.2f}s len={len(pl):4d} {pl.hex()[:96]}")
