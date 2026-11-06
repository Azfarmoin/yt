"""AI script drafting for stories. The AI may only REPHRASE material it is given (the verified translation and the author's sourced notes).
Free + local: Ollama on the user's own PC (e.g. `ollama pull qwen2.5:3b`). Without it, a deterministic fallback drafts from the translation alone.
Every draft goes to content/stories/drafts/ and still needs HUMAN review before it is moved into content/stories/ (and again at approval)."""
from __future__ import annotations
import json, re
from pathlib import Path
import requests, yaml
from .quran import SURAH_NAMES
from .hooks import FORBIDDEN

ARABIC = re.compile(r"[؀-ۿ]")
QURANIC_MARKS = re.compile(r"[ؐ-ًؚ-ٟۖ-ٰۭ]")        # tashkeel/tajweed marks: never in AI-written lines
VISUAL_BAN = re.compile(r"\b(looked like|his face|her face|appearance of|handsome|beard|wearing|dressed in)\b", re.I)
STOP = set("the a an and of to in is was were are be been it its this that these those for with as by on at from or but not he she they them his her their we you our your who which what when then so than also into upon over after before about has have had will would can could may might do did does".split())

class Ollama:
    def __init__(self, url="http://localhost:11434", model="qwen2.5:3b", timeout=300):
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout
    def available(self) -> bool:
        try: return requests.get(self.url + "/api/tags", timeout=3).ok
        except Exception: return False
    def generate(self, prompt: str) -> str:
        r = requests.post(self.url + "/api/generate", json={"model": self.model, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0.4}}, timeout=self.timeout)
        r.raise_for_status(); return r.json()["response"]

PROMPT = """You write short narration for an Islamic story video. STRICT RULES:
- Use ONLY the SOURCE MATERIAL below. Do not add events, names, numbers, dates, causes or details that are not in it.
- Do not quote or write Arabic. Do not describe any prophet's appearance. Never invent hadith, scholars or opinions.
- If you are unsure, write less. Plain, calm English; Urdu must be simple and correct.
- No clickbait, no claims of certainty beyond the source.
Return JSON: {{"hook": "<one question, <= 12 words>", "hook_candidates": ["...","..."], "narration": [{{"after_ayah": <int>, "en": "...", "ur": "..."}}], "takeaway": {{"en": "...", "ur": "..."}}}}
Write 4 to 7 narration items, each 1-2 sentences, each tied to the source (after_ayah = the ayah number it follows, or 0 for the introduction).

TITLE: {title}
SOURCE MATERIAL (verified translation, then author's notes):
{source}
"""

def _content_words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", t.lower()) if w not in STOP}

def check_line(text: str, lang: str, corpus: str, support_min: float = 0.3) -> str | None:
    """Returns a rejection reason or None. Guards against invention, Arabic/Quran text, forbidden or visual-description language."""
    if not text.strip(): return "empty"
    if lang == "en" and ARABIC.search(text): return "Arabic text in English line"
    if QURANIC_MARKS.search(text): return "tashkeel/Quranic marks: AI must never write Quranic text"
    if any(re.search(p, text.lower()) for p in FORBIDDEN): return "forbidden clickbait/certainty phrase"
    if VISUAL_BAN.search(text): return "describes a person's appearance"
    if lang != "en": return None
    cw = _content_words(text); cc = _content_words(corpus)
    if cw and len(cw & cc) / len(cw) < support_min: return f"not supported by the source material ({len(cw & cc)}/{len(cw)} words)"
    for n in re.findall(r"\b\d[\d,\.]*\b", text):
        if n not in corpus: return f"number '{n}' not in source"
    for name in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{3,}\b", text):
        if name.lower() not in corpus.lower(): return f"name '{name}' not in source"
    return None

ENV_KEYS = [(("sea", "ship", "boat", "fish", "wave"), "sea_calm"), (("darkness", "night"), "night_sea"), (("mountain", "hill"), "mountain_dawn"), (("star", "sky", "heaven"), "sky_stars")]
ACT_KEYS = [(("elephant",), "army_march"), (("bird", "birds"), "flock"), (("journey", "winter", "summer", "caravan", "travel"), "caravan"), (("gather", "people", "crowd"), "crowd_gather")]

def _scene_action(text: str) -> tuple[str, str]:
    low = text.lower(); scene = next((s for ks, s in ENV_KEYS if any(k in low for k in ks)), "desert_dawn")
    return scene, next((a for ks, a in ACT_KEYS if any(k in low for k in ks)), "none")

