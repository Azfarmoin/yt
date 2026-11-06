"""Automated visual QC from the RENDERED video (FFmpeg + numpy; no cloud, no ML): black/frozen frames, contrast, clipped
highlights/shadows, flicker, camera jitter (phase correlation), text-band legibility, and per-scene attribution so only the
failing scene needs regenerating."""
from __future__ import annotations
import subprocess
import numpy as np

W, H = 108, 192            # analysis resolution (1/10 of 1080x1920)

def sample_frames(path: str, fps: float = 4.0) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (W * H)
    return np.frombuffer(raw[: n * W * H], np.uint8).reshape(n, H, W).astype(np.float32) / 255.0

def _shift(a: np.ndarray, b: np.ndarray) -> float:
    """Global translation magnitude between two frames via phase correlation (pixels at analysis scale)."""
    fa, fb = np.fft.fft2(a - a.mean()), np.fft.fft2(b - b.mean()); r = fa * np.conj(fb); r /= np.abs(r) + 1e-9
    c = np.fft.ifft2(r).real; y, x = np.unravel_index(np.argmax(c), c.shape); y = y - H if y > H // 2 else y; x = x - W if x > W // 2 else x
    return float(np.hypot(x, y))

def analyse(path: str, timeline: list[dict], fps: float = 4.0) -> dict:
    fr = sample_frames(path, fps)
    if len(fr) < 4: return {"ok": False, "checks": [("frames", "fail", "too few frames decoded")], "failed_scenes": []}
    mean = fr.mean((1, 2)); std = fr.std((1, 2)); dark = (fr < 0.03).mean((1, 2)); bright = (fr > 0.97).mean((1, 2))
    checks, bad = [], set()
    def scene_of(i): 
        t = i / fps
        for k, s in enumerate(timeline):
            if s["start"] <= t < s["start"] + s["dur"]: return k
        return len(timeline) - 1
    bounds = [s["start"] for s in timeline[1:]]                       # fades through colour at scene boundaries are intentional transitions
    near = lambda t: any(abs(t - b) < 0.55 for b in bounds)
    black = [i for i in range(len(fr)) if mean[i] < 0.02 and std[i] < 0.01 and 1.0 < i / fps < len(fr) / fps - 1.0 and not near(i / fps)]
    for i in black: bad.add(scene_of(i))
    checks.append(("black_frames", "fail" if len(black) > 2 else "pass", f"{len(black)} near-black sample frames mid-video"))
    flat = [i for i in range(len(fr)) if std[i] < 0.012 and mean[i] > 0.02]
    checks.append(("flat_frames", "warn" if len(flat) > 4 else "pass", f"{len(flat)} flat/empty frames"))
    contrast = float(np.median(std)); checks.append(("contrast", "pass" if contrast > 0.07 else "warn", f"median luma std {contrast:.3f}"))
    crush = float(np.median(dark)); blow = float(np.median(bright))
    checks.append(("crushed_blacks", "pass" if crush < 0.55 else "warn", f"{crush:.0%} of pixels under 3% luma (median frame)"))
    checks.append(("blown_highlights", "pass" if blow < 0.08 else "warn", f"{blow:.1%} of pixels over 97% luma (median frame)"))
    # flicker: luma changes that reverse direction quickly inside a scene (excluding fades at boundaries)
    fl_bad = []
    for k, s in enumerate(timeline):
        a, b = int((s["start"] + 0.6) * fps), int((s["start"] + s["dur"] - 0.6) * fps)
        if b - a < 4: continue
        d = np.diff(mean[a:b]); sgn = np.sign(d[np.abs(d) > 0.012])
        if len(sgn) > 3 and (np.diff(sgn) != 0).mean() > 0.8 and np.abs(d).mean() > 0.012: fl_bad.append(k); bad.add(k)
    checks.append(("flicker", "fail" if fl_bad else "pass", f"flicker in scenes {fl_bad}" if fl_bad else "stable luma inside scenes"))
    # camera jitter: size of frame-to-frame shifts; jitter = erratic (high variance relative to mean) large shifts
    jit_bad = []
    for k, s in enumerate(timeline):
        a, b = int((s["start"] + 0.6) * fps), int((s["start"] + s["dur"] - 0.6) * fps)
        if b - a < 5 or s["kind"] in ("hook",): continue
        sh = np.array([_shift(fr[i], fr[i + 1]) for i in range(a, b - 1)])
        if len(sh) and sh.mean() > 0.4 and sh.std() > 1.4 * sh.mean() and sh.max() > 3.0: jit_bad.append(k); bad.add(k)
    checks.append(("camera_jitter", "fail" if jit_bad else "pass", f"erratic frame shifts in scenes {jit_bad}" if jit_bad else "camera motion smooth"))
    # text band legibility: contrast around the vertical centre where the subtitle panel lives is judged by the scene's own luma spread
    band = fr[:, int(H * 0.30): int(H * 0.70), :]; ls = band.std((1, 2)); lowc = [i for i in range(len(fr)) if ls[i] < 0.02 and mean[i] > 0.02]
    checks.append(("text_band_contrast", "warn" if len(lowc) > 0.5 * len(fr) else "pass", f"{len(lowc)}/{len(fr)} frames with a very flat text band"))
    return {"ok": not any(c[1] == "fail" for c in checks), "checks": [{"name": n, "status": s, "detail": d} for n, s, d in checks], "failed_scenes": sorted(bad)}
