import json
from pathlib import Path
import pytest
from ivs import anim, content as C
from ivs.quran import Quran
from ivs.pipeline import Pipeline
from ivs.db import DB

def story(**kw):
    d = {"id": "t", "title": "T", "sources": ["Quran 105:1-5"], "_file": "t.yaml", "hook": "Hook?",
         "lines": [{"scene": "desert_dawn", "quran": "105:1-2", "expect": "elephant"}]}
    d.update(kw); return d

def test_story_verse_lines_are_pulled_from_verified_source():
    c, rep = C.build_story(story(), Quran())
    assert rep["ok"] and [s.label for s in c.segments] == ["Al-Fil 105:1", "Al-Fil 105:2"]
    assert c.needs_review and c.ayat == [(105, 1), (105, 2)]
    assert c.segments[0].ar == Quran().ayah("ar", 105, 1)            # exact source text, never author-typed Arabic

def test_story_rejects_wrong_reference_unknown_scene_and_missing_sources():
    q = Quran()
    assert not C.build_story(story(lines=[{"scene": "desert_dawn", "quran": "105:1-2", "expect": "mountain"}]), q)[0]
    bad = C.build_story(story(lines=[{"scene": "city_with_people", "narration": {"en": "x"}}]), q)[1]
    assert not bad["ok"] and "unknown scene" in bad["problems"][0]
    assert not C.build_story(story(sources=[]), q)[0]
    assert not C.build_story(story(lines=[{"scene": "sky_stars"}]), q)[0]          # neither quran nor narration

def test_scenery_never_contains_figures():
    allowed = {"dune", "wave", "cloud", "mist", "mountain", "pattern"}                          # landscape primitives only
    for tag, spec in anim.SCENES.items():
        assert {k for k, *_ in spec["layers"]} <= allowed, tag
        assert spec["orb"] is None or spec["orb"][0] in ("moon", "sun")

def test_story_renders_animated_faceless_video(cfg):
    cfg["audio"]["recitation"]["enabled"] = False; cfg["schedule"]["categories"] = ["story"]
    cfg["video"]["fps"] = 12                                                           # keep the test fast
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next(); it = p.db.get_item(i)
    assert it["status"] == "needs_review", it["error"]                                # stories never skip human review
    d = Path(it["video_path"]).parent
    qc = json.loads((d / "qc_report.json").read_text())
    st = {c["name"]: c["status"] for c in qc["checks"]}
    assert qc["passed"] and st["vfx_motion"] == "pass" and st["human_review"] == "warn"
    assert (d / "hook_w0.png").exists() and "#IslamicStories" in it["description"]
    assert (d / "thumbnail.jpg").stat().st_size > 5000

def test_actions_have_only_generic_faceless_actors():
    for name, inst in anim.ACTIONS.items():
        for sprite, *_ in inst:
            assert sprite in {"walker", "spearman", "traveller", "elephant", "bird"}, (name, sprite)
    assert not (set(anim.ACTIONS) & anim.FORBIDDEN_ACTORS)
    assert not (set(anim.AC.SPRITES) & anim.FORBIDDEN_ACTORS)

def test_unknown_or_sacred_action_is_rejected():
    q = Quran()
    for bad in ("prophet", "sahabi_walking", "allah"):
        c, rep = C.build_story(story(lines=[{"scene": "desert_dawn", "action": bad, "narration": {"en": "x"}}]), q)
        assert c is None and "unknown action" in rep["problems"][0]

def test_actor_sprites_have_no_facial_detail():
    from PIL import Image
    import numpy as np
    for fn in (lambda: anim.AC.walker(0.2), lambda: anim.AC.walker(0.6, spear=True)):
        a = np.array(fn())
        opaque = a[..., 3] > 200
        assert opaque.any() and a[opaque][:, :3].max() < 40      # uniformly dark silhouette: no light eye/mouth/feature pixels

def test_narrated_story_has_voice_ambience_and_label(cfg):
    from ivs import tts
    if not tts.kokoro_ready(): pytest.skip("Kokoro model files not present")
    cfg["audio"]["recitation"]["enabled"] = False; cfg["schedule"]["categories"] = ["story"]; cfg["video"]["fps"] = 12
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next(); it = p.db.get_item(i)
    d = Path(it["video_path"]).parent
    qc = json.loads((d / "qc_report.json").read_text()); st = {c["name"]: c["status"] for c in qc["checks"]}
    assert qc["passed"] and st["audio_audible"] == "pass" and st["narration_labeled"] == "pass"
    assert (d / "voice_hook_en.wav").exists() and (d / "ambience.wav").exists()
    assert "synthetic" in it["description"].lower()
    assert not list(d.glob("voice_*_ar.wav"))                                           # never any Arabic/Quran TTS
