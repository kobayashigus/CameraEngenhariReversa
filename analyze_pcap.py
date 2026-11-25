"""Analisa pcap do PCAPdroid: fluxos, DNS/SNI, rajadas p/ camera. So metadados."""
import struct
import sys
from collections import Counter, defaultdict

F = sys.argv[1] if len(sys.argv) > 1 else "PCAPdroid_13_out_21_16_11.pcap"
raw = open(F, "rb").read()
magic, ver_maj, ver_min, _, _, snap, net = struct.unpack("<IHHIIII", raw[:24])
print(f"magic ok, linktype={net}, bytes={len(raw)}")
off = 24
pkts = []
while off + 16 <= len(raw):
    ts_s, ts_u, cap, ln = struct.unpack("<IIII", raw[off:off + 16])
    off += 16
    data = raw[off:off + cap]
    off += cap
    if len(data) < cap:
        break
    pkts.append((ts_s + ts_u / 1e6, data))
print(f"pacotes: {len(pkts)}, duracao: {pkts[-1][0]-pkts[0][0]:.1f}s" if pkts else "vazio")


def parse(data):
    if net == 1:  # ethernet
        if len(data) < 14 or struct.unpack(">H", data[12:14])[0] != 0x0800:
            return None
        ip = data[14:]
    elif net == 101:  # raw IP (PCAPdroid padrao)
        ip = data
    else:
        return None
    if len(ip) < 20 or (ip[0] >> 4) != 4:
        return None
    ihl = (ip[0] & 0xF) * 4
    proto, src, dst = ip[9], ".".join(map(str, ip[12:16])), ".".join(map(str, ip[16:20]))
    seg = ip[ihl:]
    if proto == 6 and len(seg) >= 4:
        return ("tcp", src, dst, struct.unpack(">HH", seg[:4]), len(seg), seg)
    if proto == 17 and len(seg) >= 4:
        return ("udp", src, dst, struct.unpack(">HH", seg[:4]), len(seg), seg)
    return (f"ip-{proto}", src, dst, (0, 0), len(seg), seg)


flows = Counter()
talkers = Counter()
dns, sni = [], []
udp_cam, tcp_cam = [], []
t0 = pkts[0][0]
for ts, data in pkts:
    p = parse(data)
    if not p:
        continue
    kind, src, dst, (sp, dp), ln, seg = p
    flows[(kind, src, sp, dst, dp)] += 1
    talkers[(dst, dp)] += 1
    if dst.startswith("192.168.1.") or src.startswith("192.168.1."):
        (udp_cam if kind == "udp" else tcp_cam).append((ts - t0, src, sp, dst, dp, ln))
    if kind == "udp" and (sp == 53 or dp == 53) and len(seg) > 12:
        try:
            q = seg[8:]
            name, i = "", 0
            while q[i] != 0 and i < len(q):
                n = q[i]
                name += q[i + 1:i + 1 + n].decode() + "."
                i += 1 + n
            dns.append(name)
        except Exception:
            pass
    if kind == "tcp" and len(seg) > 40 and seg[20:21] == b"\x16" and b"\x00\x00" in seg[20:30]:
        try:
            i = seg.find(b"\x00\x00", 20)
            ln2 = struct.unpack(">H", seg[i + 2:i + 4])[0]
            sni.append(seg[i + 4:i + 4 + ln2].decode())
        except Exception:
            pass

print("\n-- top destinos --")
for (dst, dp), n in talkers.most_common(15):
    print(f"  {dst}:{dp} x{n}")
print("\n-- DNS --")
for d in dict.fromkeys(dns):
    print("  ", d)
print("\n-- SNI --")
for s in dict.fromkeys(sni):
    print("  ", s)
print(f"\n-- pacotes p/ 192.168.1.x: udp={len(udp_cam)} tcp={len(tcp_cam)} --")
seen = defaultdict(int)
for ts, src, sp, dst, dp, ln in (udp_cam + tcp_cam)[:10] + (udp_cam + tcp_cam)[-5:]:
    print(f"  t={ts:7.1f}s {src}:{sp} -> {dst}:{dp} len={ln}")
print("\n-- fluxos UDP p/ camera (contagem e tamanhos) --")
agg = defaultdict(list)
for ts, src, sp, dst, dp, ln in udp_cam:
    agg[(src, sp, dst, dp)].append((ts, ln))
for k, v in agg.items():
    lens = sorted(set(ln for _, ln in v))
    print(f"  {k[0]}:{k[1]} -> {k[2]}:{k[3]} n={len(v)} tamanhos={lens[:12]} tspan={v[-1][0]-v[0][0]:.1f}s")
