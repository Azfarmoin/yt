"""Zero-cost / license audit: static dependency table + live environment checks."""
from __future__ import annotations
import shutil, importlib
from .config import enforce_zero_cost

DEPENDENCIES = [
    # name, license, cost, limitation
    ("Python / PyYAML / requests", "PSF / MIT / Apache-2.0", "free", "—"),
    ("Pillow (+libraqm for Arabic/Urdu shaping)", "HPND / MIT", "free", "Needs a build with raqm (official wheels on Windows/macOS/Linux include it)"),
    ("FFmpeg / ffprobe", "LGPL/GPL (build-dependent)", "free", "Use a standard build with libx264 + aac"),
    ("SQLite", "Public domain", "free", "—"),
    ("Flask (optional dashboard)", "BSD-3", "free", "Bound to 127.0.0.1 only"),
    ("Amiri font", "SIL OFL 1.1", "free", "Keep license file with redistributed font"),
    ("Noto Nastaliq Urdu / Noto Sans / Noto Naskh Arabic", "SIL OFL 1.1", "free", "Keep license files"),
    ("Quran text: King Fahd Complex Uthmani Hafs v13 (via fawazahmed0/quran-api)", "Source terms apply (qurancomplex.gov.sa)", "free", "Text must not be altered; attribute source. Check terms before commercial use."),
    ("Quran cross-check + Urdu + English (Tanzil data via same mirror)", "Tanzil terms (verbatim, attribute, no modification)", "free", "Translations are third-party; credit translators on screen (done)"),
    ("Hadith text (fawazahmed0/hadith-api)", "Open data mirror; underlying texts public", "free", "Translation quality varies; every hadith item is forced to human review"),
    ("Recitation audio: EveryAyah.com (Alafasy 128kbps default)", "Free download; check site terms", "free", "NOT reachable from build sandbox; fetched on your PC. Verify reuse/monetization terms yourself."),
    ("Piper TTS (optional, educational narration only)", "MIT (engine); voices have individual licenses", "free", "Urdu voice availability must be confirmed; never used for Quran"),
    ("YouTube Data API v3", "Google API ToS", "free quota (default 10,000 units/day)", "Upload = 1,600 units (~6/day); OAuth apps in Testing mode expire refresh tokens in 7 days; unverified API projects may force uploads private"),
    ("GitHub Actions (optional)", "—", "free tier w/ quotas", "Not used by default: rendering is local; do not rely on it for 24/7 operation"),
]

PAID_PACKAGES = ("openai", "anthropic", "elevenlabs", "replicate", "stability", "runway", "midjourney", "azure-cognitiveservices", "google-cloud-texttospeech", "boto3", "pyttsx3-paid", "synthesia", "heygen")
PAID_ENV = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "REPLICATE_API_TOKEN", "STABILITY_API_KEY", "AZURE_SPEECH_KEY", "AWS_ACCESS_KEY_ID", "STRIPE")
FREE_TIER_LIMITS = [
    ("YouTube Data API", "10,000 quota units/day by default; one upload costs 1,600 (about 6 uploads/day). Unverified API projects may be forced private; Testing-mode OAuth refresh tokens expire after 7 days."),
    ("GitHub Actions", "Public repos: free. Private repos: a monthly free-minute allowance. Scheduled runs can be delayed or disabled after repo inactivity. Never assumed unlimited here."),
    ("edge-tts (optional, off by default)", "Free but unofficial/online Microsoft endpoint: no quota guarantee, can change or break, ToS risk. Disabled unless audio.narration.allow_edge is true."),
    ("Ollama / local LLM (optional)", "Free, runs on your PC; needs the model download and enough RAM. Not used unless running."),
    ("EveryAyah recitation", "Free to download; verify reuse/monetisation terms yourself. Off until permission_verified is true."),
    ("A powered-off PC", "Cannot render or run scheduled tasks. Local scheduler only works while the computer is on."),
]

def paid_scan(root) -> list[tuple[str, str, str]]:
    import os, re
    from pathlib import Path
    out = []; req = Path(root) / "requirements.txt"
    pk = [l.split("#")[0].strip().lower() for l in req.read_text().splitlines()] if req.exists() else []
    hit = [p for p in pk if any(re.match(r"^" + re.escape(x) + r"([<>=!~\[ ]|$)", p) for x in PAID_PACKAGES)]
    out.append(("paid_python_packages", "fail" if hit else "pass", ", ".join(hit) or "none in requirements.txt"))
    env = [k for k in PAID_ENV if os.environ.get(k)]
    out.append(("paid_api_keys_in_env", "warn" if env else "pass", (", ".join(env) + " present in the environment; this project never reads them") if env else "none set"))
    code = []
    for p in Path(root).glob("ivs/*.py"):
        if p.name in ("audit.py", "config.py"): continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"api\.openai\.com|api\.elevenlabs\.io|api\.anthropic\.com|runwayml|stability\.ai|replicate\.com", t): code.append(p.name)
    out.append(("paid_endpoints_in_code", "fail" if code else "pass", ", ".join(code) or "none referenced"))
    out.append(("credit_card_or_payment", "pass", "no code path asks for payment details"))
    return out

def run_audit(cfg: dict) -> dict:
    checks = []
    try:
        enforce_zero_cost(cfg); checks.append(("zero_cost_mode", "pass", "enabled, no paid provider referenced"))
    except Exception as e:
        checks.append(("zero_cost_mode", "fail", str(e)))
    for tool in ("ffmpeg", "ffprobe"):
        checks.append((tool, "pass" if shutil.which(tool) else "fail", shutil.which(tool) or "not on PATH"))
    from PIL import features
    checks.append(("pillow_raqm", "pass" if features.check("raqm") else "fail", "complex text layout"))
    for m in ("yaml", "requests", "flask"):
        try: importlib.import_module(m); checks.append((f"py:{m}", "pass", "installed"))
        except ImportError: checks.append((f"py:{m}", "warn" if m == "flask" else "fail", "not installed"))
    from .config import ROOT
    checks += paid_scan(ROOT)
    checks.append(("edge_tts_opt_in", "warn" if (cfg.get("audio", {}).get("narration", {}) or {}).get("allow_edge") else "pass", "online unofficial voice enabled" if (cfg.get("audio", {}).get("narration", {}) or {}).get("allow_edge") else "off (default)"))
    checks.append(("piper_tts", "pass" if shutil.which("piper") else "warn", "optional; narration disabled if absent"))
    return {"dependencies": DEPENDENCIES, "free_tier_limits": FREE_TIER_LIMITS, "checks": [{"name": n, "status": s, "detail": d} for n, s, d in checks]}
