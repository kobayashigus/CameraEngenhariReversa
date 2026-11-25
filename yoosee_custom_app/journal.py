"""Journal local: tempo online + eventos. Espelha UsageJournal/EventLog do LG (sem nuvem)."""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

ONLINE_STATES = {"live", "ao vivo", "gravando", "recording"}


def appdata_dir() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "YooseeWidget")
    os.makedirs(d, exist_ok=True)
    return d


def _now() -> float:
    return time.time()


@dataclass
class Session:
    start: float
    end: float  # 0 = aberta
    state: str = "live"


class Journal:
    """Sessoes de 'online' (ao vivo/gravando). Salvo em usage.json."""

    def __init__(self, path: str = ""):
        self.path = path or os.path.join(appdata_dir(), "usage.json")
        self.sessions: list[Session] = []
        self._open_start: float = 0.0
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            self.sessions = [Session(**s) for s in raw.get("sessions", [])][-500:]
        except Exception:
            self.sessions = []

    def save(self):
        try:
            self._flush_open()
            data = {"sessions": [asdict(s) for s in self.sessions[-500:]]}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)
        except Exception:
            pass

    @staticmethod
    def _is_online(state: str) -> bool:
        return (state or "").strip().lower() in ONLINE_STATES

    def observe(self, state: str):
        """Chame a cada mudanca de status + tick 30s."""
        online = self._is_online(state)
        if online and not self._open_start:
            self._open_start = _now()
        elif not online and self._open_start:
            self.sessions.append(Session(start=self._open_start, end=_now(), state="live"))
            self._open_start = 0.0
            self.save()

    def _flush_open(self):
        if self._open_start:
            # fecha sessoes abertas p/ calculo sem perder o inicio
            self.sessions.append(Session(start=self._open_start, end=_now(), state="live"))
            self._open_start = _now()

    def pause(self):
        self.observe("paused")

    def totals(self, days: int = 1) -> dict:
        """Retorna {'online': segs, 'sessions': n, 'since': iso}."""
        since = (datetime.now() - timedelta(days=max(0, days - 1))).replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp()
        total = 0.0
        count = 0
        for s in self.sessions:
            end = s.end or _now()
            if end < since:
                continue
            total += max(0.0, min(end, _now()) - max(s.start, since))
            count += 1
        if self._open_start and self._open_start >= since:
            total += _now() - max(self._open_start, since)
            count += 1
        return {"online": total, "sessions": count}

    def breakdown(self, days: int = 1) -> dict:
        t = self.totals(days)
        return t


class EventLog:
    """Historico de eventos (max 200). Salvo em events.json."""

    def __init__(self, path: str = ""):
        self.path = path or os.path.join(appdata_dir(), "events.json")
        self.events: list[dict] = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.events = json.load(f).get("events", [])[:200]
        except Exception:
            self.events = []

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"events": self.events[:200]}, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def log(self, title: str, detail: str = ""):
        # nunca gravar senha
        for secret in ("password", "pwd=", "rtsp://"):
            if secret.lower() in detail.lower() and "rtsp://" in detail.lower():
                detail = "[redacted rtsp url]"
                break
        self.events.insert(0, {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "title": title[:80],
            "detail": detail[:300],
        })
        self.events = self.events[:200]
        self.save()

    def clear(self):
        self.events = []
        self.save()


def duration_fmt(seconds: float) -> str:
    s = int(seconds or 0)
    if s < 60:
        return f"{s} s"
    m = s // 60
    if m < 60:
        return f"{m} min"
    return f"{m // 60} h {m % 60:02d} min"
