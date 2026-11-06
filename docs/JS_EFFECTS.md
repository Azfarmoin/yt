# JS effects layer (PixiJS, p5.js, GL Transitions, HyperFrames)

All four are free/open source, pinned in `js/package.json`, rendered **headless and deterministically** (seeded, time-driven) with software WebGL. Nothing is fetched at render time. Code: `js/fx.mjs`, `js/hf_frame/`, `ivs/jsfx.py`; hooks in `ivs/render.py`; switches under `js_fx:` in `config.yaml`.

| Library | Licence | What it does here |
|---|---|---|
| PixiJS 8 | MIT | Soft blurred light rays + drifting gold motes, seamless 6 s alpha loop over every video |
| p5.js 1.11 | LGPL-2.1 (used unmodified, loaded from node_modules) | Generative breathing 8-point star lattice as the background of `geometric_*` scenes (geometry only) |
| GL Transitions 3 | MIT (checked per shader by a test) | GLSL transitions at story scene boundaries: CrossWarp, Dreamy, DreamyZoom, SimpleZoom, CrossZoom, Bloom/Glow/SmokeDissolve, DefocusBlur, DirectionalWarp. Duration and audio sync unchanged |
| HyperFrames | Apache-2.0 | Renders an HTML/GSAP composition (animated geometric border, rotating corner stars) to an alpha MOV loop, used on Quran/hadith videos (stories already have their own frame). Telemetry is disabled |

## Setup
- Node 22+, then `cd js && npm ci` (once). In GitHub Actions the workflows do this step; if it fails the engine renders exactly as before (`continue-on-error`, and every effect is wrapped so a failure never loses the video).
- Chromium: `npx playwright install --with-deps chromium` (done in CI). On a machine with a Chrome you want to reuse, set `IVS_CHROME=/path/to/chrome`.
- Turn off: `js_fx: {enabled: false}`, or individually `transitions/pixi/frame/p5: false`.

## Honest notes
- Verified here: each effect renders (alpha, shaders compile, loop cached), and one full 73 s story render with all four on. The HyperFrames and Playwright browser download steps were **not** tested on a real GitHub runner.
- Cost: this added roughly 6-10 minutes to a 70-90 s story on 2 cores (transitions are the slow part: each one is a separate Chrome launch). Quran clips only add the overlay loops (cached after the first video).
- Software WebGL only; no GPU needed or used.
- Effects are decoration, never content: nothing here changes the verified text, recitation or subtitles.
