"""Motor da camera: abstracao p/ comandos de movimento.

Situacao (verificado em 2026-10-13, ver ptz_probe.py / apk_mine.py / mine_out.txt):
- ONVIF PTZ: a camera anuncia, mas /onvif/ptz_service derruba a conexao. MORTO.
- HTTP/CGI local: so as portas TCP 554/5000 abertas. MORTO.
- UDP: nenhuma porta de controle responde. MORTO.
- Unico caminho real: Gwell CloudLink P2P (libp2pav.so: handshake TCP_HELPER +
  KCP + canal JSON camKz*, ex: camKzPtzPos). Exige handshake com a nuvem
  (www.gwell.cc) + cripto — RE profunda (Frida/MITM), nao e replay simples.

Por isso o D-pad hoje move a VISTA (zoom digital) e REGISTRA cada comando,
para quando o driver CloudLink existir ele plugar aqui sem mexer na UI.
"""
from __future__ import annotations
import struct
import time


class MotorDriver:
    name = "digital"
    can_move_lens = False  # True so quando houver driver CloudLink validado

    def __init__(self, log=None):
        self._log = log or (lambda t, d: None)
        self._last_key = ""
        self._last_ts = 0.0

    def send(self, action: str, detail: str = "") -> bool:
        """Registra o comando (throttle 2s por acao). Retorna se a lente moveu."""
        now = time.monotonic()
        key = f"{action}|{detail}"
        if key != self._last_key or now - self._last_ts > 2.0:
            self._last_key, self._last_ts = key, now
            suffix = "" if self.can_move_lens else " (lente sem canal — preview digital)"
            self._log(f"Motor {action}", f"{detail}{suffix}")
        return self.can_move_lens

    def move(self, dx: int, dy: int) -> bool:
        arrow = "up" if dy < 0 else ("down" if dy > 0 else ("left" if dx < 0 else "right"))
        return self.send(arrow, f"dx={dx} dy={dy}")

    def zoom_cmd(self, factor: float) -> bool:
        return self.send("zoom", f"x{factor:.2f}")

    def preset_cmd(self, key: str) -> bool:
        return self.send(f"preset-{key}", "")

    def stop(self):
        self._last_key = ""


class CloudLinkDriver(MotorDriver):
    """Driver REAL (Gwell CloudLink UDP 32859) — AINDA NAO VALIDADO.

    Evidencia (PCAPdroid_13_out_21_26_31.pcap, captura ANOTADA up->left):
    - STEP 91B @5Hz durante hold: MAGIC c010030b, canal 0x83, contador global
      (cluster1 steps 1-17, cluster2 steps 18-34), corpo cifrado.
    - DIRECAO em bytes[64:66]: cluster1(UP)=0x6710, cluster2(LEFT)=0x3333
      (constante intra-cluster, resto do bloco [66:80] e cauda [80:91] iguais).
      Modelo: JSON cifrado (ECB-like) com bloco de seq variando por pacote.
    - NONCE bytes[4:6] sempre unico; SESS3 por sessao (385efc aqui).
    - replay de sessao morta e IGNORADO (replay_test.py).
      Falta: handshake (gera SESS3) + chave do corpo. UI continua no digital.

    NAO ligar na UI até mover a lente de verdade em teste.
    """

    name = "cloudlink"
    can_move_lens = False
    PORT = 32859
    MAGIC = bytes.fromhex("c0100603")
    CONST4 = bytes.fromhex("52000001")
    # Direcao = bytes[64:66] do STEP 91B (up primeiro na captura anotada).
    # Ainda HIPOTESE (aguarda teste em sessao viva). down/right desconhecidos.
    DIR_FIELD = {"up": bytes.fromhex("6710"), "down": None,
                 "left": bytes.fromhex("3333"), "right": None}
    DIR_BYTE = {"up": 0x41, "down": 0x41, "left": 0x42, "right": 0x42}  # legado 30B

    def __init__(self, ip: str, session3: bytes = bytes.fromhex("4469b7"), log=None):
        super().__init__(log=log)
        self.ip = ip
        self.session3 = session3

    def build(self, subtype: int, nonce: bytes | None = None, seq: int = 1,
              ctr: bytes = bytes(13), event: bool = True) -> bytes:
        import secrets
        nonce = nonce if nonce is not None else secrets.token_bytes(2)
        tail = bytes([subtype]) + bytes(ctr[:13]).ljust(13, b"\x00")
        assert len(tail) == 14
        pkt = (self.MAGIC + nonce + self.session3 + bytes([0x80 if event else 0x00])
               + self.CONST4 + struct.pack(">H", seq & 0xFFFF) + tail)
        assert len(pkt) == 30, len(pkt)
        return pkt

    @staticmethod
    def parse(payload: bytes) -> dict:
        assert len(payload) == 30, len(payload)
        return {"magic": payload[0:4].hex(), "nonce": payload[4:6].hex(),
                "session3": payload[6:9].hex(), "flag": payload[9],
                "const4": payload[10:14].hex(),
                "seq": struct.unpack(">H", payload[14:16])[0],
                "subtype": payload[16], "ctr": payload[17:].hex()}

    def send_raw(self, payload: bytes):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.sendto(payload, (self.ip, self.PORT))
        finally:
            s.close()
