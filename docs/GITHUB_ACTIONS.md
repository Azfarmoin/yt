# Running everything on GitHub Actions (free)

Three workflows in `.github/workflows/`:

| Workflow | When | What it does |
|---|---|---|
| `draft-scripts.yml` | Mondays 02:00 UTC (+manual) | Takes the next unused entry of `content/queue.yaml`, verifies the Quran text (SHA-256 pinned), drafts a story with a local Ollama model on the runner (falls back to deterministic wording), validates every line, opens a **pull request**. |
| `daily.yml` | every 2 hours (+manual); makes the slots that came due, 10/day spread 06:00-23:00 Karachi | Restores state, makes the next unique verified video (2.5D engine), runs QC, publishes **only if policy allows**, saves state, opens a review issue for anything waiting on you. |
| `approve.yml` | Owner comments `/approve N` or `/skip N` on any issue (+manual) | Rebuilds item N if needed, approves it and uploads to YouTube. |

## Setup (about 15 minutes, $0)
1. Push the project to a GitHub repo. Public = unlimited minutes; private = 2000 free min/month (a daily video takes ~10 min).
2. Run `python -m ivs auth-youtube` **on your own PC once** (see `docs/YOUTUBE_SETUP.md`). Put the three values in *Settings > Secrets and variables > Actions > Secrets*: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`. Without them, videos are still made and reviewed but nothing is uploaded.
3. Optional variable `IVS_YT_PRIVACY` (`private` default, `unlisted`, `public`). Start private.
4. *Settings > Actions > General > Workflow permissions*: read and write, and tick "Allow GitHub Actions to create pull requests".
5. Run `daily-video` manually once from the Actions tab.

## The human gate (hard rule, not configurable from CI)
- Stories, hadith and AI drafts **always** wait for you. A Quran ayah item auto-publishes only if it has no review flag; today the editorial context/takeaway lines are flagged, so in practice you approve everything until a qualified person reviews those lines.
- A drafted story has `draft.needs_human_review: true` and the loader **ignores it**. Merging the PR is not enough: you check the lines against the source, then delete that flag.
- Only the repository owner's comments count, only the exact form `/approve <digits>`; the comment reaches the job through an environment variable, never a shell line.

## Never the same video twice
- Every video's key (e.g. `quran:94:5-6`) is stored in SQLite; a key is never made again, and a near-duplicate text/ayah check runs too.
- Pool: 20 hand-curated ayah videos, hadith, your stories, then an automatic walk through **the whole Quran in order** (about 2,000 clips of 1-4 ayat, Juz Amma first). That is more than 5 years of daily videos.
- Those walk videos are recitation + verified translation only (no editorial lines), so they need no review and can auto-publish. They use a 70/100 engagement threshold instead of 80, because they deliberately have no takeaway line.
- If you don't approve items, new ones are still made each day (a waiting item is still "used").

## 10 videos a day
- Set the repo variable `IVS_VIDEOS_PER_DAY` (default 10).
- **YouTube's free quota allows about 6 uploads a day** (10,000 units; an upload plus thumbnail is 1,650). The engine therefore makes only as many videos as it can upload (6 by default), instead of building a backlog.
- To really get 10: request a free quota increase through Google's YouTube API quota-extension form, then set the variable `IVS_YT_QUOTA` to the new daily quota (20000 or more). Until Google approves it, don't set it.
- Minutes: 10 videos is about 100 runner-minutes a day. Fine on a public repo; a private repo's free 2000 min/month covers only about 6 a day for a week or so. Use a public repo.
- At 10/day the whole-Quran pool lasts about 200 days, not 5 years. Add stories and hadith to extend it.
- Posting 10 near-identical Shorts a day can look like spam to YouTube's systems; check your channel's reach and policies.

## State
SQLite history (what was made and published, so nothing repeats) lives on the orphan branch `ivs-state`, one force-pushed commit per run, using the built-in `GITHUB_TOKEN`. Runs share a concurrency group so two jobs never write at once. Video files are not stored: they are artifacts for 14 days, and `/approve` re-renders deterministically from the same verified source.

## Limits and honesty
- Nothing here was run against real GitHub or YouTube from my sandbox. Verified locally: command parsing, workflow YAML, state round-trip against a local git remote, `ci-run` and `ci-act` end to end with YouTube disabled.
- Runners have 2 cores and no GPU: 3D Blender shots are off in CI (2.5D only). Render 3D locally if you want it.
- Scheduled workflows can start late and GitHub disables them after 60 days without repo activity; the state commits don't count, so push anything occasionally.
- If your Google OAuth app is in *Testing* mode, the refresh token expires after 7 days. Publish the app (Production, unverified is fine for yourself) to avoid this.
- YouTube API quota: ~6 uploads/day on the free 10,000 units; the local guard prevents overrun.
- Edge voices stay off in CI unless you set `allow_edge`; recitation is never synthetic.
