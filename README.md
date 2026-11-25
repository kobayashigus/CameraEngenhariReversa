# CameraEngenhariReversa

Estudo de engenharia reversa da câmera IP **Yoosee 6.36** (app Android) e um app alternativo para uso na rede local, sem depender da nuvem do fabricante.

## O que tem aqui

| Caminho | Descrição |
|---|---|
| `yoosee_custom_app/` | App desktop (PySide6) para ver o stream RTSP, gravar, tirar snapshot e controlar a câmera na LAN |
| `apk_mine.py` / `mine_out.txt` | Mineração de strings do APK em busca do protocolo de controle/PTZ |
| `analyze_pcap.py`, `dump_flow.py`, `burst*.py`, `press_resp.py` | Análise dos fluxos de rede capturados com o PCAPdroid |
| `scan_ports.py`, `udp_probe.py`, `yoosee_onvif_test.py` | Sondas de portas, RTSP, ONVIF e UDP |

## Como rodar o app

```powershell
cd yoosee_custom_app
pip install -r requirements.txt

copy config.example.json config.json
# edite config.json com o IP e a senha RTSP da sua câmera

python main.py --list
python main.py --view 0
```

Painel com bandeja do sistema:

```powershell
python tray_app.py --standalone
```

## Observações

- O APK original (195 MB) e as capturas `.pcap` **não** foram incluídos neste repositório.
- Credenciais e IPs reais foram removidos. `config.json` está no `.gitignore`; use `config.example.json` como modelo.
- A senha RTSP é habilitada no app oficial em *Settings → RTSP Settings → Enable RTSP (with password)*.
- Projeto de estudo. Não é afiliado à Yoosee.
