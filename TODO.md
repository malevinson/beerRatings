# BeerRated — Remaining Tasks

## Must Do Before Play Store Release

- [ ] fiinal bug testing
- [ ] **Deploy server to Railway** — push `server.py`, `Procfile`, `requirements-server.txt` to Railway and set `OPENAI_API_KEY` env var. See [README-server.md](README-server.md).
- [ ] **Update DEFAULT_SERVER_URL** — in `src/beerratingsmenuocr/ai_agent.py`, change `DEFAULT_SERVER_URL` from local IP to the Railway production URL.
- [ ] **Rebuild release APK** — after updating the server URL: `briefcase update android && briefcase build android`, then sign with gradle (`./gradlew assembleRelease`).
- [ ] **Test release APK end-to-end** — install on phone, scan a real menu, verify OCR + ratings work against the cloud server.
- [ ] **Enable GitHub Pages** — go to repo Settings → Pages → Source: "Deploy from a branch", Branch: `master`, Folder: `/docs`. This publishes the privacy policy at `https://mattlevinson.github.io/beerratingsmenuocr/`.
- [ ] **Play Store developer account** — sign up at https://play.google.com/console ($25 one-time fee).
- [ ] **Play Store listing assets** — take 2-3 screenshots of the app on your phone (home screen, scanning, results). Play Store requires at least 2 screenshots.
- [ ] **Play Store data safety form** — declare: no personal data collected, camera used for menu scanning, images sent to server for processing but not stored.
- [ ] **Submit to Play Store** — upload signed APK, fill in listing (descriptions already drafted in pyproject.toml), set content rating (everyone), link privacy policy URL.

## Nice to Have

- [ ] **App Store (iOS)** — requires Apple Developer account ($99/year). See [README-ios.md](README-ios.md).
- [ ] **Change keystore password** — current password is `beerrated123` in `build.gradle`. Consider using a stronger password.
- [ ] **Store listing screenshots** — create polished screenshots with device frames for the store page.
- [ ] **Fallback if server is down** — show a user-friendly error instead of a generic crash message.

## Completed

- [x] App icon (1024x1024, custom)
- [x] Release signing keystore
- [x] Privacy policy (HTML + Markdown in `/docs`)
- [x] Version set to 1.0.0
- [x] Settings/debug UI removed from production
- [x] Speed optimizations (image resize, JPEG compress, simplified prompt, gpt-4o-mini)
- [x] Sort during loading
- [x] Crash fix on "Scan Another"
- [x] Logo in home screen header
- [x] Server deployment docs (README-server.md)
- [x] Platform READMEs (Android, iOS)
- [x] Procfile + requirements-server.txt for cloud deploy
