"""Storyboard scene -> Blender shot (PNG sequence -> H.264 clip). Runs bpy in a subprocess (it crashes the interpreter on
some hosts). TIERS are honest about cost: 'draft' is for review on weak machines, 'full' is 1080x1920 for a machine with time/GPU."""
from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
import numpy as np
from . import direction as D

RENDER_VERSION = "v4"            # bump when bl_scene.py changes the look, so cached shots are re-rendered
TIERS = {"draft": dict(res=[360, 640], fps=8, samples=8), "hd": dict(res=[540, 960], fps=12, samples=16), "full": dict(res=[1080, 1920], fps=24, samples=32)}

def actors_for(scene: dict, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed); out = []; sc = {"army_march": 1.0}.get(scene["environment"], 1.0)
    for a in scene["actors"]:
        n = a["count"]
        for i in range(n):
            t = a["type"]
            if t == "bird": out.append(dict(type="bird", x=float(rng.uniform(-14, 14)), y=float(rng.uniform(14, 40)), z=float(rng.uniform(9, 20)), heading=float(rng.uniform(-12, 12)), speed=float(rng.uniform(4, 6)), phase=float(rng.uniform(0, 1))))
            elif t == "elephant": out.append(dict(type="elephant", x=float(5.0 + i * 8 - 2), y=float(20 + 6 * i), heading=0, speed=1.5, phase=0.2 + 0.3 * i, scale=1.0))
            elif t == "camel": out.append(dict(type="camel", x=float(-6 + i * 4.5), y=float(22 + 4 * (i % 2)), heading=0, speed=1.4, phase=0.15 * i))
            elif t == "ship": out.append(dict(type="ship", x=float(rng.uniform(-3, 3)), y=30.0, heading=float(rng.uniform(-10, 10)), speed=0.5, phase=0.3, scale=1.0))
            else: out.append(dict(type=t, x=float(-4 + (i % 3) * 2.2 + rng.uniform(-.3, .3)), y=float(12 + (i // 3) * 3.2 + rng.uniform(-.5, .5)), heading=float(rng.uniform(-4, 4)),
                                  speed=float(rng.uniform(1.15, 1.45)), phase=float(rng.uniform(0, 1)), scale=float(rng.choice([0.95, 1.0, 1.05]))))
    return out

def props_for(scene: dict) -> list[dict]:
    e = scene["environment"]
    if e.startswith("desert"): return [{"type": "palm", "count": 5}, {"type": "rock", "count": 8}, {"type": "tent", "count": 2}]
    if e == "mountain_dawn": return [{"type": "rock", "count": 22}, {"type": "palm", "count": 2}]
    if e == "sky_stars": return [{"type": "rock", "count": 8}]
    return []

def make_spec(scene: dict, chars: dict, tier: str, out_dir: Path, seed: int, seconds: float | None = None, engine="CYCLES", device="CPU") -> dict:
    T = TIERS[tier]; dur = seconds or scene["duration_s"]; cam = D.camera_for(scene["camera"], seed + scene["scene"], scene.get("dist", 1.0), composition=scene.get("composition", "centered_symmetry"))
    ov = scene.get("lighting_override") if scene["environment"] not in D.NIGHT_ENVS else None
    return dict(env=D.ENV_INFO[scene["environment"]][1], frames=max(2, int(dur * T["fps"])), fps=T["fps"], res=T["res"], samples=T["samples"], seed=seed, engine=engine, device=device,
                out=str(out_dir), palette=chars["palette"], actors=actors_for(scene, seed), camera=cam, props=props_for(scene), env_override=ov or {})

def render_shot(scene: dict, chars: dict, tier: str, out_mp4: Path, seed: int = 1, seconds: float | None = None, engine="CYCLES", device="CPU") -> dict:
    out_mp4.parent.mkdir(parents=True, exist_ok=True); fr = out_mp4.with_suffix("") .parent / (out_mp4.stem + "_frames"); fr.mkdir(exist_ok=True)
    for f in fr.glob("*.png"): f.unlink()
    spec = make_spec(scene, chars, tier, fr, seed, seconds, engine, device); sp = fr / "spec.json"; sp.write_text(json.dumps(spec))
    t0 = time.time(); r = subprocess.run([sys.executable, "-m", "ivs.bl_scene", str(sp)], capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent)
    n = len(list(fr.glob("f*.png")))
    if n < spec["frames"]: return {"ok": False, "error": (r.stderr or r.stdout)[-600:], "frames": n}
    # 3D shots are cut into the 1080x1920/24fps timeline; draft tiers are upscaled + frame-interpolated by duplication (honestly lower quality)
    smooth = "" if spec["fps"] >= 24 else "minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc:vsbmc=1,"      # motion-compensated in-betweening for low-fps tiers
    vf = smooth + "scale=1080:1920:flags=lanczos,unsharp=5:5:0.7,noise=alls=5:allf=t,vignette=PI/5,format=yuv420p"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(spec["fps"]), "-i", str(fr / "f%05d.png"), "-vf", vf, "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", str(out_mp4)], check=True)
    return {"ok": True, "frames": n, "seconds_render": round(time.time() - t0, 1), "s_per_frame": round((time.time() - t0) / n, 1), "tier": tier, "camera": scene["camera"], "path": str(out_mp4)}


