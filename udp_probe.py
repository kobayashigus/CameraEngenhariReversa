"""Probe UDP na camera (porta fechada responde ICMP refused no Windows).
Uso: python udp_probe.py [--ip X]
"""
import socket
import sys

IP = "192.168.1.100"
for a in sys.argv:
    if a.startswith("--ip"):
        IP = a.split("=", 1)[-1] if "=" in a else sys.argv[sys.argv.index(a) + 1]

PORTS = [3702, 5000, 5050, 5060, 5678, 6789, 8000, 8080, 8554, 8666,
         9000, 9999, 10000, 15000, 15500, 15961, 16000, 20000, 30000,
         34567, 45555, 5353, 1900]

PAYLOADS = {
    1900: b"M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\nMAN:\"ns:discover\"\r\nMX:1\r\nST:upnp:rootdevice\r\n\r\n",
    5353: b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00",
}


def probe(p):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.5)
    try:
        s.sendto(PAYLOADS.get(p, b"\x00\x01\x02\x03"), (IP, p))
        data, _ = s.recvfrom(2048)
        return (p, f"RESPONDEU {len(data)}B {data[:60]!r}")
    except socket.timeout:
        return (p, "timeout (filtrada/aberta sem resposta)")
    except ConnectionResetError:
        return (p, "refused (fechada)")
    except OSError as e:
        return (p, f"oserr {e.winerror if hasattr(e, 'winerror') else e}")
    finally:
        s.close()


print("IP:", IP)
for p in PORTS:
    port, verdict = probe(p)
    print(f"  udp {port}: {verdict}")
