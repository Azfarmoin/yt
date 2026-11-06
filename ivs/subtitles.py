"""Timeline + SRT/VTT export. Each timeline entry is one on-screen state."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Cue:
    start: float
    end: float
    lang: str
    text: str

def _ts(t: float, vtt=False) -> str:
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{'.' if vtt else ','}{ms:03d}"

def write_srt(cues: list[Cue], path: Path, lang: str, vtt=False) -> None:
    rows = [c for c in cues if c.lang == lang]
    out = ["WEBVTT", ""] if vtt else []
    for i, c in enumerate(rows, 1):
        if not vtt: out.append(str(i))
        out += [f"{_ts(c.start, vtt)} --> {_ts(c.end, vtt)}", c.text, ""]
    Path(path).write_text("\n".join(out), encoding="utf-8")

def read_seconds(text: str, lang: str) -> float:
    """Reading-time estimate used when no audio defines the timing."""
    words = len(text.split())
    per = {"ar": 0.75, "ur": 0.45, "en": 0.40}.get(lang, 0.45)
    return max(3.0, words * per)
