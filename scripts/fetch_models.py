"""Downloads the free Kokoro English voice model (Apache-2.0, ~120 MB) into assets/models. Run once: python scripts/fetch_models.py"""
import sys, urllib.request
from pathlib import Path
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ["kokoro-v1.0.int8.onnx", "voices-v1.0.bin"]
dest = Path(__file__).resolve().parent.parent / "assets" / "models"; dest.mkdir(parents=True, exist_ok=True)
for f in FILES:
    p = dest / f
    if p.exists(): print("have", f); continue
    print("downloading", f); urllib.request.urlretrieve(BASE + f, p)
print("done")
