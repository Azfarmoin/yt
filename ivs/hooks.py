"""Hook + title candidate generation, rule-based scoring, anti-repetition.
HONEST SCOPE: this is deterministic, template/author-driven text selection (no LLM). Scoring is a transparent heuristic that
filters out clickbait and repetition; it is not a judgement of religious accuracy and not a substitute for human editing."""
from __future__ import annotations
import re, json
from .dedupe import similarity

FORBIDDEN = [r"guarantee", r"secret", r"shocking", r"won'?t believe", r"nobody (knows|told)", r"100\s*%", r"\bmiracle\b",
             r"will make you (rich|wealthy)", r"you will be forgiven", r"definitely (go|enter) (to )?(paradise|jannah)",
             r"\bpunish", r"hell\b", r"or else", r"\bhidden truth", r"banned", r"they don'?t want you"]
EMOTION = {"struggling", "heavy", "alone", "afraid", "hope", "lost", "tired", "grateful", "hard", "darkness", "difficult", "patience", "mercy", "calm"}
QUESTION_WORDS = ("what", "why", "how", "which", "who", "have you", "do you", "can you", "is there", "did ")
CTAS = ["What lesson would you take from this?", "Save this reminder for a difficult day.", "Share this with someone who may benefit.",
        "Follow for more authentic Islamic stories and reminders.", "Which part stayed with you the most?", ""]   # "" = no call to action

def pattern(text: str) -> str:
    return " ".join(re.findall(r"[a-z']+", text.lower())[:3])

def used(db, kind: str) -> list[tuple[str, str]]:
    return [(r["text"], r["pattern"]) for r in db.conn.execute("SELECT text, pattern FROM style_log WHERE kind=?", (kind,))]

def hook_candidates(content) -> list[str]:
    th, ref = content.theme, content.reference_line
    base = [content.hook] if content.hook else []
    base += getattr(content, "hook_candidates_author", []) or []
    if content.category == "quran_ayah":
        base += [f"What does the Quran teach us about {th}?", f"How does the Quran speak about {th}?",
                 f"One ayah on {th}. Read it slowly.", f"Here is what {ref.split('(')[0].strip()} says about {th}.",
                 f"What can we learn from this ayah about {th}?"]
    elif content.category == "hadith":
        base += ["Which lesson does this Hadith teach us?", f"What does this authentic Hadith say about {th}?",
                 "What does faith look like in daily life?", f"One Hadith on {th}.", f"What can we learn from this narration about {th}?"]
    else:
        src = content.source.get("title", "this story")
        base += [f"What can we learn from {src}?", f"What does the Quran say in {src}?", f"A short story from the Quran: {src}.",
                 f"What is the message of {src}?"]
    seen, out = set(), []
    for h in base:
        k = h.strip().lower()
        if k and k not in seen: seen.add(k); out.append(h.strip())
    return out

def score_hook(h: str, content, history: list[tuple[str, str]], authored: set[str] | None = None) -> dict:
    words = re.findall(r"[\w']+", h)
    low = h.lower()
    forbid = [p for p in FORBIDDEN if re.search(p, low)]
    ctx = " ".join([content.theme, content.reference_line, json.dumps(content.source.get("title", ""))] +
                   [s.en for s in content.segments]).lower()
    rel = len({w.lower() for w in words if len(w) > 3} & set(re.findall(r"[a-z']+", ctx))) > 0
    if content.source.get("sequence"):          # whole-Quran walk: every hook names its own surah+verses, so only an exact repeat counts
        dup = any(t.strip().lower() == h.strip().lower() for t, _ in history)
    else:
        dup = any(p == pattern(h) for _, p in history) or any(similarity(h, t) > 0.8 for t, _ in history)
    c = {"curiosity": 1.0 if ("?" in h or low.startswith(QUESTION_WORDS)) else 0.5,
         "emotion": 1.0 if (EMOTION & set(re.findall(r"[a-z']+", low)) or re.search(r"\b(you|your)\b", low)) else 0.4,
         "relevance": 1.0 if rel else 0.0,
         "clarity": 1.0 if 4 <= len(words) <= 14 else 0.4,
         "natural": 0.0 if (h.isupper() or "!!" in h) else 1.0,
         "retention": 1.0 if "?" in h else 0.6}
    w = {"curiosity": 20, "emotion": 15, "relevance": 20, "clarity": 15, "natural": 10, "retention": 20}
    total = sum(c[k] * w[k] for k in w)
    if authored and h in authored: total = min(100, total + 12)          # hand-written by the author beats template filler
    return {"hook": h, "score": round(total), "criteria": c, "rejected": bool(forbid) or dup or not rel,
            "reason": ("forbidden pattern " + forbid[0]) if forbid else ("repeats an earlier hook/opening" if dup else ("not tied to the video's content" if not rel else ""))}

def select_hook(content, db) -> tuple[str, list[dict]]:
    hist = used(db, "hook")
    cands = hook_candidates(content)
    authored = {content.hook, *(getattr(content, "hook_candidates_author", []) or [])} - {""}
    scored = sorted((score_hook(h, content, hist, authored) for h in cands), key=lambda x: (x["rejected"], -x["score"]))
    ok = [s for s in scored if not s["rejected"]]
    chosen = ok[0]["hook"] if ok else None
    return chosen, scored

def title_candidates(content, chosen_hook: str) -> list[str]:
    th = content.theme.title(); ref = content.reference_line.split("(")[0].strip().rstrip(",")
    if content.category == "story":
        t = content.source["title"]
        c = [f"{t}: {th}", f"What {t} Teaches Us", f"{t} in One Minute", f"A Lesson from {t}", f"{th} | {t}"]
    elif content.category == "quran_ayah":
        c = [f"{th} | {ref}", f"What the Quran Says About {th}", f"{ref}: A Reminder on {th}", f"A Short Reminder on {th}", f"{th} in the Quran"]
    else:
        c = [f"A Hadith on {th}", f"{th} | {ref}", f"What This Hadith Teaches About {th}", f"One Hadith, One Lesson: {th}", f"{th} in Sahih al-Bukhari"]
    return [x[:92] for x in c]

def pick_title(cands: list[str], db) -> str:
    hist = [t for t, _ in used(db, "title")]
    for c in cands:
        if all(similarity(c, h) < 0.85 for h in hist): return c
    return cands[0]

def pick_cta(db, item_hint: int = 0) -> str:
    hist = [t for t, _ in used(db, "cta")][-3:]
    for i in range(len(CTAS)):
        c = CTAS[(item_hint + i) % len(CTAS)]
        if c not in hist: return c
    return ""

def log_style(db, item_id: int, hook: str, title: str, ending: str, cta: str) -> None:
    from .db import now
    rows = [("hook", hook, pattern(hook)), ("title", title, pattern(title)), ("ending", ending, pattern(ending)), ("cta", cta, "")]
    for kind, text, pat in rows:
        if text:
            db.conn.execute("INSERT INTO style_log(ts,kind,text,pattern,item_id) VALUES(?,?,?,?,?)", (now(), kind, text, pat, item_id))
    db.conn.commit()
