"""Creative direction + storyboard + storyboard QC for story videos. RULE-BASED (no AI at runtime): the engine derives a concept
from the human-authored, verified story file, then picks camera/character/environment choices that differ from recent videos
(direction_log). It does NOT invent events: it only stages the lines the author wrote. Prophets/Allah are never staged."""
from __future__ import annotations
import json
from . import db as DBM

ENV_INFO = {   # scene tag -> (setting, default 3D env, mood)
    "desert_dawn": ("desert at first light", "desert_dawn", "tense, expectant"), "desert_night": ("desert at night", "desert_night", "still, awe"),
    "sea_calm": ("open sea, calm", "sea_calm", "relief, hope"), "sea_storm": ("storm at sea", "sea_storm", "danger, fear"),
    "night_sea": ("sea at night", "night_sea", "isolation, supplication"), "mountain_dawn": ("mountains at dawn", "mountain_dawn", "reflective"),
    "sky_stars": ("night sky", "sky_stars", "wonder"),
    "geometric_night": ("Islamic geometric pattern space, night", "", "contemplative"), "geometric_dawn": ("Islamic geometric pattern space, dawn", "", "hopeful")}
ALLOWED_ACTORS = {"walker", "spearman", "traveller", "elephant", "camel", "ship", "bird"}          # generic, faceless. Nothing else can be staged.
FORBIDDEN_VISUAL = ("prophet", "nabi", "rasul", "messenger", "allah", "god", "angel", "jibril", "gabriel", "sahaba", "companion", "face", "eyes")
ACTION_ACTORS = {"army_march": [("spearman", 5), ("elephant", 2)], "flock": [("bird", 9)], "caravan": [("traveller", 3), ("camel", 3)],
                 "crowd_gather": [("walker", 6)], "ship_drift": [("ship", 1)], "none": []}
PALETTES = {   # character design = clothing palette; one per story, consistent inside it
    "sand_brown": dict(robe="#3b2f2a", accent="#8a4b2e", hood="#2a211e"), "indigo": dict(robe="#23305a", accent="#b88a2e", hood="#171f3c"),
    "olive": dict(robe="#4a5230", accent="#c9b27a", hood="#2f351f"), "ash_white": dict(robe="#bdb6a6", accent="#6b4a2e", hood="#8f897c"),
    "maroon": dict(robe="#5a2326", accent="#d0b070", hood="#3a1618"), "teal": dict(robe="#1f5a5a", accent="#e0c27a", hood="#143a3a")}
# Camera library. Every style is a smooth Catmull-Rom path RELATIVE to the live centroid of the actors, so the camera keeps tracking
# subjects that walk. Offsets are (x right, y forward, z up) in metres at dist=1; they are scaled for elephants/ships/landscapes.
STYLES = {
    "low_push":      ("low-angle push toward the group", [(0, (-2, -14, -0.8), (0, 0, 0.3)), (1, (0, -5, -0.7), (0, 0, 0.9))], 26),
    "crane_reveal":  ("rising crane reveal", [(0, (4, -9, -1.0), (0, 0, 0.5)), (0.5, (4, -10, 2.5), (0, 0, 0.5)), (1, (3, -9, 6.5), (0, 0, 0.5))], 26),
    "high_descent":  ("high-angle descent from behind", [(0, (0, -30, 14), (0, 0, 0)), (0.6, (-3, -16, 6), (0, 0, 0.5)), (1, (-4, -8, 0.8), (0, 0, 1.0))], 28),
    "sweep_behind":  ("wide lateral sweep behind the group", [(0, (-11, -5, 0.0), (0, 0, 0.6)), (0.5, (0, -8, 0.5), (0, 0, 0.6)), (1, (11, -5, 0.8), (0, 0, 0.6))], 30),
    "orbit_low":     ("low-angle orbit around the group", [(0, (-8, -4, -0.3), (0, 0, 0.8)), (0.33, (-8, -9, 0.0), (0, 0, 0.8)), (0.66, (0, -11, 0.4), (0, 0, 0.8)), (1, (8, -7, 0.2), (0, 0, 0.8))], 30),
    "over_shoulder": ("over-the-shoulder from behind (no faces)", [(0, (1.1, -3.4, 0.5), (0, 8, 0.2)), (1, (1.5, -2.7, 0.9), (0.5, 9, 0.3))], 36),
    "macro_feet":    ("close-up on footsteps and dust", [(0, (0.6, -4.2, -0.95), (0, 0, -1.1)), (1, (-0.3, -2.6, -1.0), (0.3, 1, -1.1))], 55),
    "pull_back":     ("pull-back to reveal scale", [(0, (0, -4, 0.2), (0, 0, 0.8)), (1, (0, -17, 2.5), (0, 0, 1.0))], 26),
    "push_through":  ("moving camera passing beside the group", [(0, (-9, -9, -0.2), (3, 6, 0.6)), (0.5, (-4, -1, 0.0), (1, 6, 0.8)), (1, (-2, 7, 0.4), (0, 14, 1.0))], 32),
    "pedestal_pan":  ("pedestal rise with a pan from ground to sky", [(0, (0, -12, -1.0), (0, 0, -0.5)), (1, (0, -12, 3.5), (0, 24, 3.2))], 28),
    "dutch_arc":     ("arcing track with a rising horizon", [(0, (9, -6, -0.4), (0, 0, 0.9)), (0.5, (9, -13, 0.8), (0, 0, 1.0)), (1, (-2, -15, 2.4), (0, 0, 1.1))], 28),
    "wide_establish":("wide establishing shot with slow dolly", [(0, (0, -22, 1.5), (0, 8, 2.5)), (1, (0, -13, 1.2), (0, 8, 2.2))], 24)}
