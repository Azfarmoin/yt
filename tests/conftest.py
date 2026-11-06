import sys, subprocess, copy
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ivs.config import load_config
from ivs.db import DB

@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c = copy.deepcopy(c)
    c["paths"] = {"db": str(tmp_path / "t.sqlite3"), "output": str(tmp_path / "out"), "cache": str(tmp_path / "cache")}
    c["video"]["vfx"]["enabled"] = False         # fast tests; VFX has its own test
    c["script"]["require_review"] = False        # review gating has its own test
    return c

@pytest.fixture
def db():
    return DB(":memory:")

@pytest.fixture
def tone_mp3(tmp_path):
    p = tmp_path / "tone.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:a", "libmp3lame", str(p)], capture_output=True, check=True)
    return p
