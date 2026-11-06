"""Detect the machine and pick a render tier (LOW / MEDIUM / HIGH). Works on Linux, Windows and macOS with the stdlib only."""
from __future__ import annotations
import os, shutil, subprocess, sys, ctypes
from pathlib import Path

def _ram_gb() -> float:
    try:
        if sys.platform.startswith("linux"):
            for l in open("/proc/meminfo"):
                if l.startswith("MemTotal"): return int(l.split()[1]) / 1024 / 1024
        if sys.platform == "win32":
            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("total", ctypes.c_ulonglong)] + [(f"x{i}", ctypes.c_ulonglong) for i in range(5)]
            s = MS(); s.l = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)); return s.total / 1024 ** 3
        if sys.platform == "darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 1024 ** 3
    except Exception:
        pass
    return 0.0

def _gpu() -> dict:
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0]
            name, mem = [x.strip() for x in out.split(",")]; return {"name": name, "vram_gb": round(int(mem) / 1024, 1), "api": "CUDA/OPTIX"}
        except Exception:
            pass
    return {"name": None, "vram_gb": 0.0, "api": None}

def detect(path: str | Path = ".") -> dict:
    cpu = os.cpu_count() or 1; ram = round(_ram_gb(), 1); gpu = _gpu(); free = round(shutil.disk_usage(str(path)).free / 1024 ** 3, 1)
    if gpu["vram_gb"] >= 4 and cpu >= 8 and ram >= 16: tier = "HIGH"
    elif (gpu["vram_gb"] >= 2 and cpu >= 4 and ram >= 8) or (cpu >= 8 and ram >= 12): tier = "MEDIUM"
    else: tier = "LOW"
    return {"cpu_threads": cpu, "ram_gb": ram, "gpu": gpu, "disk_free_gb": free, "tier": tier,
            "blender_available": _has_bpy(), "ffmpeg": bool(shutil.which("ffmpeg")), "low_disk": free < 5}

def _has_bpy() -> bool:
    import importlib.util
    return importlib.util.find_spec("bpy") is not None

PLANS = {   # what each tier does by default (user config can override)
    "LOW":    dict(tier="draft", max_seconds=12, device="CPU", note="2.5D film with a short 3D hook/key shot; CPU rendering"),
    "MEDIUM": dict(tier="draft", max_seconds=30, device="CPU", note="more 3D seconds; shadows and atmosphere"),
    "HIGH":   dict(tier="hd", max_seconds=60, device="GPU", note="longer higher-resolution Blender sequences (GPU when Cycles can use it)")}

def effective_three_d(cfg: dict, hw: dict | None = None) -> dict:
    """Merge the hardware plan with config: explicit config values win, `hardware.auto: false` disables auto selection."""
    hw = hw or detect(); td = dict(cfg.get("three_d", {}) or {}); auto = (cfg.get("hardware", {}) or {}).get("auto", True)
    plan = dict(PLANS[hw["tier"]]) if auto else {}
    for k in ("tier", "max_seconds"):
        if td.get(k) not in (None, "auto"): plan[k] = td[k]            # explicit value wins; "auto" = follow the hardware plan
    plan.setdefault("tier", "draft"); plan.setdefault("max_seconds", 12); plan.setdefault("device", "CPU")
    plan.update({k: v for k, v in td.items() if k in ("enabled", "engine") })
    if hw["low_disk"]: plan["max_seconds"] = min(plan.get("max_seconds", 12), 8)
    plan["hardware_tier"] = hw["tier"]; plan.setdefault("enabled", True); plan.setdefault("engine", "CYCLES"); return plan
