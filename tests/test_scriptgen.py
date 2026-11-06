import json
from ivs.quran import Quran
from ivs import scriptgen as G

class Fake:
    def __init__(self, plan): self.plan = plan
    def generate(self, prompt): return json.dumps(self.plan)

GOOD = {"hook": "What happened to the army that came with elephants?",
        "hook_candidates": ["What did the army with elephants face?"],
        "narration": [
            {"after_ayah": 0, "en": "Surah Al-Fil speaks about the companions of the elephant.", "ur": "سورۃ الفیل ہاتھی والوں کا ذکر کرتی ہے۔"},
            {"after_ayah": 3, "en": "The Lord sent against them flights of birds.", "ur": ""},
            {"after_ayah": 5, "en": "Their plan was made to go astray, says the surah.", "ur": ""},
            {"after_ayah": 5, "en": "Abrahah had 60,000 soldiers and a golden crown.", "ur": ""},          # invented: must be dropped
            {"after_ayah": 5, "en": "They said بِسْمِ in Arabic.", "ur": ""}],   # Arabic in English: dropped
        "takeaway": {"en": "Reflect on how the surah describes their plan going astray.", "ur": ""}}

def test_invented_and_arabic_lines_dropped(tmp_path):
    q = Quran()
    st, rep = G.draft_story(q, "105:1-5", "t1", "Surah Al-Fil", "x", [], Fake(GOOD), tmp_path)
    assert rep["mode"] == "llm" and len(rep["dropped"]) == 2
    why = " ".join(d["why"] for d in rep["dropped"])
    assert "not in source" in why or "not supported" in why or "name" in why
    assert st["draft"]["needs_human_review"] is True
    assert (tmp_path / "t1.yaml").exists()
    assert sum(1 for l in st["lines"] if "quran" in l) == 5          # verses come from the verified provider, never from the AI

def test_ai_cannot_write_quranic_marks_or_forbidden_phrases():
    assert G.check_line("بِسْمِ", "ur", "") is not None
    assert G.check_line("This is a shocking secret", "en", "shocking secret") is not None
    assert G.check_line("He looked like a tall man with a beard", "en", "tall man beard looked") is not None

def test_thin_llm_output_falls_back_to_deterministic(tmp_path):
    st, rep = G.draft_story(Quran(), "105:1-5", "t2", "Surah Al-Fil", "x", [], Fake({"hook": "?", "narration": [{"after_ayah": 0, "en": "Zorblax invented 12 kings.", "ur": ""}]}), tmp_path)
    assert rep["mode"] == "fallback" and st["lines"][0]["narration"]["en"]

def test_unverifiable_reference_refused():
    st, rep = G.draft_story(Quran(), "105:1-9", "t3", "x", "x", [], None)
    assert st is None and not rep["ok"]
