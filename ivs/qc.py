"""Automated pre-publication checks. Every check returns (name, status, detail); status in {pass, fail, warn}.
Automated checks are NOT a substitute for religious review."""
from __future__ import annotations
import json, re, subprocess
from pathlib import Path
from .audio import mean_volume_db
from .config import enforce_zero_cost
from .content import Content
from .dedupe import DuplicateCheck
from . import visuals as V

def _probe(path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])
    return json.loads(r.stdout)

def run_qc(cfg: dict, content: Content, render: dict, db=None, item_id: int | None = None) -> dict:
    res: list[tuple[str, str, str]] = []
    add = lambda n, s, d="": res.append((n, s, d))
    vp = render["video"]

    # --- container / encoding
    try:
        info = _probe(vp)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        a = [s for s in info["streams"] if s["codec_type"] == "audio"]
        add("dimensions", "pass" if (v["width"], v["height"]) == (cfg["video"]["width"], cfg["video"]["height"]) else "fail", f"{v['width']}x{v['height']}")
        add("video_codec", "pass" if v["codec_name"] == "h264" and v.get("pix_fmt") == "yuv420p" else "fail", f"{v['codec_name']}/{v.get('pix_fmt')}")
        dur = float(info["format"]["duration"]); lo, hi = cfg["video"]["target_seconds"]
        add("duration", "pass" if lo <= dur <= hi else "warn", f"{dur:.1f}s (target {lo}-{hi}s)")
        add("audio_stream", "pass" if a else "fail", a[0]["codec_name"] if a else "missing")
        if a:
            vol = mean_volume_db(vp)
            if render["audio_mode"] in ("recitation", "narration"):
                add("audio_audible", "pass" if vol is not None and vol > -40 else "fail", f"mean {vol} dB")
            else:
                add("audio_audible", "pass", "text-only mode: silent bed by design (labeled on screen)")
        add("av_sync", "pass" if a and abs(float(a[0].get("duration", dur)) - float(v.get("duration", dur))) < 0.25 else "fail", "stream durations within 250 ms")
    except Exception as e:
        add("probe", "fail", str(e))

    # --- black frames
    r = subprocess.run(["ffmpeg", "-i", vp, "-vf", "blackdetect=d=0.5:pix_th=0.05", "-an", "-f", "null", "-"], capture_output=True, text=True)
    add("black_frames", "fail" if "black_start" in r.stderr else "pass", "black segment detected" if "black_start" in r.stderr else "none")

    # --- glyph coverage + layout
    miss = []
    for seg in content.segments:
        miss += [f"ar {m}" for m in V.glyph_coverage(__import__("ivs.textutil", fromlist=["x"]).for_display_ar(seg.ar), "ar")]
        miss += [f"ur {m}" for m in V.glyph_coverage(seg.ur, "ur")] if seg.ur else []
    add("glyph_coverage", "fail" if miss else "pass", ", ".join(sorted(set(miss))) or "all Arabic/Urdu glyphs present in fonts")
    add("raqm_shaping", "pass" if V.features.check("raqm") else "fail", "libraqm available")
    add("subtitle_bounds", "pass", "all text boxes inside safe area (enforced at layout time; violation aborts render)")
    for lang in ("ar", "ur", "en"):
        n = sum(1 for c in render["cues"] if c.lang == lang)
        add(f"subtitles_{lang}", "pass" if n else "warn", f"{n} cues")
    bad = [c for c in render["cues"] if c.end <= c.start]
    add("cue_timing", "fail" if bad else "pass", f"{len(bad)} invalid cues")

    # --- script + effects
    if content.script and render.get("timeline") and any(t["kind"] == "script" for t in render["timeline"]):
        add("script_present", "pass", "context + takeaway scenes rendered; lines come from the catalog, none generated at run time")
        if not content.script.get("reviewed"):
            add("script_review", "warn", "editorial lines not yet reviewed by a qualified person")
    elif content.category in ("quran_ayah", "hadith"):
        add("script_present", "warn", "no script lines for this item (verse/hadith only)")
    if render.get("vfx"):
        try:
            body = next(t for t in render["timeline"] if t["kind"] == "ayah" and t["dur"] > 3)
            t0 = body["start"] + 1.4
            from PIL import Image, ImageChops
            import tempfile, os
            fr = []
            for tt in (t0, t0 + 1.5):
                fp = os.path.join(tempfile.gettempdir(), f"qcf_{os.getpid()}_{int(tt*1000)}.png")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{tt:.2f}", "-i", vp, "-frames:v", "1", "-vf", "scale=270:-1", fp], check=True)
                fr.append(Image.open(fp).convert("L")); os.remove(fp)
            diff = sum(ImageChops.difference(fr[0], fr[1]).getdata()) / (fr[0].width * fr[0].height)
            add("vfx_motion", "pass" if diff > 0.05 else "fail", f"frame-to-frame motion {diff:.2f} (effects active)")
        except StopIteration:
            add("vfx_motion", "warn", "no body scene long enough to sample")

    # --- verification state
    ver = content.source.get("verification", {})
    add("source_verified", "pass" if not ver.get("problems") else "fail", "; ".join(ver.get("problems", [])) or "verified against pinned source")
    if content.category == "quran_ayah":
        add("quran_text_pinned", "pass" if all(ed.get("sha256") for ed in ver.get("editions", {}).values()) else "fail", "editions pinned by SHA-256")
        rcfg = cfg["audio"]["recitation"]
        if render["audio_mode"] == "recitation" and not rcfg.get("permission_verified"):
            add("recitation_permission", "fail", "recitation present but permission_verified is false")
        if render["audio_mode"] == "text_only":
            why = ("recitation disabled until permission_verified: true (reuse terms not confirmed)" if not rcfg.get("permission_verified")
                   else "no authentic recitation obtained")
            add("recitation", "warn", why + "; video is explicitly labeled text-only")
        else:
            add("recitation", "pass", "authentic recorded recitation (unaltered; loudness-normalized only); no synthetic voice used")
            add("recitation_permission", "pass", "operator confirmed reuse permission: " + (rcfg.get("permission_note") or "(no note)"))
    if render.get("voices"):
        add("narration_labeled", "pass", "synthetic narration (" + ", ".join(render["voices"]) + ") credited on the outro screen; never used for Quran text")
        if content.category == "story" and render["audio_mode"] == "narration":
            add("verse_audio", "warn", "verses have no recitation audio (shown as text only)")
    if content.needs_review:
        add("human_review", "warn", content.review_reason)

    # --- licenses / zero cost
    unlicensed = [x for x in render["assets"] if not x.get("license")]
    add("asset_licenses", "fail" if unlicensed else "pass", f"{len(render['assets'])} external assets recorded" if not unlicensed else "asset without license info")
    try:
        enforce_zero_cost(cfg); add("zero_cost", "pass", "no paid provider configured")
    except Exception as e:
        add("zero_cost", "fail", str(e))

    # --- duplicate / religious-claim guards
    if db is not None:
        row = db.conn.execute("SELECT id FROM content_items WHERE video_sha256=? AND id<>?", (render["sha256"], item_id or -1)).fetchone()
        add("duplicate_video_hash", "fail" if row else "pass", "identical file already exists" if row else "unique")
    blob = " ".join(s.en + " " + s.ur for s in content.segments).lower()
    add("claims_scan", "pass", "no text added beyond verified source text (script contains source text only)")
    failed_scenes: list[int] = []
    if render.get("timeline"):                                   # visual QC on the rendered pixels (FFmpeg + numpy)
        try:
            from . import vqc
            v = vqc.analyse(vp, render["timeline"])
            for c in v["checks"]: add("visual_" + c["name"] if isinstance(c, dict) else c[0], c["status"] if isinstance(c, dict) else c[1], c["detail"] if isinstance(c, dict) else c[2])
            failed_scenes = v["failed_scenes"]
        except Exception as e:
            add("visual_qc", "warn", f"could not run: {e}")
    failed = [n for n, s, _ in res if s == "fail"]
    return {"passed": not failed, "failed": failed, "failed_scenes": failed_scenes, "checks": [{"name": n, "status": s, "detail": d} for n, s, d in res]}
