"""Visual style library: 112 styles = 14 categories x 8 parameter sets. A style is NOT a name: it is a vector of parameters that the
pipeline really consumes (camera families, lighting -> 3D sun/sky, typography palette, pacing, colour grade, transition colour,
silence ratio). The generator guarantees every pair of styles differs in >= 3 of 7 parameters (tested), so they are not relabeled
copies. `support`: 'full' = every environment the style uses is implemented; 'approximate' = the category asks for something the
engine cannot render faithfully yet (e.g. real architecture or maps), so it is drawn with the nearest implemented environments."""
from __future__ import annotations
import random, hashlib

LIGHTING = {  # name -> Blender world overrides (night/day) + the grade it pairs with
    "golden_dawn": dict(sun=7, sun_col=(1.0, 0.62, 0.34), sun_e=4.0), "blue_hour": dict(sun=-1.5, sun_col=(0.55, 0.65, 1.0), sun_e=1.2),
    "hard_noon": dict(sun=58, sun_col=(1.0, 0.95, 0.85), sun_e=4.5), "overcast_soft": dict(sun=30, sun_col=(0.85, 0.88, 0.95), sun_e=1.6, dust=0.5),
    "moonlit": dict(), "storm_dusk": dict(sun=3, sun_col=(0.5, 0.55, 0.6), sun_e=1.0, dust=6.0),
    "candle_warm": dict(sun=2, sun_col=(1.0, 0.5, 0.2), sun_e=2.0), "backlit_haze": dict(sun=11, sun_col=(1.0, 0.8, 0.55), sun_e=3.5, dust=5.0)}
CAMERA_FAMILIES = {"establishing": ["wide_establish", "crane_reveal", "high_descent", "pull_back"], "intimate": ["over_shoulder", "macro_feet", "low_push", "pedestal_pan"],
                   "sweeping": ["sweep_behind", "orbit_low", "dutch_arc", "push_through"], "contemplative": ["wide_establish", "pedestal_pan", "pull_back", "low_push"],
                   "still": ["wide_establish", "pedestal_pan"]}
TYPOGRAPHY = ["minimal_editorial", "classical_islamic", "luxury_documentary", "cinematic_calligraphy", "modern_educational"]
ANIMATION = ["slow_drift", "wind_driven", "water_flow", "geometric_drift", "parallax_layers", "stillness_with_light"]
PACE = {"meditative": 1.35, "measured": 1.0, "informative": 0.9, "dramatic": 0.8}
COMPOSITION = ["centered_symmetry", "low_horizon", "thirds_left", "thirds_right", "high_horizon", "framed_depth", "extreme_wide", "top_down"]
GRADES = ["filmic_natural", "warm_dawn", "cool_dusk", "documentary_muted", "soft_pastel", "deep_night", "high_clarity", "sepia_archive"]
TRANSITION = {"dip_black": "#000000", "warm_light": "#f1e2c0", "dusk": "#0b1226", "sand": "#c98b4f"}

CATEGORIES = {   # name: (environments it may use, technique, support, lighting pool, camera families, animations, grades)
 "cinematic_documentary": (["desert_dawn", "mountain_dawn", "sea_calm"], "blender_3d", "full", ["golden_dawn", "overcast_soft", "hard_noon", "backlit_haze"], ["establishing", "sweeping", "contemplative"], ["slow_drift", "wind_driven", "parallax_layers"], ["filmic_natural", "documentary_muted", "warm_dawn"]),
 "architectural_cinematography": (["geometric_night", "geometric_dawn", "mountain_dawn"], "geometric_2_5d", "approximate", ["candle_warm", "backlit_haze", "blue_hour"], ["contemplative", "still", "intimate"], ["geometric_drift", "stillness_with_light"], ["warm_dawn", "sepia_archive", "high_clarity"]),
 "nature_cinematography": (["desert_dawn", "sea_calm", "mountain_dawn", "sea_storm"], "blender_3d", "full", ["golden_dawn", "storm_dusk", "overcast_soft", "hard_noon"], ["establishing", "sweeping", "intimate"], ["wind_driven", "water_flow", "slow_drift"], ["filmic_natural", "high_clarity", "cool_dusk"]),
 "minimalist_editorial": (["sky_stars", "geometric_night", "desert_dawn"], "layered_2_5d", "full", ["blue_hour", "overcast_soft", "moonlit"], ["still", "contemplative"], ["stillness_with_light", "slow_drift"], ["documentary_muted", "soft_pastel", "deep_night"]),
 "abstract_symbolism": (["geometric_night", "geometric_dawn", "sky_stars"], "geometric_2_5d", "full", ["blue_hour", "candle_warm", "moonlit", "backlit_haze"], ["contemplative", "still"], ["geometric_drift", "stillness_with_light", "parallax_layers"], ["deep_night", "soft_pastel", "warm_dawn"]),
 "procedural_3d": (["desert_dawn", "mountain_dawn", "sea_calm"], "blender_3d", "full", ["golden_dawn", "hard_noon", "blue_hour"], ["sweeping", "establishing", "intimate"], ["parallax_layers", "wind_driven", "slow_drift"], ["filmic_natural", "high_clarity", "warm_dawn"]),
 "historical_cartography": (["desert_dawn", "geometric_dawn"], "layered_2_5d", "approximate", ["overcast_soft", "golden_dawn"], ["establishing", "contemplative"], ["slow_drift", "parallax_layers"], ["sepia_archive", "documentary_muted"]),
 "macro_cinematography": (["desert_dawn", "mountain_dawn"], "blender_3d", "approximate", ["backlit_haze", "golden_dawn", "hard_noon"], ["intimate"], ["wind_driven", "slow_drift"], ["high_clarity", "warm_dawn", "filmic_natural"]),
 "atmospheric_storytelling": (["sea_storm", "night_sea", "desert_night", "mountain_dawn"], "blender_3d", "full", ["storm_dusk", "moonlit", "blue_hour", "overcast_soft"], ["sweeping", "establishing", "contemplative"], ["water_flow", "wind_driven", "slow_drift"], ["cool_dusk", "deep_night", "documentary_muted"]),
 "motion_graphic_documentary": (["geometric_night", "sky_stars", "geometric_dawn"], "layered_2_5d", "full", ["blue_hour", "backlit_haze", "candle_warm"], ["sweeping", "establishing"], ["geometric_drift", "parallax_layers"], ["high_clarity", "filmic_natural", "cool_dusk"]),
 "geometric_islamic_design": (["geometric_night", "geometric_dawn"], "geometric_2_5d", "full", ["candle_warm", "blue_hour", "backlit_haze", "moonlit"], ["still", "contemplative", "intimate"], ["geometric_drift", "stillness_with_light", "parallax_layers"], ["warm_dawn", "deep_night", "sepia_archive", "soft_pastel"]),
 "photorealistic_environmental": (["desert_dawn", "mountain_dawn", "sea_calm"], "blender_3d", "approximate", ["golden_dawn", "hard_noon", "overcast_soft"], ["establishing", "sweeping"], ["slow_drift", "wind_driven"], ["filmic_natural", "high_clarity"]),
 "surreal_symbolic": (["sky_stars", "geometric_night", "night_sea"], "layered_2_5d", "approximate", ["moonlit", "blue_hour", "candle_warm"], ["still", "contemplative"], ["stillness_with_light", "water_flow", "geometric_drift"], ["deep_night", "soft_pastel", "cool_dusk"]),
 "educational_visualization": (["geometric_dawn", "sky_stars", "desert_dawn"], "layered_2_5d", "full", ["hard_noon", "overcast_soft", "backlit_haze"], ["establishing", "intimate"], ["parallax_layers", "slow_drift"], ["high_clarity", "documentary_muted", "filmic_natural"])}