import hashlib

def provider(content, db, cfg: dict, cache: Path, render_missing: bool = False, log=print):
    """Returns shots(scenes)->{scene_index: [mp4,...]} for render_video. Builds the storyboard from the REAL timeline (so shots match
    the narration), stores it in SQLite, renders missing 3D shots only when render_missing is set (slow), otherwise uses cached ones."""
    from . import hardware
    td = hardware.effective_three_d(cfg)
    if not td.get("enabled", True): return None
    tier = td["tier"]; budget = float(td["max_seconds"]); engine = td.get("engine", "CYCLES"); device = td.get("device", "CPU")
    def shots(scenes: list[dict]) -> dict:
        from .content import load_stories
        root = Path(__file__).resolve().parent.parent
        story = next((s for s in load_stories(root / "content" / "stories") if s["_file"] == content.source.get("file")), None)
        if story is None: return {}
        idx = [i for i, s in enumerate(scenes) if s["kind"] != "outro"]
        units = [dict(env=scenes[i]["anim"] or "sky_stars", action=scenes[i].get("action") or "none", text=scenes[i]["kind"], dur=round(scenes[i]["dur"], 2), scene_index=i) for i in idx]
        tr = getattr(content, "treatment", None)
        if tr: tr["lighting_override"] = __import__("ivs.director", fromlist=["x"]).lighting_override(tr)
        sb = D.build_storyboard(story, db, units, budget, tr); qc = D.qc_storyboard(sb, db)
        D.save(db, story, sb, qc)
        if not qc["ok"]: log("storyboard QC failed -> falling back to 2.5D:", qc["problems"]); return {}
        out: dict[int, list[str]] = {}; seed = sum(map(ord, story["id"])); keys: dict[int, tuple[str, str]] = {}
        sdir = cache / "shots3d"; sdir.mkdir(parents=True, exist_ok=True)
        for sc in sb["scenes"]:
            if sc["technique"] != "blender_3d": continue
            spec = make_spec(sc, sb["characters"], tier, Path("."), seed, sc["duration_s"] + 0.45, engine, device); spec.pop("out")
            key = hashlib.sha1((RENDER_VERSION + json.dumps(spec, sort_keys=True)).encode()).hexdigest()[:16]; mp4 = sdir / f"{key}.mp4"
            keys[sc["scene"]] = (key, json.dumps(spec, sort_keys=True))
            if not mp4.exists():
                if not render_missing: continue
                log(f"  rendering 3D shot scene {sc['scene']} ({sc['camera']}, {sc['duration_s']}s) ...")
                res = render_shot(sc, sb["characters"], tier, mp4, seed, sc["duration_s"] + 0.45, engine, device); log("   ", {k: res.get(k) for k in ("ok", "s_per_frame", "error")})
                if not res["ok"]: continue
            out.setdefault(units[sc["unit"]]["scene_index"], []).append(str(mp4))
        # a scene is 3D only if ALL of its parts exist, otherwise the whole scene stays 2.5D (never a half-3D scene)
        need = {}
        for sc in sb["scenes"]:
            if sc["technique"] == "blender_3d": need[units[sc["unit"]]["scene_index"]] = need.get(units[sc["unit"]]["scene_index"], 0) + 1
        final = {k: v for k, v in out.items() if len(v) == need.get(k)}
        # scene manifest: every shot can be regenerated independently (delete its cached mp4 / re-run `film`; other shots are untouched)
        for sc in sb["scenes"]:
            k3 = keys.get(sc["scene"]); ok3 = sc["technique"] == "blender_3d" and units[sc["unit"]]["scene_index"] in final
            db.conn.execute("INSERT OR REPLACE INTO scene_manifest VALUES(?,?,?,?,?,?,?,?,?,?)", (story["id"], sc["scene"], k3[0] if k3 else None, sc["technique"], sc["environment"], sc["camera"],
                            k3[1] if k3 else None, ("rendered" if ok3 else ("pending" if sc["technique"] == "blender_3d" else "2.5d")), str(sdir / f"{k3[0]}.mp4") if k3 and ok3 else None, __import__("ivs.db", fromlist=["x"]).now()))
        db.conn.commit()
        return final
    return shots
