# GSPro test screens: sources and provenance

Collected 2026-10-04.

## Current GSPro release

- **Current release (non-beta): 3.1.6.20, dated 12/22/2025.** Source: official change log, https://gsprogolf.com/change-log.html (fetched 2026-10-04). The previous release was 3.1.6.13 (11/23/2025).
- Newer entries on that page are betas: `3.2.46 PUBLIC BETA - 6/24/2026` and `3.49.11.13 PUBLIC BETA - 10/01/2026` (Physics 2.0). A 3.49.11.15 public beta is also referenced in YouTube titles.
- **How betas are labelled:** "PUBLIC BETA" in the change log heading, with a `-PB` anchor suffix (e.g. `#v3-49-11-13-PB`). In game, the version number is shown at the bottom of the startup screen and the main menu (KB: https://gspro.gitbook.io/gspro-knowledge-base/setup-and-installation/how-to-download-the-gspro-public-beta). Beta players cannot play online with release players.
- **Visual tell:** the 3.49.x public beta is a Unity 6 rebuild with a redesigned UI (news: https://launchpointgolf.com/news/today-in-golf-tech-2026-04-18-gspro-unity-6/, 2026-04-18). The beta HUD has a "GS PRO" logo in the wind box, a course-name box with a hamburger menu ("Crooked River Ranch / Hole 2 Par 4 336 yds"), and a red player bar with numbered shot dots. The **release (v3.x) HUD** has a white box holding the hole number next to the course name, par and yardage, a four-dot menu button, and a player box with a red score badge. All images kept here show the release HUD.
- Note: `gspro.com` is an unrelated engineering firm's site. GSPro's official domain is `gsprogolf.com`.

## Videos (local only, in `video/`, gitignored)

| File | Source | Uploaded | Resolution | Version evidence |
|---|---|---|---|---|
| `video/20260131_Mixtape Golf_WkqTIug2YEI.mp4` | https://www.youtube.com/watch?v=WkqTIug2YEI ("GSPro Golf Simulator — Full Round at Palmer Hills Golf Course (No Commentary)", Mixtape Golf, Square Golf LM) | 2026-01-31 | 1280x720 (highest available) | The in-game scorecard footer shows `DATE: 1/31/2026`. On that date the current release was 3.1.6.20 (12/22/2025). The change log lists no public beta between that release and the April 2026 Unity 6 beta. Release-style HUD. Version is not stated in the title or description. **Likely 3.1.6.20 (high confidence that it is release, version number unconfirmed).** |
| `video/20260818_MyGolfQuest_DW-V70P-8_k.mp4` | https://www.youtube.com/watch?v=DW-V70P-8_k ("TPC Scottsdale ... Full Round \| GSPro - Sim Golf", MyGolfQuest, Square Golf Home Edition) | 2026-08-18 | 1920x1080 | The scorecard footer shows `DATE: 8/12/2026`. Public betas with the new UI existed by then, but this round shows the **old release HUD**, and the change log lists no release newer than 3.1.6.20. **Likely 3.1.6.20 (release; version number unconfirmed).** Units are metric (m, m/s). |

Both videos include a picture-in-picture swing camera inset (Mixtape: bottom-left, about 20% width; MyGolfQuest: left side, about 13% width). The inset does not cover the HUD: player box top-left, wind top-centre, hole box top-right, data tiles right, mini-map bottom-right. I found no recent release-UI video without any overlay. The cleanest no-inset video I found (Bogeys Backyard Golf, 2026-03-02, https://www.youtube.com/watch?v=gby51NfSvWs) shows the **new beta UI**, so it was deleted and excluded.

## Frames extracted from video

Times are seek offsets into the video (seconds, ±1 s). "Tiles" means the right-hand data tile panel.

### Mixtape Golf, Palmer Hills, 2026-01-31, 1280x720, imperial

| File | t (s) | What's visible |
|---|---|---|
| `mix_h1_tee_preshot_t0045.png` | 45 | Hole 1 tee before shot: player "Mixtape_Golf", Shot 1, 359.1 YDS to pin, score E, hole box "1 / Palmer Hills / PAR 4 / 359 YDS", wind 3 MPH, tiles zeroed, pin marker "359". |
| `mix_h1_drive_landed_label_t0059.png` | 59 | **Shot result:** drive just landed, on-ground label "88.3yd" (remaining to pin), tiles Carry(raw) 255.0, Carry(game) 271.0, Total 274.8, Ball speed 148.1, Spin 1903. Lie "Rough" on the mini-map. |
| `mix_h1_second_shot_hud_t0064.png` | 64 | Next-shot HUD: Shot 2, 84.8 YDS, ▲4.8 YDS elevation, "2nd (E)" badge, previous drive data still in tiles, pin marker "85". |
| `mix_h1_shot2_inflight_t0080.png` | 80 | Shot 2 in flight: tiles partially updated (Carry(raw) 86.4, Total "--.--"). Useful as a not-yet-landed negative example. |
| `mix_h1_putting_grid_t0100.png` | 100 | **Putting view:** green grid overlay, Shot 3, "10 FT 8", pin marker "10'8", lie "Green". |
| `mix_scorecard_after_h1_t0108.png` | 108 | **Scorecard:** Palmer Hills, all 18 holes par/index/distance, player row, footer with STIMP/TEES/PINS/GIMMES/WIND/DATE 1/31/2026. HUD shows hole 2, PAR 5, 504 YDS, score -1. |
| `mix_h2_tee_preshot_t0120.png` | 120 | Hole 2 tee before shot (par 5, 504 yds). |
| `mix_h2_shot4_hud_t0220.png` | 220 | Hole 2, Shot 4, 19.5 YDS, "4th (-1)", previous shot tiles (Carry 206.4/213.0, Total 222.3), pin marker "19". |

### MyGolfQuest, DPC Scottsdale (TPC Scottsdale), 2026-08-18 upload / 2026-08-12 round, 1920x1080, metric

| File | t (s) | What's visible |
|---|---|---|
| `mgq_h1_tee_preshot_t0005.png` | 5 | Hole 1 tee: player "MyGolfQuest", Shot 1, 317.9 m, score E, hole box "1 / DPC Scottsdale / PAR 4 / 318 m", 12-tile panel blank, two pin markers. |
| `mgq_h1_shot2_hud_after_drive_t0016.png` | 16 | HUD after drive settled: Shot 2, 98.2 m, "2nd (E)", lie Sand, full drive tiles (Carry 226.2/225.6, Total 232.0, Ball speed 249.9 km/h, Offline -55.6, Spin 2652). |
| `mgq_h1_approach_landed_tiles_t0025.png` | 25 | **Shot result:** approach landed on the green, "10.7m" label, gimme circle, tiles (Carry 86.2/94.4, Total 89.5). |
| `mgq_h2_shot2_hud_bunker_t0042.png` | 42 | Hole 2, Shot 2 from bunker, pin marker "150", tiles from the drive (Carry 204.8, Total 207.5). |
| `mgq_h9_shot_landed_bunker_label_t0256.png` | 256 | **Shot result:** ball landed near a bunker, "14.1m" label, hole 9 tiles. |
| `mgq_h9_approach_landed_green_circle_t0264.png` | 264 | **Shot result:** chip finished "3.2m" from the pin inside the gimme circle, hole 9 par 4 346 m, "3rd (+2)". |
| `mgq_scorecard_after_h9_t0269.png` | 269 | **Scorecard:** front 9 complete (37), footer DATE 8/12/2026, AUTO PUTT FIXED gimmes. |
| `mgq_h10_tee_distance_markers_t0272.png` | 272 | Hole 10 tee, score +2, pin/layup markers "236" and "338". |
| `mgq_h10_approach_landed_t0292.png` | 292 | Ball landed on the green with an auto-putt ring ("11.8m" label), tiles updated. |
| `mgq_h10_autoputt_green_t0293.png` | 293 | Same moment from the auto-putt camera ("AutoPutt 2" text on green). |

## Still image (official)

| File | Source page | Direct URL | Date | Version / recency |
|---|---|---|---|---|
| `kb_official_range_data_tiles_2025-07.png` | https://gspro.gitbook.io/gspro-knowledge-base/in-game-information/data-tiles | https://1446020469-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2F6x1BlySPbOTmTOIKshRM%2Fuploads%2FAb85OvRpenWnIIoO5gPH%2Fimage.png?alt=media&token=f6a47fe4-ef15-4702-ac2f-725088c081d5 | Uploaded 2025-07-24 (Firebase `timeCreated`) | Official KB, release v3 UI. Version not stated (3.1.x era, unconfirmed). Driving range, not in-round: 24 data tiles (Carry game/raw, Total length, Offline, Peak height, Spin, etc.), wind, club/hand panel, aim panel. 1917x1074. About 14 months old, slightly over the 12-month target. |

## Looked at and excluded

- GSPro KB "In Game User Interface" page screenshots (document360 CDN): the images now return 404, and their siblings date from Sep 2024 (about 2 years old).
- gsprogolf.com gallery (`assets/img/ingame/*.jpg`): the Last-Modified date (2026-10-01) is just the site redeploy. Capture date and version are unknown, so they were not used.
- Reddit r/Golfsimulator posts from 2025-2026: mostly phone photos of projector screens. The one clean screenshot (Aug 2026, round settings menu) is the new beta UI. Reddit's JSON API was blocked (403). RSS search worked but was heavily rate-limited.
- Bogeys Backyard Golf (2026-03-02), Handicap Golf "BETA Update" (2026-06-27), ILGolfManSteve SGT round (2026-10-04): all show the new beta UI, so they were excluded.