KEYS = ("lighting", "camera_family", "typography", "animation", "pace", "composition", "grade")

def _build() -> list[dict]:
    out, seen = [], []
    for ci, (cat, (envs, tech, sup, lights, cams, anims, grades)) in enumerate(CATEGORIES.items()):
        rng = random.Random(1000 + ci); n = 0; tries = 0
        while n < 8 and tries < 20000:
            tries += 1
            v = dict(lighting=rng.choice(lights), camera_family=rng.choice(cams), typography=rng.choice(TYPOGRAPHY), animation=rng.choice(anims),
                     pace=rng.choice(list(PACE)), composition=rng.choice(COMPOSITION), grade=rng.choice(grades))
            if any(sum(v[k] != o[k] for k in KEYS) < 3 for o in seen): continue          # must differ from EVERY other style in >= 3 parameters
            seen.append(v); n += 1
            out.append(dict(id=f"{cat}-{n:02d}", category=cat, environments=envs, technique=tech, support=sup, **v,
                            transition=list(TRANSITION)[(ci + n) % 4], silence_ratio=[0.0, 0.15, 0.3][(ci * 3 + n) % 3],
                            name=f"{cat.replace('_', ' ')} / {v['lighting'].replace('_', ' ')}, {v['animation'].replace('_', ' ')}, {v['typography'].replace('_', ' ')}"))
    return out

LIBRARY = _build()
BY_ID = {s["id"]: s for s in LIBRARY}

def distance(a: dict, b: dict) -> int: return sum(a[k] != b[k] for k in KEYS)

def select(story_envs: list[str], mood_tags: list[str], recent: list[str], prefer: list[str] | None = None) -> tuple[dict, list[dict]]:
    """Choose a style for a story: environments must be usable, full support preferred, metaphor-preferred lighting/category rewarded,
    recently used styles/categories penalised (anti-repetition). Returns (style, ranking with scores)."""
    prefer = prefer or []; rows = []
    for s in LIBRARY:
        cover = sum(1 for e in set(story_envs) if e in s["environments"]) / max(len(set(story_envs)), 1)
        if cover < 0.5: continue
        sc = 3 * cover + (2 if s["support"] == "full" else 0) + (1.5 if s["lighting"] in prefer else 0) + (1.0 if s["category"] in prefer else 0)
        if "night" in mood_tags and s["lighting"] in ("moonlit", "blue_hour"): sc += 1
        if "night" not in mood_tags and s["grade"] == "deep_night": sc -= 3            # daylight stories should not get a night grade
        if "night" in mood_tags and s["grade"] in ("warm_dawn", "high_clarity", "sepia_archive"): sc -= 2
        if s["id"] in recent: sc -= 6
        elif any(r.rsplit("-", 1)[0] == s["category"] for r in recent[:3]): sc -= 1.5
        h = int(hashlib.sha1((s["id"] + "|".join(story_envs)).encode()).hexdigest()[:6], 16) / 0xFFFFFF       # deterministic tie-break
        rows.append((sc + 0.01 * h, s))
    rows.sort(key=lambda x: -x[0])
    if not rows: return LIBRARY[0], []
    return rows[0][1], [{"id": s["id"], "score": round(sc, 2)} for sc, s in rows[:5]]
