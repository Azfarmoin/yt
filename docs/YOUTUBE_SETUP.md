# YouTube OAuth setup
1. console.cloud.google.com → new project → enable **YouTube Data API v3**.
2. OAuth consent screen: External; add your Google account as a test user. To stop refresh tokens expiring after 7 days, set publishing status to **In production** (a sensitive-scope warning screen will appear for you only; that is fine for a personal app).
3. Credentials → Create **OAuth client ID** → type *Desktop app*. Copy the ID and secret into `.env` (copy `.env.example`).
4. `python -m ivs auth-youtube` → browser consent → the command prints `YOUTUBE_REFRESH_TOKEN=...`; paste it into `.env`.
5. Set `publishing.platforms.youtube.enabled: true` and keep `privacy: private` for the first test. `python -m ivs approve <id>` then `python -m ivs publish <id>`.
6. Quota: default 10,000 units/day; an upload costs 1,600 (local guard stops at 10,000/day, Pacific-time day). New API projects may have uploads locked private until an audit — check the current YouTube API policy.
Never commit `.env` or token files (both are in `.gitignore`).
