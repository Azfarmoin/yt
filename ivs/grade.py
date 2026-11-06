"""Colour grading profiles (FFmpeg filters only). Gentle by design: lifted blacks (no crushing), moderate saturation, no teal/orange or HDR look."""
from __future__ import annotations
from pathlib import Path
from .audio import run

PROFILES = {   # name: FFmpeg video filter chain (white balance / curve / saturation / vignette)
 "filmic_natural":     "curves=all='0/0.012 0.25/0.235 0.5/0.5 0.75/0.77 1/0.975',eq=saturation=0.97:contrast=1.03,vignette=PI/6",
 "warm_dawn":          "colorbalance=rs=0.04:gs=0.01:bs=-0.04:rm=0.03:bm=-0.03,curves=all='0/0.015 0.5/0.52 1/0.98',eq=saturation=1.03,vignette=PI/6",
 "cool_dusk":          "colorbalance=rs=-0.03:bs=0.05:rm=-0.02:bm=0.04,curves=all='0/0.02 0.5/0.49 1/0.97',eq=saturation=0.95,vignette=PI/5",
 "documentary_muted":  "eq=saturation=0.82:contrast=1.04,curves=all='0/0.012 0.5/0.5 1/0.98',vignette=PI/7",
 "soft_pastel":        "curves=all='0/0.04 0.5/0.54 1/0.97',eq=saturation=0.9:contrast=0.96,vignette=PI/8",
 "deep_night":         "curves=all='0/0.03 0.3/0.31 0.7/0.72 1/0.96',eq=saturation=0.98:brightness=0.01,vignette=PI/5",
 "high_clarity":       "unsharp=5:5:0.5,eq=contrast=1.06:saturation=1.02,curves=all='0/0.01 1/0.985',vignette=PI/8",
 "sepia_archive":      "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,eq=saturation=0.85:contrast=1.02,vignette=PI/5"}

def filter_for(profile: str) -> str:
    return PROFILES.get(profile, PROFILES["filmic_natural"])

def apply(src: Path, dst: Path, profile: str, fps: int = 24) -> Path:
    run(["ffmpeg", "-y", "-i", str(src), "-vf", filter_for(profile) + ",format=yuv420p", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-an", str(dst)])
    return dst
