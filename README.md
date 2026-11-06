# Islamic Video Engine (zero-cost)

Python pipeline that selects **verified, never-repeated** Islamic content (Quran ayat, Hadith, human-authored stories),
renders a 1080×1920 vertical MP4 with Arabic / Urdu / English text, runs automated QC, and (optionally) uploads to
YouTube through the official API. Everything runs locally with free tools. No paid API, no cloud rendering, no card.

## What works today (tested in this repo)
| Area | Status |
|---|---|
| Quran text: pinned checksums, 2-edition cross-check (all 6,236 ayat pass), Urdu + English, display-safe Arabic | ✅ tested |
| Hadith: fetch + number/book-ref/keyword checks + matn extraction; **always forced to human review** | ✅ tested (1 catalog entry) |
| Duplicate prevention: key, fingerprint, ayah overlap, near-duplicate similarity, rejection log | ✅ tested |
| Rendering: RTL shaping (libraqm), auto-fit with readability floor, chunking, SRT/VTT, thumbnail | ✅ tested |
| **VFX** (local, license-free): slow zoom/drift, drifting gold dust, animated text reveal; QC proves motion | ✅ tested (~80 s extra render per video on 2 cores) |
| **Animated faceless stories**: scenery only (parallax dunes/waves/mountains, moon/sun, clouds, stars), word-by-word hook, verse + narration scenes, verified Quran verses by reference | ✅ tested; 2 sample stories; always `needs_review` |
| **Narrated stories**: free local voices — English = Kokoro-82M (natural), Urdu = eSpeak NG (robotic; optional via `story_languages: [en, ur]`) — never used for Quran text | ✅ tested |
| **Faceless people**: silhouette soldiers/travellers/elephants/birds with walk cycles, tied to each scene's `action`; prophets/Companions never drawn (tests enforce) | ✅ tested (1 walk style only) |
| **Sound design**: synthesized footsteps, rumble, wing flutter, bird chirps, murmur, wind/surf ambience; silent under verses | ✅ tested (basic) |
| **Hook engine**: ≥5 candidates, forbidden-pattern + repetition filter, scored; 5 title candidates; varied CTA; anti-repetition log | ✅ tested (rule-based, no LLM) |
| **Two statuses** `religious_verification` / `content_quality`, engagement score ≥80, **claims audit table**, publish gate | ✅ tested |
| **Script stage**: hook → context → verse → takeaway → source, English + Urdu, saved as `script.json`, in SRT and description | ✅ tested; lines are editorial and **unreviewed → items wait in `needs_review`** |
| Audio: recitation download + FFmpeg mix/loudnorm/limiter | ✅ mixing tested with a stand-in tone; ⚠️ real recitation **not** fetched in build sandbox |
| QC (21 checks), resumable states, scheduler catch-up, pause/resume, CLI, dashboard | ✅ tested / smoke-run |
| YouTube upload (resumable, quota guard, duplicate guard) | ⚠️ unit-tested with a fake HTTP layer; **never run against a real account** |
| Instagram / Facebook / TikTok | ❌ not implemented (need app review + business accounts) |
| LLM-generated topics/scripts, Piper narration, Whisper alignment | ❌ not included (see docs/LIMITATIONS.md) |

