import subprocess
from pathlib import Path
from ivs import styles as S, hardware as HW, metaphor as MT, director as DR, vqc, assets, audit
from ivs.content import load_stories, build_story
from ivs.quran import Quran

STORIES = load_stories(Path(__file__).resolve().parent.parent / "content" / "stories")

def test_style_library_size_and_distinctness():
    assert len(S.LIBRARY) >= 100 and len({s["category"] for s in S.LIBRARY}) == 14
    assert min(S.distance(a, b) for i, a in enumerate(S.LIBRARY) for b in S.LIBRARY[i + 1:]) >= 3
    assert all(s["grade"] in __import__("ivs.grade", fromlist=["x"]).PROFILES for s in S.LIBRARY)

def test_hardware_tiers_and_overrides():
    assert HW.detect()["tier"] in ("LOW", "MEDIUM", "HIGH")
    low = {"cpu_threads": 2, "ram_gb": 8, "gpu": {"vram_gb": 0}, "disk_free_gb": 50, "tier": "LOW", "low_disk": False}
    assert HW.effective_three_d({"three_d": {"tier": "auto"}}, low)["max_seconds"] == 12
    assert HW.effective_three_d({"three_d": {"max_seconds": 40}}, low)["max_seconds"] == 40
    assert HW.effective_three_d({"three_d": {"enabled": False}}, low)["enabled"] is False

def test_metaphor_is_labelled_interpretation():
    m = MT.analyse("He called out in the darkness and was answered; hope and relief followed")
    assert {c["concept"] for c in m["concepts"]} >= {"darkness", "hope"} and "not the religious explanation" in m["disclaimer"]

def test_treatments_differ_and_do_not_repeat_style(db):
    q = Quran(); seen = []
    for st in STORIES:
        c, _ = build_story(st, q); t = DR.treat(c, st, db); DR.save(db, t); seen.append(t)
        assert t["sound"]["music"] is False and "No Prophet" in t["claims"]
    assert len({t["style_id"] for t in seen}) == len(seen)
    assert len({(t["color"]["grade"], t["typography"]["personality"]) for t in seen}) >= 2

def test_assets_registered_with_license(db):
    aid = assets.register(db, "pattern", "star8", {"cell": 180})
    r = db.conn.execute("select license, provenance from assets where asset_id=?", (aid,)).fetchone()
    assert "CC0" in r[0] and r[1]
    assert assets.pattern_tile(180, "#d9b36a", 60, 1080, 400).size == (1080, 400)

def test_visual_qc_detects_black_and_flicker(tmp_path):
    ok = tmp_path / "ok.mp4"; bad = tmp_path / "bad.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=216x384:rate=24:duration=8", "-pix_fmt", "yuv420p", str(ok)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:size=216x384:rate=24:duration=8", "-pix_fmt", "yuv420p", str(bad)], check=True)
    tl = [{"start": 0, "dur": 8, "kind": "scene"}]
    assert vqc.analyse(str(ok), tl)["ok"]
    r = vqc.analyse(str(bad), tl); assert not r["ok"] and any(c["name"] == "black_frames" and c["status"] == "fail" for c in r["checks"])

def test_cost_auditor_flags_paid_package(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests\nopenai>=1.0\n"); (tmp_path / "ivs").mkdir()
    res = {n: s for n, s, _ in audit.paid_scan(tmp_path)}
    assert res["paid_python_packages"] == "fail" and res["credit_card_or_payment"] == "pass"
