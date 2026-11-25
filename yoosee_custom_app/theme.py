"""Design tokens estilo LGwebOS-menubar adaptados p/ Yoosee (Windows/Qt)."""
from __future__ import annotations

PANEL_W = 384
PANEL_H = 704

BG_TOP = "#101318"
BG_BOT = "#0a0c10"
CARD_BG = "#1a212d"
CARD_BG_SOFT = "rgba(255,255,255,0.055)"
CARD_BORDER = "rgba(255,255,255,0.09)"
TEXT = "#e8ecf1"
MUTED = "#9aa7b8"

# Acento verde dinamico por estado (escolha do usuario)
ACCENTS = {
    "live": "#35d07f",
    "recording": "#ff5470",
    "connecting": "#ffa62b",
    "paused": "#8b98ab",
    "error": "#ff5470",
    "idle": "#8b98ab",
}

STATE_ACCENT = {
    "ao vivo": "live",
    "gravando": "recording",
    "conectando": "connecting",
    "pausado": "paused",
    "erro": "error",
}

def accent_for(status: str, recording: bool = False) -> str:
    s = (status or "").lower()
    if recording or "gravando" in s or "rec" in s:
        return ACCENTS["recording"]
    for key, kind in STATE_ACCENT.items():
        if key in s:
            return ACCENTS[kind]
    if "vivo" in s or "live" in s:
        return ACCENTS["live"]
    return ACCENTS["idle"]


def build_stylesheet(accent: str) -> str:
    return f"""
    QWidget {{ font-family: 'Segoe UI'; font-size: 13px; color: {TEXT}; }}
    #panelWindow {{ background: transparent; border: none; }}
    #panelRoot {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {BG_TOP}, stop:1 {BG_BOT});
                 border: 1px solid #2a3342; border-radius: 18px; }}
    #title {{ font-size: 15px; font-weight: 700; }}
    #subtitle {{ color: {MUTED}; font-size: 11px; }}
    #status {{ color: {MUTED}; font-size: 11px; }}
    #dot {{ font-size: 14px; }}
    #tabbar {{ background: rgba(255,255,255,0.06); border: 1px solid {CARD_BORDER}; border-radius: 12px; }}
    #tabBtn {{ background: transparent; border: none; border-radius: 9px; padding: 8px 2px; color: {MUTED}; font-size: 11px; }}
    #tabBtnActive {{ background: rgba(255,255,255,0.09); border: none; border-radius: 9px; padding: 8px 2px; color: {accent}; font-weight: 700; font-size: 11px; }}
    #card {{ background: {CARD_BG_SOFT}; border: 1px solid {CARD_BORDER}; border-radius: 12px; }}
    #cardSolid {{ background: {CARD_BG}; border: 1px solid #2a3342; border-radius: 12px; }}
    #section {{ color: {MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}
    #video {{ background: #000; border-radius: 12px; border: 1px solid #262f3d; }}
    #heroBadge {{ background: {accent}; color: #06130c; border-radius: 8px; font-size: 10px; font-weight: 800; padding: 3px 8px; }}
    #bigNumber {{ font-size: 34px; font-weight: 700; color: {accent}; }}
    #btn {{ background: #1e2532; border: 1px solid #2d3748; border-radius: 10px; padding: 8px 10px; }}
    #btn:hover {{ background: #28324a; }}
    #btnAccent {{ background: {accent}; border: none; border-radius: 10px; padding: 8px 10px; color: #06130c; font-weight: 700; }}
    #btnDanger {{ background: #2a1d22; border: 1px solid #5a2b35; border-radius: 10px; padding: 8px 10px; }}
    #btnDangerRecording {{ background: #a1253a; border: 1px solid #a1253a; border-radius: 10px; padding: 8px 10px; color: white; font-weight: 700; }}
    #ghost {{ background: transparent; border: none; color: {MUTED}; border-radius: 8px; }}
    #ghost:hover {{ background: #232c3d; color: white; }}
    #info {{ color: #8b98ab; font-size: 11px; }}
    #barBg {{ background: rgba(255,255,255,0.07); border-radius: 4px; }}
    QLineEdit {{ background: #0f131b; border: 1px solid #2d3748; border-radius: 8px; padding: 7px; selection-background-color: {accent}; }}
    QSlider::groove:horizontal {{ height: 5px; background: rgba(255,255,255,0.12); border-radius: 3px; }}
    QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; border-radius: 7px; background: {accent}; }}
    QListWidget {{ background: #0f131b; border: 1px solid #2d3748; border-radius: 10px; padding: 4px; }}
    QListWidget::item {{ padding: 6px; border-radius: 6px; }}
    QListWidget::item:selected {{ background: #232c3d; }}
    QToolTip {{ background: #0f131b; color: {TEXT}; border: 1px solid #2d3748; }}
    #ptzOverlay {{ background: rgba(8,10,14,0.62); border: 1px solid rgba(255,255,255,0.14); border-radius: 10px; }}
    #ptzBtn {{ background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.10); border-radius: 7px; padding: 4px; color: white; }}
    #ptzBtn:pressed {{ background: {accent}; color: #06130c; }}
    #zoomBadge {{ background: rgba(8,10,14,0.62); color: white; border-radius: 7px; font-size: 10px; font-weight: 700; padding: 3px 7px; }}
    #fsHint {{ color: rgba(255,255,255,0.60); font-size: 11px; background: transparent; border: none; }}
    QDialog {{ background: {BG_TOP}; }}
    """
