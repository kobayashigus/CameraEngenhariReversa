"""Probe ONVIF PTZ: descobre se a camera aceita mover (ContinuousMove) ou e fixa.
Uso: python ptz_probe.py  (le config.json; nunca imprime a senha)
"""
import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import sys

try:
    import requests
except ImportError:
    print("ERRO: pip install requests")
    sys.exit(1)

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
    CAM = json.load(f)["cameras"][0]

IP, PORT, USER, PWD = CAM["ip"], CAM.get("onvif_port", 5000), CAM["user"], CAM["password"]


def envelope(body: str) -> bytes:
    nonce = secrets.token_bytes(16)
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + PWD.encode()).digest()).decode()
    return (
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        '<s:Header><Security xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        "<UsernameToken>"
        f"<Username>{USER}</Username>"
        '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{digest}</Password>"
        '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{base64.b64encode(nonce).decode()}</Nonce>"
        '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        f"{created}</Created></UsernameToken></Security></s:Header>"
        f"<s:Body>{body}</s:Body></s:Envelope>"
    ).encode()


def post(path: str, body: str, timeout: int = 8) -> str:
    url = f"http://{IP}:{PORT}{path}"
    r = requests.post(url, data=envelope(body),
                      headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                      timeout=timeout)
    return r.text


def main():
    print(f"== {CAM['nome']} {IP}:{PORT} ==")
    caps = post("/onvif/device_service",
                '<tds:GetCapabilities xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
                "<tds:Category>All</tds:Category></tds:GetCapabilities>")
    has_ptz = "PTZ" in caps and "XAddr" in caps
    print("PTZ mencionado em capabilities:", "PTZ" in caps)
    xaddrs: dict[str, str] = {}
    for ns, addr in re.findall(r"<tds:Namespace>([^<]+)</tds:Namespace>\s*<tds:XAddr>([^<]+)</tds:XAddr>", caps):
        key = "ptz" if "/ptz" in ns else ("media" if "/media" in ns else ("device" if "/device" in ns else ns))
        xaddrs[key] = addr
        print("service:", key, "->", addr)

    def path_of(key: str, default: str) -> str:
        addr = xaddrs.get(key, "")
        if addr and f"{IP}:{PORT}" in addr:
            return "/" + addr.split(f"{IP}:{PORT}")[-1].lstrip("/")
        return default

    media_path = path_of("media", "/onvif/media_service")
    print("media path:", media_path)
    try:
        profs = post(media_path,
                     '<trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl"/>')
        tokens = re.findall(r'<trt:Profiles[^>]*token="([^"]+)"', profs)
        names = re.findall(r"<tt:Name>([^<]+)</tt:Name>", profs)
        ptz_conf = re.findall(r"<tt:PTZConfiguration[^>]*token=\"([^\"]+)\"", profs)
        print("profiles:", list(zip(tokens, names))[:6])
        print("PTZConfiguration nos profiles:", ptz_conf or "NENHUM")
    except Exception as e:
        print("GetProfiles ERRO:", repr(e)[:200])
        return

    ptz_path = path_of("ptz", "/onvif/ptz_service")
    print("ptz path:", ptz_path)
    nodes_ok = False
    for ns in ("http://www.onvif.org/ver20/ptz/wsdl", "http://www.onvif.org/ver10/ptz/wsdl"):
        try:
            nodes = post(ptz_path, f'<tptz:GetNodes xmlns:tptz="{ns}"/>')
            if "GetNodesResponse" in nodes or "PTZNode" in nodes:
                print(f"PTZ nodes ({ns.split('/')[-2]}):",
                      re.findall(r"<tt:Name>([^<]+)</tt:Name>", nodes)[:4] or "NENHUM")
                print("ContinuousMove suportado:", "Continuous" in nodes)
                nodes_ok = True
                break
            print(f"resposta inesperada em {ns.split('/')[-2]}: {nodes[:160]!r}")
        except Exception as e:
            print(f"GetNodes {ns.split('/')[-2]} ERRO:", repr(e)[:160])
    if not nodes_ok:
        print("PTZ GetNodes: sem resposta valida nos paths testados")
    for fallback in ("/onvif/device_service", "/onvif/media_service"):
        if nodes_ok or fallback == ptz_path:
            continue
        try:
            nodes = post(fallback,
                         '<tptz:GetNodes xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl"/>')
            print(f"fallback {fallback}: {len(nodes)} bytes, nodes:",
                  re.findall(r"<tt:Name>([^<]+)</tt:Name>", nodes)[:4] or "NENHUM")
            if "GetNodesResponse" in nodes or "PTZNode" in nodes:
                nodes_ok = True
        except Exception as e:
            print(f"fallback {fallback} ERRO:", repr(e)[:160])
    print("PTZ funcional:", "SIM" if nodes_ok else "NAO (anuncia mas nao responde)")

    print("== FIM ==")


if __name__ == "__main__":
    main()
