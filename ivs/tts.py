"""Free local narration for STORIES (never for Quran recitation).
 English: Kokoro-82M via kokoro-onnx (Apache-2.0 model + code), runs on CPU, no API.
 Urdu:    eSpeak NG 'ur' voice (GPL-3, bundled by espeakng-loader). Intelligible but clearly robotic: documented limitation.
Output is always labeled as synthetic narration in the description; it is never presented as a scholar's or reciter's voice."""
from __future__ import annotations
import ctypes, wave, struct
from pathlib import Path
from .config import ROOT

MODELS = ROOT / "assets" / "models"
_kokoro = None

def kokoro_ready() -> bool:
    return (MODELS / "kokoro-v1.0.int8.onnx").exists() and (MODELS / "voices-v1.0.bin").exists()

def speak_en(text: str, out_wav: Path, voice: str = "bm_george", speed: float = 0.95) -> float:
    global _kokoro
    import soundfile as sf
    from kokoro_onnx import Kokoro
    if _kokoro is None:
        _kokoro = Kokoro(str(MODELS / "kokoro-v1.0.int8.onnx"), str(MODELS / "voices-v1.0.bin"))
    samples, sr = _kokoro.create(text, voice=voice, speed=speed, lang="en-gb")
    sf.write(str(out_wav), samples, sr)
    return len(samples) / sr

def speak_ur(text: str, out_wav: Path, rate: int = 135, pitch: int = 45) -> float:
    import espeakng_loader as L
    lib = ctypes.CDLL(L.get_library_path())
    lib.espeak_Initialize.restype = ctypes.c_int
    sr = lib.espeak_Initialize(2, 0, L.get_data_path().encode(), 0)       # AUDIO_OUTPUT_SYNCHRONOUS
    if sr <= 0: raise RuntimeError("espeak init failed")
    if lib.espeak_SetVoiceByName(b"ur") != 0: raise RuntimeError("eSpeak has no Urdu voice")
    lib.espeak_SetParameter(1, rate, 0); lib.espeak_SetParameter(3, pitch, 0)  # rate, pitch
    chunks: list[bytes] = []
    CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)
    def cb(wav, n, ev):
        if wav and n > 0: chunks.append(ctypes.string_at(wav, n * 2))
        return 0
    cbf = CB(cb); lib.espeak_SetSynthCallback(cbf)
    b = text.encode("utf-8") + b"\0"
    lib.espeak_Synth(b, len(b), 0, 0, 0, 1, None, None)                   # espeakCHARS_UTF8 = 1
    lib.espeak_Synchronize(); lib.espeak_Terminate()
    pcm = b"".join(chunks)
    if not pcm: raise RuntimeError("eSpeak produced no audio")
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)
    return len(pcm) / 2 / sr

EDGE_VOICES = {"en": "en-GB-RyanNeural", "ur": "ur-PK-AsadNeural"}      # Microsoft neural voices through the free, unofficial edge-tts client
ENGINE_BY_LANG: dict[str, str] = {}                                       # which engine actually produced each language (for on-screen credits)

def edge_ready() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return False

def speak_edge(text: str, lang: str, out_wav: Path, voice: str | None = None, rate: str = "-5%") -> float:
    """Human-sounding neural voice. ONLINE and unofficial (Microsoft's read-aloud endpoint): only used when the user opts in
    (audio.narration.allow_edge: true) and never for Quran recitation. Falls back to local voices on any failure."""
    import asyncio, subprocess, edge_tts
    mp3 = out_wav.with_suffix(".edge.mp3")
    async def go(): await edge_tts.Communicate(text, voice or EDGE_VOICES[lang], rate=rate).save(str(mp3))
    asyncio.run(go())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(out_wav)], check=True)
    mp3.unlink(missing_ok=True)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out_wav)], capture_output=True, text=True).stdout
    return float(out.strip())

def narrate(text: str, lang: str, out_wav: Path, cfg: dict | None = None) -> float | None:
    """Returns duration or None when no engine is available (caller continues without voice).
    Order: Edge neural (only if opted in) -> Kokoro (en) / eSpeak NG (ur)."""
    nar = ((cfg or {}).get("audio", {}) or {}).get("narration", {}) or {}
    if nar.get("allow_edge", False) and edge_ready() and lang in EDGE_VOICES:
        try:
            d = speak_edge(text, lang, out_wav, (nar.get("edge_voices") or {}).get(lang), nar.get("edge_rate", "-5%"))
            ENGINE_BY_LANG[lang] = "Microsoft Edge neural voice"; return d
        except Exception:
            pass
    try:
        if lang == "en" and kokoro_ready(): ENGINE_BY_LANG[lang] = "Kokoro"; return speak_en(text, out_wav)
        if lang == "ur": ENGINE_BY_LANG[lang] = "eSpeak NG"; return speak_ur(text, out_wav)
    except Exception:
        return None
    return None
