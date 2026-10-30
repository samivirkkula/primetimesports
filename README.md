# Urheilu-TV

A personal sports TV guide for iPhone. It shows only the sports I follow, with the Finnish service or channel each broadcast is on:

| Sport | Source | Shown as |
|---|---|---|
| Liiga | Liiga schedule API (`liiga.fi/api/v2/schedule`) | MTV Katsomo+ (all games, Finnish commentary) |
| Liiga free-to-air | MTV TV guide (GraphQL), `LIVE` programmes on MTV3 / Sub | MTV3 / MTV Sub, marked free |
| NHL | Viaplay schedule API (`content.viaplay.fi/pcdash-fi/urheilu/jaakiekko/nhl`) | Viaplay |
| NHL on Sub | MTV TV guide, `LIVE` programmes with "NHL" in the title | MTV Sub, marked free |
| NHL on Disney+ | Manual entries in `data/overrides.json` | Disney+ (marked with *) |
| NFL | Ruutu NFL page (`ruutu.fi/ohjelmat/nfl`, `/stream/` cards; "Selostus suomi" marks Finnish commentary) | Ruutu+ |
| NFL free-to-air | Elisa Viihde EPG API (`viihde-epg-api-prod.csf.elisa.fi/epg`), live NFL on Jim / Nelonen / Hero | Jim etc., marked free |
| F1, MotoGP, Moto2, Moto3 | Viaplay schedule API (`…/moottoriurheilu/<series>`) | Viaplay |
| Darts | Viaplay schedule API (path discovered from the sports landing page) | Viaplay |

The app is a static PWA. A GitHub Actions workflow fetches the sources every three hours, builds `schedule.json` and publishes the app with GitHub Pages. Opening the app never calls the providers' APIs.

## Structure

```
app/                  PWA: index.html, app.css, app.js, sw.js, manifest, icons, fonts
scraper/              Python 3.12, standard library only
  build.py            fetch → merge → site/schedule.json
  viaplay.py liiga.py mtv.py ruutu.py elisa.py   one module per source
config.json           sports, Viaplay paths, schedule length (14 days)
data/overrides.json   manual broadcasts (Disney+ etc.)
tests/                offline tests with fixtures
.github/workflows/update.yml
```

## Run locally

```sh
python3 -m unittest discover -s tests -t .   # offline tests
python3 -m scraper.build                      # fetch sources → site/schedule.json
cp -r app/. site/ && python3 -m http.server -d site 8000
```

`python3 -m scraper.build --cached` rebuilds from `.cache/` without network access.

## Publish

1. Create a GitHub repository and push this folder to `main`. GitHub Pages on a free account requires a **public** repository. The data is public broadcast information; nothing personal is published.
2. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Actions → *Päivitä aikataulu ja julkaise* → Run workflow.
4. On the iPhone: open `https://<user>.github.io/<repo>/` in Safari → Share → Add to Home Screen.

## Start-time window

`config.json` → `sports.<sport>.start_window` keeps only events that start inside the window in Finnish local time (inclusive), e.g. `["16:00", "23:00"]` for NHL and NFL. A 23.25 NFL game or a 02.00 NHL game is dropped. Remove the key to show all games.

## How merging works

- Each source becomes events with one or more broadcasts.
- A free-to-air or manual broadcast joins an existing event only when the sport matches, the broadcast starts at most 75 min before / 30 min after the event, and the titles share a team name. Ambiguous matches are not merged.
- Viaplay motorsport extra feeds (Onboard, Timing, Pitlane, Track Positioning) and replays are dropped.
- Finished events are hidden in the app; events past their end time are dropped at build.

## Resilience

The last successful result of each source is cached in `.cache/` (kept between workflow runs). If a source fails, data up to 48 hours old is used and the app footer says which source failed. If every source fails, the workflow fails and the previously published site stays up.

## Known gaps

- **NHL commentary language.** Viaplay's schedule list does not have an explicit language field. `scraper/viaplay.py: detect_language` looks for language arrays and Finnish/English commentary markers in the description. The build prints `nhl_viaplay_languages` (counts of `fi` / `en` / `None`); check it after the first real run and tune the patterns. Unknown-language games are hidden while the app's "NHL vain suomeksi selostettuna" toggle is on.
- **Disney+** has no public schedule; add confirmed Finnish-commentary games to `data/overrides.json` (remove `"_example": true`).
- **Viaplay API field names** are taken from public clients of the same API and are verified only against fixtures; the first live run is the real test.
- **Ruutu's NFL page** is parsed from HTML (link, title, time and commentary-language image). A site redesign breaks it; the cached result is used for 48 h and the app footer shows the failure.
- A free-to-air NFL broadcast whose guide title does not name the teams joins the single Finnish-commentary Ruutu game starting within 20 minutes; otherwise it is left out (see `.cache/match-report.json`).
- Darts' Viaplay path is discovered automatically; if discovery fails, set `viaplay.darts.path` in `config.json`.

## Fonts

VT323 and Archivo, self-hosted from Google Fonts under the SIL Open Font License (`app/fonts/OFL-*.txt`).