## Install (Windows or Linux)
1. Python 3.10+, FFmpeg on PATH (`winget install Gyan.FFmpeg` / `apt install ffmpeg`).
2. `pip install -r requirements.txt` (Pillow's official wheels include libraqm; if `python -m ivs audit` says raqm missing on Linux: `apt install libraqm0`).
3. `python scripts/fetch_quran_data.py` (downloads the 4 Quran editions, validates them, verifies SHA-256 against `assets/data/MANIFEST.json`; on the very first run it creates the manifest - verify, then commit `assets/data/`), then `python scripts/fetch_models.py` (one-time, free English voice model, ~120 MB)
4. `python -m ivs init && python -m ivs verify-data && python -m ivs audit`
5. `python -m ivs make` → video in `output/<id>_<key>/video.mp4`; `python -m ivs list`.

## Daily use
- Approval mode (default): `python -m ivs make`, watch the video, `python -m ivs approve <id>`, `python -m ivs publish <id>`.
- Scheduler: `python -m ivs daemon` (or call `python -m ivs tick` from Windows Task Scheduler / cron every 15 min; missed slots are caught up).
- Dashboard: `python -m ivs dashboard` → http://127.0.0.1:8787 (approve/skip/re-render/pause, rejections, quota, audit).
- Script lines: edit `SCRIPTS` in `ivs/catalog.py`; after a qualified person reviews a key, add it to `SCRIPT_REVIEWED` so it can auto-publish. `script.require_review: false` skips the hold (not recommended).
- Effects: `video.vfx.*` toggles (or `enabled: false` for faster renders).
- Modes in `config.yaml → publishing.mode`: `approval` | `auto` | `draft`. Hadith/story items never auto-publish.
- Time zone/times/videos per day: `timezone`, `schedule.*`. Subtitle layouts: `video.subtitle_mode`.

## Recitation (important)
**Recitation is OFF until you set `audio.recitation.permission_verified: true`** (after reading the reciter/site's reuse and
monetization terms and writing what you checked in `permission_note`). Until then every Quran video is text-only and says so.
Reciter name comes from `reciter_display`; Murattal/Mujawwad is shown only if you set `style` yourself. Each ayah's complete
file is used unaltered (loudness-normalized only; no pitch, speed or reverb). Whole ayah is highlighted; word-level timing
is not attempted because no verified timing data is bundled.

Real recitation is fetched **on your PC** from EveryAyah (`audio.recitation`), one file per ayah, cached under `data/cache`.
If a file can't be obtained the video is rendered **text-only and says so on screen and in the description** — it never
substitutes TTS for recitation. Check the reciter's/site's terms yourself before monetizing.

## Review workflow (what "VERIFIED" means)
`religious_verification`: VERIFIED only when text/reference checks pass **and** nothing needs a person (hadith, stories and
unreviewed script lines are always NEEDS_HUMAN_REVIEW). `content_quality`: APPROVED when QC passes and the heuristic engagement
score is ≥80. Only VERIFIED + APPROVED items can be published; `python -m ivs approve <id>` records a human approval in the
`claims` audit table. Automated checks are not a scholar's review.

## Layout
`ivs/` engine · `assets/data` pinned Quran data + MANIFEST.json · `assets/fonts` OFL fonts · `content/stories` human-authored stories ·
`tests/` · `docs/` · `output/sample/` sample video.

## Stories (animated, no faces)
Write `content/stories/<id>.yaml` (see `_template.yaml.example` and the two included stories). Each line is either a verse
(`quran: "105:1-2"` + `expect:` keyword; text/translations come from the verified source) or your own `narration`, plus a
`scene:` (`desert_night`, `desert_dawn`, `sea_calm`, `sea_storm`, `night_sea`, `mountain_dawn`, `sky_stars`), a `hook:` and a
`takeaway:`. People, prophets and sacred figures are never drawn; the engine only has landscape and light primitives
(enforced by a test). Stories are never auto-published. Rendering takes ~2 min per video on 2 cores.

## Adding content
Quran/Hadith references live in `ivs/catalog.py` (references only; text always comes from the pinned/verified source, and each
entry needs an `expect` keyword so a wrong reference fails verification). Run `python -m ivs verify-data` after editing.


## 3D cinematic direction (Blender)

```
python -m ivs storyboard al-fil          # creative direction + storyboard + QC, stored in SQLite (storyboards, direction_log)
python -m ivs shot al-fil 1 --tier draft # render scene 1 in Blender -> output/shots/al-fil_s1_draft.mp4
```
Tiers: `draft` 360x640@12fps, `hd` 720x1280@24, `full` 1080x1920@24. See `docs/LIMITATIONS.md` items 27-31 for what is and is not done.

### Full 1-2 minute film with 3D shots
```
python -m ivs film al-fil --tier draft        # slow: renders the Blender shots (cached in output/film/cache/shots3d), then assembles the film
```
Cameras are smooth paths relative to the moving subjects (low push, crane reveal, high descent, lateral sweep, low orbit, over-the-shoulder, macro footsteps, pull-back, push-through, pedestal pan, arcing track, wide establishing). Anti-repetition: hooks are compared with earlier hooks, other shots with the last 14 camera moves.

## AI script, voices and daily automation
```
python -m ivs draft-story 105:1-5 --id al-fil2 --title "Surah Al-Fil" --notes notes.yaml   # needs `ollama serve` for AI mode; --no-llm for fallback
```
Set `audio.narration.allow_edge: true` for human-like Urdu/English narration (opt-in, online). Real Arabic tajweed = real reciter audio (`audio.recitation.permission_verified: true`).
Daily automation: `.github/workflows/daily.yml` (add YOUTUBE_* secrets).

## Cinematic universe layer
`python -m ivs hardware` (tier plan) - `python -m ivs audit` (cost + free-tier limits) - treatments are created automatically for every story render (`output/.../treatment.json`).
Modules: `director.py` (treatment), `styles.py` (112 parametric styles), `metaphor.py`, `grade.py`, `vqc.py` (visual QC), `thumbstudio.py`, `assets.py` (procedural Islamic geometric patterns + asset catalog), `hardware.py`.


## Fully automated on GitHub Actions
See `docs/GITHUB_ACTIONS.md`: weekly script drafting (PR), daily render + gated YouTube publish, `/approve N` chat-ops. All free.

## JS effects and Lemo-Opuscar
See `docs/JS_EFFECTS.md` and `docs/LEMO_OPUSCAR.md`.