def _fallback(title: str, sur: int, a1: int, a2: int, en: list[str]) -> dict:
    nm = SURAH_NAMES.get(sur, f"Surah {sur}"); n = a2 - a1 + 1
    return {"hook": f"What does {nm} ask us to reflect on?", "hook_candidates": [f"What can we learn from {nm}?", f"Have you reflected on {nm}?"],
            "narration": [{"after_ayah": 0, "en": f"{nm} has {n} ayat. Let us read them and reflect.", "ur": ""}],
            "takeaway": {"en": f"Reflect on the ayat of {nm} and what they teach us.", "ur": ""}}

def draft_story(quran, ref: str, story_id: str, title: str, theme: str, notes: list[dict] | None = None, llm=None, out_dir: Path | None = None) -> tuple[dict | None, dict]:
    """notes: [{"text": "...", "source": "Ibn Kathir, Tafsir of Surah ..."}] written/pasted by the human. Returns (story_dict, report)."""
    sur, rng = ref.split(":"); a1, _, a2 = rng.partition("-"); sur, a1, a2 = int(sur), int(a1), int(a2 or a1)
    rep = quran.verify(sur, a1, a2)
    if not rep["ok"]: return None, {"ok": False, "problems": rep["problems"]}
    en = quran.range_text("en", sur, a1, a2); notes = notes or []
    corpus = " ".join(en + [n["text"] for n in notes] + [title])
    src = "\n".join([f"Ayah {a1 + i}: {t}" for i, t in enumerate(en)] + [f"Note ({n['source']}): {n['text']}" for n in notes])
    report = {"ok": True, "mode": "fallback", "dropped": [], "problems": []}
    plan = None
    if llm is not None and (not hasattr(llm, "available") or llm.available()):
        try:
            plan = json.loads(llm.generate(PROMPT.format(title=title, source=src))); report["mode"] = "llm"
        except Exception as e:
            report["problems"].append(f"LLM failed, using fallback: {e}")
    if plan is None: plan = _fallback(title, sur, a1, a2, en)
    items = []
    for it in plan.get("narration", []):
        why = check_line(it.get("en", ""), "en", corpus) or (check_line(it["ur"], "ur", corpus) if it.get("ur") else None)
        if why: report["dropped"].append({"line": it.get("en", "")[:80], "why": why}); continue
        items.append(it)
    if report["mode"] == "llm" and len(items) < 3:                       # too little survived validation: do not ship a thin AI draft
        report["problems"].append("fewer than 3 narration lines passed validation; used fallback"); plan = _fallback(title, sur, a1, a2, en); items = plan["narration"]; report["mode"] = "fallback"
    hook = plan.get("hook", "")
    if check_line(hook, "en", corpus, 0.0): hook = _fallback(title, sur, a1, a2, en)["hook"]
    cands = [h for h in plan.get("hook_candidates", []) if h and not check_line(h, "en", corpus, 0.0)][:3] or _fallback(title, sur, a1, a2, en)["hook_candidates"]
    tk = plan.get("takeaway") or {}
    if check_line(tk.get("en", ""), "en", corpus) or (tk.get("ur") and check_line(tk["ur"], "ur", corpus)): tk = _fallback(title, sur, a1, a2, en)["takeaway"]
    lines = []
    for it in [i for i in items if int(i.get("after_ayah", 0)) <= 0]:
        sc, ac = _scene_action(it["en"]); lines.append({"scene": sc, "action": ac, "narration": {k: it[k] for k in ("en", "ur") if it.get(k)}})
    for i, a in enumerate(range(a1, a2 + 1)):
        sc, ac = _scene_action(en[i]); lines.append({"scene": sc, "action": ac, "quran": f"{sur}:{a}", "expect": next(iter(sorted(_content_words(en[i]), key=len, reverse=True)), "")})
        for it in [x for x in items if int(x.get("after_ayah", 0)) == a - a1 + 1]:
            sc2, ac2 = _scene_action(it["en"]); lines.append({"scene": sc2, "action": ac2, "narration": {k: it[k] for k in ("en", "ur") if it.get(k)}})
    story = {"id": story_id, "title": title, "theme": theme, "hook": hook, "hook_candidates": cands,
             "sources": [f"Quran {ref} ({SURAH_NAMES.get(sur, 'Surah ' + str(sur))})"] + [n["source"] for n in notes], "lines": lines, "takeaway": tk,
             "draft": {"generated_by": report["mode"], "needs_human_review": True}}
    report["lines"] = len(lines)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{story_id}.yaml").write_text("# DRAFT written by the script assistant. REVIEW every line against its source, then move to content/stories/.\n" +
                                                  yaml.safe_dump(story, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
    return story, report
