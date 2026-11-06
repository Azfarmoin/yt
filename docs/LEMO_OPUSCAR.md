# Lemo-Opuscar (github.com/lemomo-ai/lemo-opuscar, MIT)

What it is: a Claude Code **plugin/skill**. An AI agent directs a short film in code (Canvas/WebGL frames + FFmpeg) in one of 59 styles (each a `STYLE.md` prompt). It uses no video-generation model.

## What I added
- `third_party/lemo-opuscar/`: the 59 `STYLE.md` + `style.json` files and the MIT licence (about 1.6 MB; not the 197 MB of demo films).
- `python -m ivs lemo-styles`: ranks the styles by how figure-free they are (keyword density of faces/characters/figures/people and other-faith imagery). It is a rough text heuristic, not a review: read a style before using it. Swiss Motion, Countdown, Microscope, Satellite Briefing and LiDAR Survey rank best.
- `python -m ivs lemo-brief story:iqra --style swiss-motion --out brief.md` (or `quran:96:1-5`): writes a brief with our **verified Arabic/Urdu/English text, source credits and the hard religious rules** (no faces, no depiction of Allah/prophets/angels, text exactly as given, no synthetic Quran voice, no music over recitation).

## How to use it (on your PC)
1. `claude plugin marketplace add lemomo-ai/lemo-opuscar` then `claude plugin install lemo-opuscar@lemolab`.
2. Paste `brief.md` into Claude Code with the plugin and let it write `TREATMENT.md` first. Review the storyboard before it renders.
3. Supply an authentic recitation file yourself if the film includes Quran audio.

## Why it is not in GitHub Actions
It needs an LLM agent session per film (the README says 30-60 minutes and a fair amount of tokens), which is not free to run unattended, and the styles are tuned for Claude Opus 5.5. That breaks the $0 rule, so it stays a manual, optional premium path. The free daily pipeline is unchanged.

Not checked: I did not run the plugin. Several styles depict characters; the figure-density number does not make them safe, so keep the rule "faceless only" in every brief.
