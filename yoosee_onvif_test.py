"""Diagnostico Yoosee ONVIF/RTSP - Windows
Uso: python yoosee_onvif_test.py --ip 192.168.1.XX --user admin --password SUA_SENHA_RTSP
A senha RTSP e criada em: app Yoosee > Settings > RTSP Settings > Enable RTSP(with password)
"""
import argparse, socket, subprocess, sys, shutil, urllib.parse

FFPROBE = shutil.which("ffprobe") or r"C:\ffmpeg\bin\ffprobe.exe"

RTSP_PATHS = [
    "/onvif1", "/onvif2",
    "/live/ch00_0", "/live/ch00_1",
    "/live/ch0", "/live/0",
    "/11", "/12",
    "/ucast/11", "/ucast/12",
    "/h264", "/mpeg4",
    "/", "",
]

ONVIF_PORTS = [80, 5000, 8080, 8888]
RTSP_PORTS = [554, 8554]

def tcp_open(ip, port, timeout=2):
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False

def try_ffprobe(url):
    cmd = [FFPROBE, "-v", "error", "-rtsp_transport", "udp",
           "-timeout", "8000000", "-show_streams", "-of", "default=noprint_wrappers=1", url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        out = (p.stdout or "") + (p.stderr or "")
        ok = "codec_name" in (p.stdout or "")
        return ok, out.strip()[:1500], p.returncode
    except subprocess.TimeoutExpired:
        return False, "timeout 15s", -1
    except Exception as e:
        return False, str(e), -1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="")
    ap.add_argument("--port", type=int, default=554)
    args = ap.parse_args()

    ip = args.ip
    print(f"[1/3] Testando portas TCP em {ip} ...")
    for port in RTSP_PORTS + ONVIF_PORTS:
        st = "ABERTA" if tcp_open(ip, port) else "fechada"
        print(f"  porta {port}: {st}")
    if not tcp_open(ip, args.port):
        print(f"\nERRO: porta RTSP {args.port} fechada. Causas: camera em outro WiFi/rede, AP isolation no roteador, RTSP desligado no app, ou IP errado.")
        print("Confirme IP no app Yoosee ou no roteador e que PC e camera estao no mesmo WiFi 2.4GHz.")
        # continua mesmo assim

    print(f"\n[2/3] Testando ONVIF HTTP (GetCapabilities) ...")
    import urllib.request
    for oport in ONVIF_PORTS:
        if tcp_open(ip, oport, timeout=1):
            url = f"http://{ip}:{oport}/onvif/device_service"
            print(f"  {url} responde TCP, teste no ODM com porta {oport}")

    print(f"\n[3/3] Testando RTSP via ffprobe UDP (user={args.user}) ...")
    found = False
    pwd_enc = urllib.parse.quote(args.password, safe="")
    for path in RTSP_PATHS:
        if args.password:
            url = f"rtsp://{args.user}:{pwd_enc}@{ip}:{args.port}{path}"
            logurl = f"rtsp://{args.user}:***@{ip}:{args.port}{path}"
        else:
            url = f"rtsp://{ip}:{args.port}{path}"
            logurl = url
        ok, out, rc = try_ffprobe(url)
        status = "OK <-- FUNCIONOU" if ok else f"falhou rc={rc}"
        print(f"  {logurl} -> {status}")
        if out and not ok:
            # mostra so primeira linha do erro pra nao poluir
            first = out.splitlines()[0] if out.splitlines() else out
            print(f"      detalhe: {first[:300]}")
        if ok:
            print(out[:2000])
            found = True
            # nao para, mostra todas que funcionam
    if not found:
        print("\nNenhuma URL abriu. Me mande esse log completo + o comando ffmpeg que voce usou.")
        print("Erros comuns: 401 = senha RTSP errada, 404 = path errado, timeout = porta bloqueada/RTSP desligado.")
    else:
        print("\nUse a URL marcada OK no VLC > Open Network Stream ou no NVR.")

if __name__ == "__main__":
    sys.exit(main())
