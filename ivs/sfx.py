"""Sound-design engine: every effect is synthesized locally by FFmpeg (no sample libraries, no licenses).
Effects are tied to the on-screen ACTION (animation.ACTIONS) so what you hear matches what moves. Silent under verses/recitation."""
from __future__ import annotations
from pathlib import Path
from .audio import run

STEP_HZ = 2.0            # walker sprites complete a 24-frame cycle in 1 s at 24 fps => 2 footfalls per second

def _lav(src: str, filt: str, out: Path, dur: float) -> Path:
    fade = f"afade=t=in:d=0.6,afade=t=out:st={max(dur - 0.8, 0):.2f}:d=0.8"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", src, "-af", f"{filt},{fade}", "-ac", "2", "-ar", "44100", str(out)])
    return out

def footsteps(out: Path, dur: float, hz=STEP_HZ, gain=0.9, crowd=1.0) -> Path:
    # soft low thuds on every footfall (+ a little grit), amplitude-gated brown noise
    gate = f"volume='pow(max(0,sin(PI*{hz}*t)),10)*{gain}':eval=frame"
    return _lav(f"anoisesrc=color=brown:amplitude=0.9:duration={dur:.2f}:sample_rate=44100", f"lowpass=f=260,{gate},volume={0.55 * crowd}", out, dur)

def rumble(out: Path, dur: float, gain=0.18) -> Path:
    return _lav(f"anoisesrc=color=brown:amplitude=0.7:duration={dur:.2f}:sample_rate=44100", f"lowpass=f=110,volume={gain}", out, dur)

def wings(out: Path, dur: float) -> Path:
    # fast flutter: band-passed noise gated at ~9 Hz, slowly swelling
    gate = "volume='pow(max(0,sin(2*PI*9*t)),2)*(0.5+0.5*sin(2*PI*0.2*t))':eval=frame"
    return _lav(f"anoisesrc=color=white:amplitude=0.5:duration={dur:.2f}:sample_rate=44100", f"highpass=f=1800,lowpass=f=6500,{gate},volume=0.35", out, dur)

def chirps(out: Path, dur: float) -> Path:
    e = "0.22*sin(2*PI*(2600+900*sin(2*PI*7*t))*t)*pow(max(0,sin(2*PI*1.7*t)),30)+0.16*sin(2*PI*(3400+600*sin(2*PI*9*t))*t)*pow(max(0,sin(2*PI*1.1*t+1)),40)"
    return _lav(f"aevalsrc='{e}':d={dur:.2f}:s=44100", "volume=0.9", out, dur)

def murmur(out: Path, dur: float) -> Path:
    return _lav(f"anoisesrc=color=pink:amplitude=0.4:duration={dur:.2f}:sample_rate=44100", "bandpass=f=500:width_type=h:w=500,tremolo=f=3.1:d=0.5,volume=0.22", out, dur)

def thunder(out: Path, dur: float) -> Path:
    return _lav(f"anoisesrc=color=brown:amplitude=0.9:duration={dur:.2f}:sample_rate=44100", "lowpass=f=140,volume='0.9*exp(-1.2*mod(t,6))':eval=frame", out, dur)

# action -> recipe: list of (generator, kwargs)
RECIPES = {
    "army_march": [(footsteps, {"gain": 1.0}), (rumble, {})],
    "caravan": [(footsteps, {"gain": 0.7, "hz": 1.8, "crowd": 0.7})],
    "flock": [(wings, {}), (chirps, {})],
    "crowd_gather": [(murmur, {}), (footsteps, {"gain": 0.4, "hz": 1.2, "crowd": 0.4})],
}

def effects_for(action: str, dur: float, cache: Path) -> list[str]:
    """Cached per (effect, rounded duration). Returns wav paths (possibly empty)."""
    out = []
    d = Path(cache) / "sfx"; d.mkdir(parents=True, exist_ok=True)
    for fn, kw in RECIPES.get(action or "", []):
        key = "_".join(f"{k}{v}" for k, v in sorted(kw.items()))
        p = d / f"{fn.__name__}_{key}_{int(round(dur * 10))}.wav"
        if not p.exists(): fn(p, dur, **kw)
        out.append(str(p))
    return out
