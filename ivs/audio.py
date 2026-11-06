"""Audio: authentic recitation download (EveryAyah, run on YOUR machine), optional local Piper narration,
FFmpeg normalization/mixing. Never synthesizes Quran recitation."""
from __future__ import annotations
import subprocess, json, shutil
from pathlib import Path
import requests

class AudioError(Exception):
    pass

def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise AudioError(f"{cmd[0]} failed: {r.stderr[-600:]}")
    return r

def probe_duration(path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(r.stdout)["format"]["duration"])

def fetch_recitation(cfg: dict, cache: Path, surah: int, ayah: int) -> dict | None:
    """Returns {'path','duration','source_url','reciter','license'} or None if unavailable (caller falls back to labeled text-only)."""
    rc = cfg["audio"]["recitation"]
    if not rc.get("enabled", True):
        return None
    if not rc.get("permission_verified", False):      # spec: no verified reuse permission => do not use the recording
        return None
    name = f"{surah:03d}{ayah:03d}.mp3"
    d = cache / "recitation" / rc["reciter"]; d.mkdir(parents=True, exist_ok=True)
    p = d / name
    url = f"{rc['base_url'].rstrip('/')}/{rc['reciter']}/{name}"
    if not p.exists():
        try:
            r = requests.get(url, timeout=45)
            if r.status_code != 200 or len(r.content) < 2000:
                return None
            p.write_bytes(r.content)
        except requests.RequestException:
            return None
    try:
        dur = probe_duration(p)
    except AudioError:
        p.unlink(missing_ok=True); return None
    if dur < 0.5:
        return None
    return {"path": str(p), "duration": dur, "source_url": url, "reciter": rc["reciter"],
            "license": rc.get("permission_note") or "reuse permission confirmed by the operator (see config audio.recitation.permission_note)",
            "reciter_display": rc.get("reciter_display", rc["reciter"]), "style": rc.get("style", "")}

def narrate_piper(text: str, voice_onnx: str, out_wav: Path) -> float | None:
    """Optional local TTS for *educational narration only* (never for Quran). Requires `piper` CLI + a voice."""
    if not voice_onnx or not shutil.which("piper"):
        return None
    r = subprocess.run(["piper", "--model", voice_onnx, "--output_file", str(out_wav)], input=text, capture_output=True, text=True)
    return probe_duration(out_wav) if r.returncode == 0 and out_wav.exists() else None

def build_track(parts: list[dict], out: Path, total: float) -> Path:
    """parts: [{'file': path|None, 'start': sec, 'dur': sec}]. Places each clip at its start time on a silent bed,
    then loudness-normalizes (EBU R128 single pass) with a true-peak limiter. No music under recitation."""
    inputs, filters, labels = [], [], []
    idx = 0
    for p in parts:
        if not p.get("file"):
            continue
        inputs += ["-i", str(p["file"])]
        ms = int(p["start"] * 1000)
        gate = "".join(f",volume=0:enable='between(t,{a:.3f},{b:.3f})'" for a, b in p.get("mute", []))
        # the gate runs BEFORE adelay on the clip's own clock, so shift windows by -start
        gate = "".join(f",volume=0:enable='between(t,{max(a - p['start'], 0):.3f},{max(b - p['start'], 0):.3f})'" for a, b in p.get("mute", []))
        filters.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo{gate}{(',volume=' + str(p['gain'])) if p.get('gain') else ''},adelay={ms}|{ms}[a{idx}]")
        labels.append(f"[a{idx}]"); idx += 1
    base = ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    if not labels:
        cmd = ["ffmpeg", "-y", *base, "-c:a", "aac", "-b:a", "192k", str(out)]
    else:
        fc = ";".join(filters) + f";[{idx}:a]" + "".join(labels) + f"amix=inputs={idx + 1}:normalize=0:duration=first," \
             f"loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.89,atrim=0:{total:.3f}[out]"
        cmd = ["ffmpeg", "-y", *inputs, *base, "-filter_complex", fc, "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(out)]
    run(cmd)
    return out

def mean_volume_db(path) -> float | None:
    r = subprocess.run(["ffmpeg", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "mean_volume" in line:
            try: return float(line.split("mean_volume:")[1].split("dB")[0])
            except ValueError: return None
    return None


def make_ambience(path: Path, kind: str, seconds: float) -> Path:
    """Quiet, license-free ambience synthesized by FFmpeg (wind for desert/mountain/sky, surf for sea)."""
    sea = kind.startswith(("sea", "night_sea"))
    src = f"anoisesrc=color={'pink' if sea else 'brown'}:amplitude=0.5:duration={seconds:.2f}:sample_rate=44100"
    filt = ("lowpass=f=700,tremolo=f=0.2:d=0.7,volume=0.16" if sea else "lowpass=f=420,tremolo=f=0.12:d=0.6,volume=0.20")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", src, "-af", f"{filt},afade=t=in:d=1.5,afade=t=out:st={max(seconds - 2, 0):.2f}:d=2", "-ac", "2", str(path)])
    return path
