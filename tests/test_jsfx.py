import json, os, shutil, subprocess, tempfile
from pathlib import Path
import pytest
from ivs import jsfx

ok, why = jsfx.available()
needs_js = pytest.mark.skipif(not ok, reason=f"JS effects not installed: {why}")

def test_availability_is_a_clean_bool_and_config_off_wins():
    assert isinstance(jsfx.available()[0], bool)
    assert jsfx.enabled({"js_fx": {"enabled": False}}) is False

@needs_js
def test_all_curated_transitions_exist_and_are_mit():
    out = subprocess.run(["node", "-e", "const t=require('gl-transitions');console.log(JSON.stringify(t.map(x=>[x.name,x.license])))"], cwd=jsfx.JS, capture_output=True, text=True).stdout
    lib = dict(json.loads(out))
    for n in jsfx.GOOD_TRANSITIONS:
        assert n in lib, n
        assert "MIT" in (lib[n] or "MIT"), (n, lib[n])

@needs_js
def test_pixi_loop_has_alpha_and_is_cached(tmp_path):
    p = jsfx.pixi_loop(tmp_path, 180, 320, 6, seconds=2)
    assert p.exists() and jsfx.pixi_loop(tmp_path, 180, 320, 6, seconds=2) == p
    pix = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip()
    assert "a" in pix

@needs_js
def test_p5_clip_renders(tmp_path):
    p = jsfx.p5_clip(tmp_path, 180, 320, 6, 2)
    assert p.exists() and p.stat().st_size > 1000

def test_workflow_installs_node_deps():
    t = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "daily.yml").read_text()
    assert "setup-node" in t and "npm ci" in t
