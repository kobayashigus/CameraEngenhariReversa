"""Timeline correta: flag=payload[9], subtipo=payload[16]."""
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

p30 = []
for t, d in pk:
    ip = d
    if len(ip) < 20 or (ip[0] >> 4) != 4 or ip[9] != 17:
        continue
    ihl = (ip[0] & 0xF) * 4
    if ".".join(map(str, ip[16:20])) != "192.168.1.100":
        continue
    pl = ip[ihl + 8:]
    if pl[:4] == bytes.fromhex("c0100603") and len(pl) == 30:
        p30.append((t - t0, pl))

print(f"30B: {len(p30)}, flag00={sum(1 for _,p in p30 if p[9]==0)} flag80={sum(1 for _,p in p30 if p[9]==0x80)}")
print("sess3:", Counter(p[6:9].hex() for _, p in p30))
print("\n-- flag80: t, subtipo, seq --")
for ts, pl in p30:
    if pl[9] == 0x80:
        print(f"  t={ts:6.2f}s sub=0x{pl[16]:02x} seq=0x{pl[14:16].hex()} nonce={pl[4:6].hex()}")
