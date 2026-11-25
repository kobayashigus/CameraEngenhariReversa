"""Minera strings do APK Yoosee atras de protocolo PTZ/controle (sem dessenhar tudo).
Uso: python apk_mine.py [--full]
"""
import re
import sys
import zipfile

APK = "Yoosee_6.36.apk"
KEYS = [b"ptz", b"preset", b"pelco", b"cruise", b"motor", b"openapi",
        b"/cgi-bin", b"/web/", b"moveup", b"movedown", b"moveleft", b"moveright",
        b"startptz", b"stopptz", b"ptzcontrol", b"setptz", b"getptz", b"gopreset",
        b"avioctrl", b"iotc", b"tutk", b"ppcs", b"p2p", b"moto", b"Motor", b"Moto",
        b"CMD_", b"Cmd", b"IOCtrl", b"Ctrl", b"nStart", b"SendCmd", b"DevCmd",
        b"cloudlinks", b"gwell", b"ipc_", b"IPC_", b"json",
        b"yiot", b"p2pav", b"gwmonitor", b"intercom", b"jfh", b"xm", b"hi3510",
        b"port 81", b":81/", b":8080", b"Nat", b"upnp",
        b"http://", b"deviceid", b"devid"]
STR = re.compile(rb"[ -~]{6,180}")


def main(full=False):
    z = zipfile.ZipFile(APK)
    dexes = [n for n in z.namelist() if n.endswith(".dex")]
    sos = [n for n in z.namelist() if n.endswith(".so")]
    print(f"dex: {len(dexes)}  so: {[n.split('/')[-1] for n in sos][:20]}")
    hits: dict[bytes, set[bytes]] = {}
    for name in dexes:
        data = z.read(name)
        for m in STR.finditer(data):
            s = m.group(0)
            low = s.lower()
            for k in KEYS:
                if k in low:
                    # filtra lixo obvio
                    if s.count(b"/") > 8 or len(set(s)) < 5:
                        continue
                    hits.setdefault(k, set()).add(s)
                    break
    interesting = [b"ptz", b"preset", b"pelco", b"cruise", b"motor", b"openapi",
                   b"/cgi-bin", b"/web/", b"moveup", b"movedown", b"moveleft",
                   b"moveright", b"startptz", b"stopptz", b"ptzcontrol", b"setptz",
                   b"getptz", b"gopreset", b"avioctrl", b"iotc", b"tutk", b"ppcs",
                   b"p2p", b"moto", b"Motor", b"Moto", b"CMD_", b"Cmd", b"IOCtrl",
                   b"Ctrl", b"nStart", b"SendCmd", b"DevCmd", b"cloudlinks",
                   b"gwell"]
    for k in interesting:
        vals = sorted(hits.get(k, set()))[:60 if full else 25]
        print(f"\n### {k.decode()} ({len(hits.get(k, set()))})")
        for v in vals:
            try:
                print("  ", v.decode())
            except Exception:
                pass

    # --- nativas (.so): e onde mora o P2P proprietario ---
    focus = [b"motor", b"Motor", b"Moto", b"multi_motor_go", b"CMD_", b"IOCtrl",
             b"PTZ", b"Ptz", b"cloudlinks", b"gwell", b"AVIOCTL", b"avSendIOCtrl",
             b"nStart", b"sendCmd", b"presets", b"cruise"]
    print("\n=== .so ===")
    for name in sos:
        if "/x86" in name or "/x86_64" in name:
            continue
        if "arm64" not in name and "arm" not in name and "armeabi" not in name:
            continue
        try:
            data = z.read(name)
        except Exception:
            continue
        if len(data) > 60_000_000:
            continue
        got: set[bytes] = set()
        for m in STR.finditer(data):
            s = m.group(0)
            for k in focus:
                if k in s:
                    if len(s) > 120 or s.count(b" ") > 6:
                        continue
                    got.add(s)
                    break
        if got:
            short = name.split("/")[-1]
            print(f"\n--- {short} ({len(data)//1024}KB, {len(got)} hits)")
            for v in sorted(got)[:40]:
                try:
                    print("   ", v.decode())
                except Exception:
                    pass


if __name__ == "__main__":
    main("--full" in sys.argv)