NIGHT_ENVS = {"desert_night", "night_sea", "sky_stars"}
NO_3D = {"geometric_night", "geometric_dawn"}                    # patterns are 2.5D only
NEEDS_ACTORS = {"over_shoulder", "macro_feet"}          # need people/animals on the ground; never used for birds, ships or empty landscapes
CAMERAS = {k: (v[0], None) for k, v in STYLES.items()}          # public registry (name -> description)
DIST = {"person": 1.0, "elephant": 1.7, "camel": 1.4, "ship": 3.2, "bird": 1.4, "none": 2.4}

def camera_for(style: str, seed: int, dist: float = 1.0, focus=(0, 25, 1.5), composition: str = "centered_symmetry") -> dict:
    """Concrete camera path for a style. The seed mirrors the move left/right and varies lens/offsets so two shots that use the
    same style never look identical."""
    import random
    rr = random.Random(seed * 131 + sum(map(ord, style))); mirror = rr.choice((-1, 1)); jit = lambda: rr.uniform(0.85, 1.15)
    shift = {"thirds_left": -1.4, "thirds_right": 1.4}.get(composition, 0.0) * dist; lift = {"low_horizon": 0.9, "high_horizon": -0.7, "extreme_wide": 0.0}.get(composition, 0.0)
    _, keys, lens = STYLES[style]     # look z is raised so the subjects sit in the lower third, below the subtitle panel
    path = [dict(u=u, pos=[p[0] * mirror * dist * jit(), p[1] * dist, p[2] * (dist ** 0.6)], look=[l[0] * mirror * dist + shift, l[1] * dist, l[2] + 1.1 * dist ** 0.7 + lift]) for u, p, l in keys]
    return dict(path=path, rel=True, lens=lens + rr.choice((-2, 0, 3)), focus=list(focus), drift=0.05, clearance=0.5 if style != "macro_feet" else 0.25)

SOUND = {"army_march": "footsteps+rumble", "flock": "wings+chirps", "caravan": "footsteps+wind", "ship_drift": "waves+creak", "crowd_gather": "murmur+footsteps", "none": "ambience"}
TRANSITIONS = ["dissolve", "fade_through_dark", "light_wipe", "dip_to_sand_colour", "match_cut_on_motion"]

