"""Director Engine: reads the VERIFIED story (Content), then writes a unique Director's Treatment before anything is rendered.
It decides style, pacing, colour grade, typography personality, soundscape (including silence), opening approach, camera families and
transition colour. It never changes the author's environments, verses or narration. Rule-based and deterministic given the history
in SQLite, so the anti-repetition guarantees are testable."""
from __future__ import annotations
import json
from . import styles as ST, metaphor as MT, direction as D
from . import db as DBM

PERSONALITY_PALETTE = {"minimal_editorial": "editorial", "classical_islamic": "classical", "luxury_documentary": "luxury",
                       "cinematic_calligraphy": "calligraphic", "modern_educational": "educational"}
OPENINGS = {"establishing": "wide environmental reveal, then the question appears", "intimate": "close detail first, then pull out to the world",
            "sweeping": "moving camera reveals the setting while the question forms", "contemplative": "still atmospheric frame; the question arrives slowly",
            "still": "held composition; light changes while the question is read"}

def _story_text(content) -> str:
    parts = [content.hook or ""] + [f"{s.en}" for s in content.segments] + [((content.script or {}).get("takeaway") or {}).get("en", "")]
    return " ".join(p for p in parts if p)

def treat(content, story_dict: dict, db) -> dict:
    text = _story_text(content); met = MT.analyse(text)
    envs = [l.get("scene", "sky_stars") for l in story_dict["lines"]]
    recent_styles = [r[0] for r in db.conn.execute("SELECT value FROM direction_log WHERE kind='style' ORDER BY id DESC LIMIT 8")]
    prefer = [c[k] for c in met["concepts"][:2] for k in ("lighting", "category")]
    mood = ["night"] if sum(e in D.NIGHT_ENVS for e in envs) > len(envs) / 2 else []
    style, ranking = ST.select(envs, mood, recent_styles, prefer)
    pace = ST.PACE[style["pace"]]; fam = ST.CAMERA_FAMILIES[style["camera_family"]]
    n_scenes = len(story_dict["lines"]); emotion = (met["concepts"][0]["mood"] if met["concepts"] else "reflective")
    final_env = envs[-1]
    t = {"story_id": story_dict["id"], "style_id": style["id"], "style": style, "ranking": ranking,
         "questions": {"what_is_communicated": story_dict.get("theme", ""), "what_should_audience_feel": emotion,
                       "most_meaningful_visual": (met["concepts"][0]["visual_language"] if met["concepts"] else "environment of the cited source, treated with restraint"),
                       "silence_and_stillness": f"{int(round(style['silence_ratio'] * n_scenes))} narration-free scene(s) left with ambience only",
                       "opening_reveal": OPENINGS[style["camera_family"]], "final_image": f"held calm frame of {final_env.replace('_', ' ')} with the source attribution"},
         "metaphors": met, "pace": {"profile": style["pace"], "factor": pace, "min_hold_s": round(3.0 * pace + 0.8, 1)},
         "color": {"grade": style["grade"], "lighting": style["lighting"]}, "typography": {"personality": style["typography"], "palette": PERSONALITY_PALETTE[style["typography"]]},
         "camera": {"family": style["camera_family"], "styles": fam, "composition": style["composition"]},
         "transition": {"family": style["transition"], "color": ST.TRANSITION[style["transition"]]},
         "sound": {"silence_ratio": style["silence_ratio"], "ambience": "low" if style["silence_ratio"] else "normal", "music": False, "recitation_priority": True},
         "animation": style["animation"], "support": style["support"],
         "claims": "Creative visual direction only. Metaphors are not tafsir. No Prophet, Allah or sacred figure is ever depicted."}
    # silent (narration-free ambience-only) scenes: the quietest narration-only middle scenes, never the hook/verse/takeaway
    k = int(round(style["silence_ratio"] * n_scenes)); mid = [i for i in range(1, n_scenes - 1) if "narration" in story_dict["lines"][i]]
    t["sound"]["silent_lines"] = mid[len(mid) // 2: len(mid) // 2 + k] if k and mid else []
    return t

def save(db, t: dict) -> None:
    sid = t["story_id"]; ts = DBM.now()
    db.conn.execute("INSERT OR REPLACE INTO treatments VALUES(?,?,?,?)", (sid, t["style_id"], json.dumps(t, ensure_ascii=False), ts))
    db.conn.execute("DELETE FROM direction_log WHERE story_id=? AND kind IN ('style','style_category')", (sid,))
    db.conn.executemany("INSERT INTO direction_log(story_id,kind,value,ts) VALUES(?,?,?,?)", [(sid, "style", t["style_id"], ts), (sid, "style_category", t["style"]["category"], ts)])
    db.conn.commit()

def lighting_override(t: dict) -> dict:
    """Blender sun/sky parameters for this treatment's lighting (applied to daylight 3D scenes only)."""
    return dict(ST.LIGHTING.get(t["style"]["lighting"], {}))
