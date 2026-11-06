from __future__ import annotations
import os, copy
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent

PAID_MARKERS = ("openai", "elevenlabs", "anthropic", "azure", "polly", "shutterstock", "pexels_premium")

class ZeroCostViolation(RuntimeError):
    pass

def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else ROOT / "config.yaml"
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("zero_cost_mode", True)
    cfg["_root"] = str(ROOT)
    enforce_zero_cost(cfg)
    return cfg

def enforce_zero_cost(cfg: dict) -> None:
    """Refuse to start if config references a paid provider while zero_cost_mode is on."""
    if not cfg.get("zero_cost_mode", True):
        raise ZeroCostViolation("zero_cost_mode cannot be disabled in this build.")
    blob = yaml.safe_dump({k: v for k, v in cfg.items() if not k.startswith("_")}).lower()
    for m in PAID_MARKERS:
        if m in blob:
            raise ZeroCostViolation(f"Config references a paid service ({m}); refused by zero_cost_mode.")

def resolve(cfg: dict, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else Path(cfg["_root"]) / p
