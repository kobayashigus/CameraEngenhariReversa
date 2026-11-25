# Yoosee Custom App (base LAN)

Base prÃ³pria, sem nuvem Yoosee. Usa o que foi revertido do `Yoosee_6.36.apk`.

## O que a reversa provou
- Observado em `resources.arsc`: RTSP/ONVIF sÃ³ na mesma LAN, precisa `Enable RTSP(with password)`.
- Observado em `classes4.dex`: campos `rtspEnable, onvifEn, rtspPwd, setRTSPpwd`.
- Observado ao vivo via `ffprobe -rtsp_transport udp rtsp://admin:***@192.168.1.100:554/onvif1`: `Video hevc 1920x1080 + Audio pcm_alaw`, `onvif2`: `640x360 hevc`. Portas `554` e `5000` abertas, `TCP` recusado (`Nonmatching transport`), sÃ³ `UDP`.
- Observado em todos `classes*.dex`: `PTZ, Preset, Alarm, Playback, /openapi/app/user/device/preset/*, /vas/playback/*` â€” dÃ¡ para expandir depois via ONVIF PTZ e HTTP.
- InferÃªncia: ODM sem vÃ­deo = sem decodificador H.265, nÃ£o Ã© falta de sinal.
- Desconhecido: protocolo P2P nuvem (`libiotvideomulti.so`, `libp2pav.so`, `libgwplayer.so`). NÃ£o precisa para app LAN.

## Rodar
```powershell
python .\yoosee_custom_app\main.py --list
python .\yoosee_custom_app\main.py --view 0
python .\yoosee_custom_app\main.py --record 0 --segundos 30 --saida video.mp4
python .\yoosee_custom_app\main.py --snapshot 0 --saida foto.jpg
```

Edite `config.json` para trocar IP/senha. Senha com `@` Ã© auto-encoded (`%40`).

## Painel tray (estilo LGwebOS-menubar, single-cam)
```powershell
python .\yoosee_custom_app\tray_app.py --standalone   # janela solta
python .\yoosee_custom_app\tray_app.py                # tray + popover (clique no Ã­cone)
# ou
.\yoosee_custom_app\run_panel.bat
```
- `theme.py`: tokens dark + acento verde dinÃ¢mico (live `#35d07f`, gravando `#ff5470`, conectando `#ffa62b`).
- `store.py`: estado Ãºnico (status/gravaÃ§Ã£o/galeria) + `set_status` sem spam de sinal.
- `journal.py`: `usage.json` (tempo online) + `events.json` em `%APPDATA%\YooseeWidget`, sem senha/nuvem.
- `panel.py`: 5 tabs â€” Ao Vivo (overlay D-pad digital + â›¶ fullscreen) / Controle (zoom/pan + presets digitais) / Galeria / Atividade / Ajustes.
- `ptz_probe.py`: prova que a cÃ¢mera anuncia PTZ mas o serviÃ§o `/onvif/ptz_service` derruba a conexÃ£o â€” por isso o D-pad Ã© zoom digital (foto/gravaÃ§Ã£o sempre full).
- `motor.py`: todo toque no D-pad vira comando `Motor <dir>` no log da Atividade; a lente sÃ³ vai mover com driver CloudLink futuro (trilha em `apk_mine.py`/`mine_out.txt`).
- `tray_app.py`: `QSystemTrayIcon` + popover 384x700, Ã­cone muda ao gravar.
- Smoke: `python .\yoosee_custom_app\panel_smoke.py` (offscreen, troca as 5 tabs).

## PrÃ³ximas funÃ§Ãµes (me diz quais quer)
1. Grade multi-cÃ¢mera + discovery ONVIF WS-Discovery
2. PTZ + presets via ONVIF (`porta 5000`)
3. DetecÃ§Ã£o de movimento + alerta Telegram
4. GravaÃ§Ã£o 24h com reconversÃ£o H.265->H.264
5. Interface grÃ¡fica (PyQt) ou web (Flask) ou Android
