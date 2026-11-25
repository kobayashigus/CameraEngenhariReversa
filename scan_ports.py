"""Scan TCP direcionado na camera. Uso: python scan_ports.py [--ip X]"""
import socket
import sys
from concurrent.futures import ThreadPoolExecutor

IP = "192.168.1.100"
for a in sys.argv:
    if a.startswith("--ip"):
        IP = a.split("=", 1)[-1] if "=" in a else sys.argv[sys.argv.index(a) + 1]

PORTS = [21, 22, 23, 25, 53, 80, 81, 82, 111, 135, 139, 443, 445, 554,
         800, 8000, 8001, 8010, 8080, 8081, 8443, 8554, 8800, 8888, 8899,
         8999, 9000, 5000, 5001, 5050, 5060, 5678, 6789, 7000, 9876,
         10554, 15961, 23456, 34567, 37777]


def probe(p):
    try:
        s = socket.create_connection((IP, p), timeout=1.2)
        try:
            s.settimeout(1.0)
            banner = s.recv(256)
        except Exception:
            banner = b""
        s.close()
        return (p, banner[:80])
    except Exception:
        return None


with ThreadPoolExecutor(max_workers=20) as e:
    found = sorted([x for x in e.map(probe, PORTS) if x])
print("IP:", IP)
for p, banner in found:
    print(f"  ABERTA {p} banner={banner!r}")
if not found:
    print("  nada aberto na lista")