def _recent(db, kind, n=6):
    return [r[0] for r in db.conn.execute("SELECT value FROM direction_log WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, n))]

def _pick(options, recent, avoid=()):
    """Least-recently-used option not in `avoid`; ties keep list order."""
    ok = [o for o in options if o not in avoid] or list(options)
    return max(ok, key=lambda o: (recent.index(o) if o in recent else 99, -list(options).index(o)))

def analyse(story: dict) -> dict:
    d = story.get("direction") or {}
    scenes = [l.get("scene", "sky_stars") for l in story["lines"]]; acts = [l.get("action", "none") for l in story["lines"]]
    first = scenes[0]
    return {"story_id": story["id"], "title": story["title"], "theme": story.get("theme", ""),
            "setting": d.get("setting") or ENV_INFO.get(first, ("", "", ""))[0], "period": d.get("period", "as stated in the cited sources; not asserted by the engine"),
            "mood_arc": d.get("mood_arc") or [ENV_INFO.get(s, ("", "", "wonder"))[2] for s in dict.fromkeys(scenes)],
            "lesson": (story.get("takeaway") or {}).get("en", ""), "sources": story.get("sources", []),
            "symbolic": d.get("symbolic", ["Prophets and Allah are never shown; the story is told through landscape, light, weather and generic faceless people."]),
            "structure": {"beginning": 0, "conflict": max(1, len(scenes) // 2), "conclusion": len(scenes) - 1},
            "environments": list(dict.fromkeys(scenes)), "actions": list(dict.fromkeys(acts))}

def design_characters(story: dict, db) -> dict:
    sid = story["id"]; row = db.conn.execute("SELECT characters_json FROM storyboards WHERE story_id=?", (sid,)).fetchone()
    if row: return json.loads(row[0])                                   # consistent across re-renders
    name = _pick(list(PALETTES), _recent(db, "character_design", 4))
    return {"palette_name": name, "palette": PALETTES[name], "note": "Generic faceless design. Not a depiction of any historical person.",
            "scale_variation": [0.95, 1.0, 1.05]}

def units_from_story(story: dict, seconds_per_word: float = 0.42) -> list[dict]:
    out = []
    for l in story["lines"]:
        text = " ".join(filter(None, [(l.get("narration") or {}).get("en", ""), l.get("expect", "")])) or "verse"
        out.append(dict(env=l.get("scene", "sky_stars"), action=l.get("action", "none"), text=text, quran=l.get("quran"),
                        dur=round(max(3.0, min(9.0, len(text.split()) * seconds_per_word + 2.0)), 1)))
    return out

def _dist(action):
    t = [a for a, _ in ACTION_ACTORS.get(action, [])]
    return DIST["ship"] if "ship" in t else DIST["elephant"] if "elephant" in t else DIST["camel"] if "camel" in t else DIST["bird"] if t == ["bird"] else DIST["person"] if t else DIST["none"]

def build_storyboard(story: dict, db, units: list[dict] | None = None, max_3d_seconds: float = 45.0, treatment: dict | None = None) -> dict:
    """units: one per planned shot (default: one per story line). In the full render the units come from the real timeline
    (narration/recitation durations), so shots always match what is spoken. Shots longer than 9 s are cut into several shots."""
    concept = analyse(story); chars = design_characters(story, db); units = units or units_from_story(story)
    flat = []
    for ui, u in enumerate(units):
        d = u["dur"]; n = max(1, int(-(-d // 9.0)))
        for k in range(n): flat.append(dict(u, dur=round(d / n, 2), part=k, unit=ui))
    rc, rt = _recent(db, "camera", 14), _recent(db, "transition", 4)
    scenes, used, prev = [], [], None; last = len(flat) - 1; conflict = max(1, len(flat) // 2)
    # 3D budget (unit level, so a scene is never half 3D): hook unit first, then one unit per distinct (environment, action) look,
    # actor scenes before landscape-only ones, so the 3D seconds are spent on different-looking moments rather than one repeated shot.
    udur, ukey = {}, {}
    for u in flat: udur[u["unit"]] = udur.get(u["unit"], 0) + u["dur"]; ukey[u["unit"]] = (u["env"], u["action"])
    uids = sorted(udur); budget = max_3d_seconds; chosen_units = [uids[0]]; budget -= udur[uids[0]]
    seen = {ukey[uids[0]]}; rest = [x for x in uids[1:]]
    for pass_ in (0, 1, 2):
        for ui in list(rest):
            k = ukey[ui]; has = bool(ACTION_ACTORS.get(k[1]))
            if k[0] in NO_3D or (not has and k[0] in NIGHT_ENVS): continue      # empty night landscapes look best in 2.5D
            if pass_ == 0 and (k in seen or not has): continue
            if pass_ == 1 and k in seen: continue
            if udur[ui] <= budget + 1e-6: chosen_units.append(ui); budget -= udur[ui]; seen.add(k); rest.remove(ui)
    use3d = {i for i, u in enumerate(flat) if u["unit"] in chosen_units}
    for i, u in enumerate(flat):
        tag, action = u["env"], u["action"]; has_actors = bool(ACTION_ACTORS.get(action))
        ground = any(t in ("walker", "spearman", "traveller", "elephant", "camel") for t, _ in ACTION_ACTORS.get(action, []))
        avail = [k for k in STYLES if ground or k not in NEEDS_ACTORS]
        fam = [k for k in (treatment or {}).get("camera", {}).get("styles", []) if k in avail]
        if len(fam) >= 2: avail = fam                  # the Director's camera family (falls back to every style when too narrow)
        pool = [k for k in ("low_push", "crane_reveal", "high_descent", "pedestal_pan", "orbit_low", "sweep_behind") if k in avail] if i == 0 else avail
        hist = [v.split('|')[0] for v in _recent(db, 'hook_shot', 6)] if i == 0 else rc + used[::-1]      # the hook is judged against previous HOOKS
        cam = _pick(pool, hist, avoid=(prev,) + tuple(used[-3:])); used.append(cam); prev = cam
        trans = _pick(TRANSITIONS, rt + [s["transition"] for s in scenes][::-1]) if i < last else "fade_to_outro"
        text = u["text"]
        scenes.append({"unit": u["unit"], "scene": i + 1, "role": "hook" if i == 0 else ("conclusion" if i == last else ("conflict" if i == conflict else "development")),
              "narration": text if not u.get("quran") else f"[Quran {u['quran']} - verse text from verified source]",
              "visual": f"{ENV_INFO.get(tag, ('', '', ''))[0]}; " + (", ".join(f"{n}x {t}" for t, n in ACTION_ACTORS[action]) + " (faceless, generic)" if has_actors else "no people: landscape/weather only"),
              "environment": tag, "technique": "blender_3d" if i in use3d else "layered_2_5d",
              "character_movement": {"army_march": "marching walk cycle, elephant leg cycle", "flock": "wing-flap cycles", "caravan": "walking with staffs, camel gait", "crowd_gather": "walking together", "ship_drift": "ship pitching on the waves", "none": "none"}[action],
              "actors": [{"type": t, "count": n} for t, n in ACTION_ACTORS[action]], "dist": _dist(action),
              "camera": cam, "camera_desc": STYLES[cam][0], "lighting": ENV_INFO.get(tag, ("", "", ""))[0] + " lighting, consistent per scene",
              "sound": SOUND.get(action, "ambience"), "transition": trans, "composition": (treatment or {}).get("camera", {}).get("composition", "centered_symmetry"), "lighting_override": ((treatment or {}).get("lighting_override") or {}), "duration_s": u["dur"], "purpose": f"{'open with a visual question' if i == 0 else 'advance the narrated line'}: {text[:70]}"})
    return {"concept": concept, "characters": chars, "scenes": scenes, "total_s": round(sum(s["duration_s"] for s in scenes), 1)}

def qc_storyboard(sb: dict, db=None) -> dict:
    p, sc = [], sb["scenes"]
    if not sc: p.append("no scenes")
    for s in sc:
        if not s.get("purpose"): p.append(f"scene {s['scene']}: no storytelling purpose")
        for a in s.get("actors", []):
            if a["type"] not in ALLOWED_ACTORS: p.append(f"scene {s['scene']}: actor '{a['type']}' not allowed (faceless generic actors only)")
        vis = (s["visual"] + " " + s["character_movement"]).lower()
        for w in FORBIDDEN_VISUAL:
            if w in vis.replace("faceless", "").replace("no faces", ""): p.append(f"scene {s['scene']}: visual text mentions forbidden term '{w}'")
        if not (1.5 <= s["duration_s"] <= 12): p.append(f"scene {s['scene']}: duration {s['duration_s']}s out of range")
        if s["camera"] not in CAMERAS: p.append(f"scene {s['scene']}: unknown camera")
    cams = [s["camera"] for s in sc]
    for a, b in zip(cams, cams[1:]):
        if a == b: p.append("repetitive camera: same move in consecutive scenes")
    if len(sc) >= 3 and len(set(cams)) < 3: p.append("camera variety: fewer than 3 distinct moves")
    if sc and sc[0]["role"] != "hook": p.append("first scene is not a hook")
    if sc and sc[0]["camera"] in ("wide_dolly_in",) and False: pass
    if db is not None:
        last = _recent(db, "hook_shot", 1)
        if last and sc and last[0] == f"{sc[0]['camera']}|{sc[0]['environment']}": p.append("hook shot repeats the previous video's hook shot")
    return {"ok": not p, "problems": p}

def save(db, story: dict, sb: dict, qc: dict) -> None:
    t = DBM.now(); sid = story["id"]
    db.conn.execute("INSERT OR REPLACE INTO storyboards VALUES(?,?,?,?,?,?)", (sid, json.dumps(sb["concept"]), json.dumps(sb["scenes"]), json.dumps(sb["characters"]), json.dumps(qc), t))
    db.conn.execute("DELETE FROM direction_log WHERE story_id=?", (sid,))
    rows = [("concept", f"{sb['concept']['setting']}|{'>'.join(sb['concept']['environments'])}"), ("character_design", sb["characters"]["palette_name"]),
            ("hook_shot", f"{sb['scenes'][0]['camera']}|{sb['scenes'][0]['environment']}")]
    for s in sb["scenes"]:
        rows += [("camera", s["camera"]), ("environment", s["environment"]), ("transition", s["transition"]), ("sound", s["sound"]),
                 ("composition", f"{s['camera']}|{s['environment']}|{s['actors'] and s['actors'][0]['type']}"), ("animation", s["character_movement"])]
    db.conn.executemany("INSERT INTO direction_log(story_id,kind,value,ts) VALUES(?,?,?,?)", [(sid, k, v, t) for k, v in rows]); db.conn.commit()
