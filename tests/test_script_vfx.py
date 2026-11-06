import json
from pathlib import Path
from ivs.catalog import QURAN, HADITH, SCRIPTS, script_for
from ivs.pipeline import Pipeline
from ivs.db import DB
from ivs import visuals as V

def test_every_script_belongs_to_a_catalog_entry_and_every_entry_has_one():
    keys = {f"quran:{s}:{a if a == b else str(a) + '-' + str(b)}" for s, a, b, *_ in QURAN}
    keys |= {f"hadith:{h['collection']}:{h['number']}" for h in HADITH}
    assert set(SCRIPTS) == keys
    for k, row in SCRIPTS.items():
        assert len(row) == 4 and all(x.strip() for x in row), k
        assert script_for(k)["reviewed"] is False             # nothing ships as scholar-reviewed by default

def test_script_scenes_in_video_and_script_json(cfg):
    cfg["audio"]["recitation"]["enabled"] = False
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next(); it = p.db.get_item(i)
    d = Path(it["video_path"]).parent
    sj = json.loads((d / "script.json").read_text(encoding="utf-8"))
    assert sj["context"]["en"] and sj["takeaway"]["ur"] and sj["reviewed"] is False
    assert (d / "s_ctx.png").exists() and (d / "s_take.png").exists()
    assert "editorial reflections, not tafsir" in it["description"]
    cues = (d / "subs.en.srt").read_text(encoding="utf-8")
    assert sj["context"]["en"] in cues and sj["takeaway"]["en"] in cues

def test_unreviewed_script_holds_item_for_review_by_default(cfg):
    cfg["audio"]["recitation"]["enabled"] = False; cfg["script"]["require_review"] = True
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next(); it = p.db.get_item(i)
    assert it["status"] == "needs_review" and "Editorial script" in it["review_reason"]

def test_script_can_be_disabled(cfg):
    cfg["audio"]["recitation"]["enabled"] = False; cfg["script"]["enabled"] = False
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next(); d = Path(p.db.get_item(i)["video_path"]).parent
    assert not (d / "s_ctx.png").exists()

def test_text_layer_has_clean_straight_alpha(tmp_path):
    sc = V.render_scene(tmp_path / "t.png", "x", "default", 3, title="Hello", ar="بِسْمِ ٱللَّهِ")
    from PIL import Image
    t = Image.open(sc.meta["text"]); assert t.mode == "RGBA"
    px = [p for p in t.getdata() if 0 < p[3] < 255][:500]
    assert px and all(p[0] > 90 for p in px)          # edge pixels keep ink color (no dark fringes)

def test_vfx_enabled_renders_motion_and_passes_qc(cfg):
    cfg["audio"]["recitation"]["enabled"] = False; cfg["video"]["vfx"]["enabled"] = True
    p = Pipeline(cfg, DB(":memory:")); i = p.make_next(); it = p.db.get_item(i)
    assert it["status"] == "rendered", it["error"]
    qc = json.loads((Path(it["video_path"]).parent / "qc_report.json").read_text())
    st = {c["name"]: c["status"] for c in qc["checks"]}
    assert st["vfx_motion"] == "pass" and qc["passed"]
