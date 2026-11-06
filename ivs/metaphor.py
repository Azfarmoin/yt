"""Visual Metaphor Engine: finds abstract concepts in the VERIFIED script text and proposes visual language. These are creative
interpretations only; they are never presented as the meaning (tafsir) of an ayah or hadith."""
from __future__ import annotations
import re

LEXICON = {   # concept: (keywords, visual motifs, mood, preferred lighting, preferred categories)
 "patience":   (("patient", "patience", "persever", "steadfast", "endure", "hardship"), "enduring landscapes, long shadows, slow changing light", "steady, quiet", "golden_dawn", "cinematic_documentary"),
 "mercy":      (("mercy", "merciful", "compassion", "forgive"), "gentle sunlight on calm ground", "warm, gentle", "backlit_haze", "nature_cinematography"),
 "knowledge":  (("knowledge", "read", "pen", "taught", "learn", "reflect", "ponder", "think"), "light revealing intricate pattern detail", "curious, focused", "candle_warm", "geometric_islamic_design"),
 "gratitude":  (("grateful", "thank", "gratitude", "blessing", "favour", "fed", "provision"), "abundant nature, steady warm light", "content", "golden_dawn", "nature_cinematography"),
 "time":       (("time", "night", "day", "dawn", "era", "season", "year", "winter", "summer"), "moving shadows, changing skies", "reflective", "blue_hour", "atmospheric_storytelling"),
 "reflection": (("reflect", "still", "calm", "silence", "ponder", "remember"), "still water, wide quiet compositions", "contemplative", "blue_hour", "minimalist_editorial"),
 "hope":       (("hope", "relief", "ease", "dawn", "answer", "answered", "saved"), "dawn and a distant horizon", "hopeful", "golden_dawn", "cinematic_documentary"),
 "darkness":   (("darkness", "dark", "distress", "fear", "storm", "anguish"), "night sea, low light, weather", "tense, vulnerable", "storm_dusk", "atmospheric_storytelling"),
 "journey":    (("journey", "travel", "caravan", "path", "way", "march"), "long paths, tracking shots, changing terrain", "forward motion", "hard_noon", "procedural_3d"),
 "power":      (("army", "power", "strength", "mighty", "elephant", "plan"), "vast scale, low-angle approach", "weight, scale", "overcast_soft", "cinematic_documentary"),
 "accountability": (("account", "reckon", "judgment", "deeds", "weigh"), "symbolic paths, strong contrast", "serious", "overcast_soft", "abstract_symbolism")}

def analyse(text: str) -> dict:
    low = text.lower(); hits = []
    for c, (kw, motif, mood, light, cat) in LEXICON.items():
        n = sum(len(re.findall(r"\b" + re.escape(k), low)) for k in kw)
        if n: hits.append({"concept": c, "hits": n, "visual_language": motif, "mood": mood, "lighting": light, "category": cat})
    hits.sort(key=lambda h: -h["hits"])
    return {"concepts": hits[:4], "disclaimer": "Visual metaphors are creative interpretations, not the religious explanation of the text."}
