"""Scene planning + FFmpeg assembly -> vertical MP4 (+ SRT/VTT, thumbnail, layout report)."""
from __future__ import annotations
import json, shutil, subprocess
from pathlib import Path
from PIL import Image
from .audio import fetch_recitation, build_track, probe_duration, run
from .content import Content
from .subtitles import Cue, write_srt, read_seconds
from .textutil import sha256_file
from . import visuals as V
from . import vfx, anim, tts, sfx, jsfx

CATEGORY_LABEL = {"quran_ayah": "QURAN", "hadith": "HADITH", "story": "STORY"}
TEXT_ONLY_NOTE = "Text-only presentation (no recitation audio)"

def _chunks(text: str, n: int) -> list[str]:
    w = text.split(); per = -(-len(w) // n)
    return [" ".join(w[i:i + per]) for i in range(0, len(w), per)] if w else [""]

def _try_scene(path, **kw):
    """Render a scene; if text can't fit legibly, split every text slot into n chunks (up to 5) and return a list."""
    try:
        return [V.render_scene(path, **kw)], [kw]
    except V.LayoutError:
        pass
    for n in range(2, 6):
        parts = {k: _chunks(kw[k], n) for k in ("ar", "ur", "en") if kw.get(k)}
        m = max(len(v) for v in parts.values())
        out, kws = [], []
        try:
            for i in range(m):
                k2 = dict(kw)
                for k, v in parts.items():
                    k2[k] = v[i] if i < len(v) else ""
                p = Path(str(path).replace(".png", f"_c{i}.png"))
                out.append(V.render_scene(p, **k2)); kws.append(k2)
            return out, kws
        except V.LayoutError:
            continue
    raise V.LayoutError("text cannot be laid out legibly even after splitting")

def render_video(cfg: dict, content: Content, work: Path, cache: Path, palette="default", shots=None) -> dict:
    V.require_raqm()
    vc = cfg["video"]; fps = vc["fps"]; mode = vc.get("subtitle_mode", "ar_ur_en_alternating")
    if content.category == "story":
        mode = vc.get("story_subtitle_mode", "ar_ur_en_stacked")
    wm = vc.get("watermark", "")
    trt = getattr(content, "treatment", None)            # Director's Treatment (None for non-story content)
    if trt: palette = trt["typography"]["palette"]
    anim.FADE_COLOR = "0x" + trt["transition"]["color"].lstrip("#") if trt else "black"
    pace = trt["pace"]["factor"] if trt else 1.0
    silent_lines = set(trt["sound"].get("silent_lines", [])) if trt else set()
    work.mkdir(parents=True, exist_ok=True)
    scenes: list[dict] = []          # {'png','dur','start','audio'?}
    cues: list[Cue] = []
    assets: list[dict] = []
    t = 0.0

    is_story = content.category == "story"
    nar = cfg.get("audio", {}).get("narration", {}) or {}
    voice_on = is_story and bool(nar.get("enabled", True))
    voice_langs = nar.get("story_languages", ["en"])
    voices_used: list[str] = []

    def speak(en: str, ur: str, tag: str):
        """Free local narration. Returns ([(wav, offset_in_scene)], total_seconds). English = Kokoro, Urdu = eSpeak NG."""
        out, off = [], 0.5
        if not voice_on: return out, 0.0
        for lang, text in (("en", en), ("ur", ur)):
            if lang not in voice_langs or not text: continue
            wav = work / f"voice_{tag}_{lang}.wav"
            d_ = tts.narrate(text, lang, wav, cfg)
            if d_:
                out.append((str(wav), off)); off += d_ + 0.45
                if lang not in voices_used: voices_used.append(lang)
        return out, (off - 0.45 + 0.6 if out else 0.0)
    tags = [sg.scene for sg in content.segments if sg.scene] or [anim.DEFAULT_TAG]

    def add(png, dur, audio=None, kind="scene", scene=None, hook_words=None, voices=None, action=None, line=-1):
        nonlocal t
        stem = Path(str(png)).with_suffix("")
        scenes.append({"png": str(png), "bg": f"{stem}_bg.png", "text": f"{stem}_text.png", "dur": dur, "start": t, "audio": audio,
                       "kind": kind, "anim": (scene or tags[0]) if is_story else None, "hook_words": hook_words,
                       "voices": voices or [], "action": action, "line": line})
        t += dur
        return t - dur

    # 1) hook
    if is_story:
        words = anim.hook_layers(content.hook, work)
        hv, hvd = speak(content.hook, content.hook_ur, "hook")
        hd = max(3.5, words[-1][1] + 1.6, hvd)
        hs = V.render_scene(work / "s_hook.png", "hook", palette, hd, label="", title="", watermark=wm)   # empty text layer (words are separate)
        st = add(hs.path, hd, kind="hook", hook_words=words, voices=hv, action=getattr(content, "hook_action", None))
        cues.append(Cue(st, st + hd, "en", content.hook))
    else:
        hs = V.render_scene(work / "s_hook.png", "hook", palette, 3.0, label=f"{CATEGORY_LABEL.get(content.category, '').strip()}  ·  {content.theme.upper()}",
                            title=content.hook, watermark=wm)
        add(hs.path, 3.0, kind="hook")

    # 1b) script: context line(s) before the verse
    sc_ = content.script if cfg.get("script", {}).get("enabled", True) else None
    if sc_ and sc_.get("context"):
        c = sc_["context"]
        cd = max(3.5, read_seconds(c["en"], "en"))
        cs = V.render_scene(work / "s_ctx.png", "script", palette, cd, label="CONTEXT", title=c["en"], ur=c["ur"], watermark=wm)
        st = add(cs.path, cd, kind="script")
        cues.append(Cue(st, st + cd, "en", c["en"])); cues.append(Cue(st, st + cd, "ur", c["ur"]))

    # 2) body, per segment
    text_only = True
    reciter_credit = ""
    for seg in content.segments:
        rec = None
        if seg.kind == "narration":                      # story narration caption over animated scenery (author's words)
            nv, nvd = speak(seg.en, seg.ur, f"n{len(scenes)}")
            nd = max(3.8 * pace, read_seconds(seg.en, "en") * pace, read_seconds(seg.ur, "ur") * 0.8 * pace, nvd)
            ns = V.render_scene(work / f"s{len(scenes)}_n.png", "narration", palette, nd, label="STORY", title=seg.en, ur=seg.ur, watermark=wm)
            st = add(ns.path, nd, kind="narration", scene=seg.scene, voices=nv, action=seg.action, line=seg.line)
            if seg.en: cues.append(Cue(st, st + nd, "en", seg.en))
            if seg.ur: cues.append(Cue(st, st + nd, "ur", seg.ur))
            continue
        if seg.audio_ref and seg.kind == "verse":
            rec = fetch_recitation(cfg, cache, *seg.audio_ref)
        if rec:
            text_only = False
            assets.append({"name": Path(rec["path"]).name, "kind": "recitation", "source_url": rec["source_url"],
                           "license": rec["license"], "attribution": f"Recitation: {rec.get('reciter_display', rec['reciter'])}"})
            reciter_credit = f"Recitation: {rec.get('reciter_display', rec['reciter'])}" + (f" ({rec['style']})" if rec.get("style") else "")
        lead, tail = 0.4, 0.8
        a_dur = (rec["duration"] + lead + tail) if rec else max(read_seconds(seg.ar, "ar"), read_seconds(seg.ur, "ur"), 4.0)
        base = dict(kind="body", palette=palette, label=seg.label, watermark=wm)
        sid = len(scenes)
        show_ur = mode in ("ar_ur", "ar_ur_en_alternating", "ar_ur_en_stacked")
        show_en = mode in ("ar_en", "ar_ur_en_stacked")
        stacked = mode == "ar_ur_en_stacked"
        try:
            sc, kws = _try_scene(work / f"s{sid}_a.png", duration=a_dur, ar=seg.ar, ur=seg.ur if show_ur else "",
                                 en=seg.en if show_en else "", **base)
        except V.LayoutError:
            if not stacked: raise
            sc, kws = _try_scene(work / f"s{sid}_a.png", duration=a_dur, ar=seg.ar, ur=seg.ur, **base)   # fall back to alternating
            stacked = False
        tot = sum(len(k.get("ar", "")) or 1 for k in kws)
        s0 = t
        for sc_i, k in enumerate(kws):
            share = (len(k.get("ar", "")) or 1) / tot
            d = a_dur * share
            st = add(sc[sc_i].path, d, audio=(rec["path"] if (rec and sc_i == 0) else None), kind="ayah", scene=seg.scene, action=seg.action)
            if k.get("ar"): cues.append(Cue(st, st + d, "ar", k["ar"]))
            if k.get("ur"): cues.append(Cue(st, st + d, "ur", k["ur"]))
            if k.get("en"): cues.append(Cue(st, st + d, "en", k["en"]))
            if rec and sc_i == 0: scenes[-1]["audio_start"] = st + lead
        if mode == "ar_ur_en_alternating":
            b_dur = max(4.0, read_seconds(seg.en, "en"))
            sc2, kws2 = _try_scene(work / f"s{sid}_b.png", duration=b_dur, ar=seg.ar, en=seg.en, **base)
            tot2 = sum(len(k.get("ar", "")) or 1 for k in kws2)
            for sc_i, k in enumerate(kws2):
                d = b_dur * ((len(k.get("ar", "")) or 1) / tot2)
                st = add(sc2[sc_i].path, d, kind="translation", scene=seg.scene, action=seg.action)
                cues.append(Cue(st, st + d, "en", k.get("en", "")))

    # 2b) script: takeaway after the verse
    if sc_ and sc_.get("takeaway"):
        k = sc_["takeaway"]
        kv, kvd = speak(k["en"], k.get("ur", ""), "take")
        kd = max(4.0, read_seconds(k["en"], "en"), kvd)
        ks = V.render_scene(work / "s_take.png", "script", palette, kd, label="TAKEAWAY", title=k["en"], ur=k["ur"], watermark=wm)
        st = add(ks.path, kd, kind="script", scene=tags[-1], voices=kv, action=None)
        cues.append(Cue(st, st + kd, "en", k["en"])); cues.append(Cue(st, st + kd, "ur", k["ur"]))

    # 3) outro: reference + credits + honesty label
    credits = []
    if content.source.get("translations"):
        tr = content.source["translations"]
        credits = [f"Urdu: {tr['ur'].split(':')[-1].strip()}", f"English: {tr['en'].split(':')[-1].strip()}"]
    if reciter_credit:
        credits.append(reciter_credit)
    if voices_used:
        credits.append("Narration: synthetic voice (" + " / ".join(tts.ENGINE_BY_LANG.get(v, v) for v in voices_used) + ")")
    if text_only and content.source.get("translations"):
        credits.append("Verses shown as text (no recitation audio)" if voices_used else TEXT_ONLY_NOTE)
    body = t
    out_dur = 4.5
    min_total = vc["target_seconds"][0]
    if body + out_dur < min_total:
        out_dur = min(min_total - body, 10.0)
    cta = getattr(content, "cta", "")
    ou = V.render_scene(work / "s_outro.png", "outro", palette, out_dur, label="SOURCE", title=content.reference_line,
                        extra_lines=credits + ([cta] if cta else []), watermark=wm)
    add(ou.path, out_dur, kind="outro", scene="sky_stars")
    total = t

    # 4) audio bed
    parts = [{"file": s["audio"], "start": s.get("audio_start", s["start"]), "dur": s["dur"]} for s in scenes if s.get("audio")]
    for s_ in scenes:
        for wav, off in s_.get("voices", []):
            parts.append({"file": wav, "start": s_["start"] + off, "dur": 0})
    if voices_used:                                   # sound design: effects tied to the on-screen action (never under verses)
        for s_ in scenes:
            if s_["kind"] in ("ayah", "translation") or not s_.get("action") or s_["action"] == "none" or s_.get("line", -1) in silent_lines: continue    # Director's silent beats: ambience only
            for w in sfx.effects_for(s_["action"], s_["dur"], cache):
                parts.append({"file": w, "start": s_["start"], "dur": s_["dur"], "gain": 2.2})
    if voices_used:                                   # ambience bed only when a voice track exists; silent under verses/recitation
        from .audio import make_ambience
        bed = make_ambience(work / "ambience.wav", tags[0], total)
        parts.append({"file": str(bed), "start": 0, "dur": total,
                      "mute": [(s_["start"], s_["start"] + s_["dur"]) for s_ in scenes if s_["kind"] in ("ayah", "translation")]})
    wav = build_track(parts, work / "audio.m4a", total)

    # 5) clips -> concat -> mux
    fx = vc.get("vfx", {}) or {}
    use_fx = bool(fx.get("enabled", True))
    particles = None
    if use_fx and fx.get("particles", True):
        particles = str(vfx.make_particles(cache / "vfx" / f"particles_{palette}.mp4", palette, fps))
    clips = []
    jx = cfg.get("js_fx") or {}; js_on = jsfx.enabled(cfg); js_log: list[str] = []
    shotmap = (shots(scenes) or {}) if (shots and is_story) else {}
    A = anim.build_assets(cache) if is_story else None
    stars = str(anim.make_stars(cache / "anim" / "stars.mp4", fps)) if is_story else None
    for i, s in enumerate(scenes):
        clip = work / f"clip{i:02d}.mp4"
        if i in shotmap:
            bg = shotmap[i][0]
            if len(shotmap[i]) > 1:
                bg = str(work / f"bg3d_{i:02d}.mp4"); lst3 = work / f"bg3d_{i:02d}.txt"; lst3.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in shotmap[i]))
                run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst3), "-c", "copy", bg])
            anim.scene_clip_3d(A, bg, None if s.get("hook_words") else s["text"], s["dur"], fps, clip, s.get("hook_words"))
        elif js_on and jx.get("p5", True) and is_story and str(s.get("anim") or "").startswith("geometric"):
            try:      # p5.js generative star lattice replaces the tile background of geometric scenes (geometry only, no figures)
                pal = ("#0b1a2b", "#d9b46a", "#3b7f8c") if s["anim"].endswith("night") else ("#14262e", "#f0d58c", "#6fa7a0")
                bg = str(jsfx.p5_clip(cache, anim.W, anim.H, fps, s["dur"], pal, seed=i + 1))
                anim.scene_clip_3d(A, bg, None if s.get("hook_words") else s["text"], s["dur"], fps, clip, s.get("hook_words")); js_log.append(f"p5:{i}")
            except Exception as e:
                js_log.append(f"p5 failed scene {i}: {e}")
                anim.scene_clip_actors(A, s["anim"], None if s.get("hook_words") else s["text"], s["dur"], fps, clip, stars, s.get("action"), cache, hook_words=s.get("hook_words"), index=i)
        elif s.get("anim"):
            anim.scene_clip_actors(A, s["anim"], None if s.get("hook_words") else s["text"], s["dur"], fps, clip, stars,
                                   s.get("action"), cache, hook_words=s.get("hook_words"), index=i)
        elif use_fx:
            vfx.scene_clip(s["bg"], s["text"], particles, s["dur"], fps, clip, index=i,
                           kenburns=fx.get("kenburns", True), reveal=fx.get("text_reveal", True))
        else:
            fade = min(0.35, s["dur"] / 4)
            run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps), "-t", f"{s['dur']:.3f}", "-i", s["png"],
                 "-vf", f"fade=t=in:st=0:d={fade},fade=t=out:st={s['dur'] - fade:.3f}:d={fade},format=yuv420p",
                 "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(clip)])
        clips.append(clip)
    lst = work / "clips.txt"
    lst.write_text("".join(f"file '{c.name}'\n" for c in clips))
    silent = work / "video_only.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])
    if js_on:
        try:
            bounds = [s_["start"] for s_ in scenes[1:]]
            if jx.get("transitions", True) and is_story and bounds:
                tr_out = work / "video_tr.mp4"; silent = jsfx.transition_pass(silent, tr_out, bounds, fps, content.key, seconds=float(jx.get("transition_seconds", 0.6))); js_log.append("gl-transitions")
            layers = []
            vw, vh = jsfx._size(silent)
            if jx.get("pixi", True): layers.append(jsfx.pixi_loop(cache, vw, vh, fps, color="#ffe9b0", seed=7)); js_log.append("pixi")
            if jx.get("frame", True) and not is_story: layers.append(jsfx.frame_loop(cache, vw, vh, fps)); js_log.append("hyperframes")
            if layers: ov_out = work / "video_fx.mp4"; silent = jsfx.overlay_pass(silent, ov_out, layers, fps)
        except Exception as e:                      # effects are decoration: never lose the video because of them
            js_log.append(f"js fx skipped: {e}")
    if trt:
        from . import grade as GR
        graded = work / "video_graded.mp4"; GR.apply(silent, graded, trt["color"]["grade"], fps); silent = graded
    final = work / "video.mp4"
    run(["ffmpeg", "-y", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
         "-shortest", "-movflags", "+faststart", str(final)])

    # 6) sidecars
    for lang in ("ar", "ur", "en"):
        if any(c.lang == lang for c in cues):
            write_srt(cues, work / f"subs.{lang}.srt", lang); write_srt(cues, work / f"subs.{lang}.vtt", lang, vtt=True)
    thumb = work / "thumbnail.jpg"
    if is_story:                                         # real frame (scenery + silhouettes) with large minimal title
        raw = work / "thumb_raw.png"; tclip = work / "thumb_clip.mp4"      # text-free frame of the opening scenery
        if 0 in shotmap: run(["ffmpeg", "-y", "-ss", "1.0", "-i", shotmap[0][0], "-vf", f"scale={V.W}:{V.H}:flags=lanczos", "-frames:v", "1", str(raw)])
        else:
            anim.scene_clip_actors(A, scenes[0]["anim"], "", 1.5, fps, tclip, stars, scenes[0].get("action"), cache)
            run(["ffmpeg", "-y", "-ss", "1.0", "-i", str(tclip), "-frames:v", "1", str(raw)])
        im = Image.open(raw).convert("RGB")
        from PIL import ImageDraw
        band = Image.new("RGBA", im.size, (0, 0, 0, 0)); bd = ImageDraw.Draw(band)
        for y in range(380, 1180):                          # soft dark band behind the title
            a = int(190 * (1 - abs((y - 780) / 400) ** 2)); bd.line([(0, y), (im.width, y)], fill=(4, 6, 16, max(a, 0)))
        im = Image.alpha_composite(im.convert("RGBA"), band)
        tl = V.TextLayer(); title = content.source.get("title", content.theme)
        f = V.font("en", 118); lines = V.wrap(title, f, "en", im.width - 200)
        y0 = 780 - len(lines) * 80
        for i, ln in enumerate(lines): tl.text((im.width // 2, y0 + i * 160), ln, f, (255, 244, 220), "en")
        tl.text((im.width // 2, y0 + len(lines) * 160 + 30), content.theme.upper(), V.font("label", 44), (217, 179, 106), "en")
        Image.alpha_composite(im, tl.rgba()).convert("RGB").save(thumb, quality=90)
    else:
        Image.open(scenes[0]["png"]).convert("RGB").save(thumb, quality=88)
    studio = None
    if is_story:                                         # thumbnail studio: 3 concepts from real film frames, best by legibility/clarity/balance
        try:
            from . import thumbstudio
            studio = thumbstudio.make(str(final), work / "thumbs", content.source.get("title", content.theme), content.theme, palette, total)
            shutil.copy(studio["chosen"], thumb)
        except Exception as e:
            studio = {"error": str(e)}
    layout = [{"scene": Path(s["png"]).name, "dur": round(s["dur"], 2)} for s in scenes]
    (work / "layout.json").write_text(json.dumps(layout, indent=2))
    return {"video": str(final), "thumbnail": str(thumb), "duration": total, "text_only": text_only, "assets": assets,
            "scene_pngs": [s["png"] for s in scenes], "sha256": sha256_file(final), "cues": cues,
            "audio_mode": ("recitation" if not text_only else ("narration" if voices_used else "text_only")), "voices": voices_used, "sfx": bool(voices_used), "vfx": use_fx or is_story, "shots_3d": sorted(shotmap), "js_fx": js_log, "thumbnail_studio": studio, "treatment": (trt or {}).get("style_id"),
            "timeline": [{"kind": x["kind"], "start": x["start"], "dur": x["dur"]} for x in scenes]}
