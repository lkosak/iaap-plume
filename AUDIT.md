# Audit

## Prototype attachment

The task pointed at `uploads/iowa_plume_pipeline.zip` (`/workspace/uploads/iowa_plume_pipeline_d6fc.zip`). That path was not on this machine: `/workspace` does not exist, and a filesystem search found no copy of the archive. There was no Streamlit app to launch and no `test_model.py` from the prototype to run.

What the task described, and what this version changes:

| Described prototype | What was wrong with relying on it | What shipped |
| --- | --- | --- |
| 2D random walk driven by one Open-Meteo wind | A single wind cannot describe transport from Middletown toward Fairfield and toward Illinois at the same time | Wind profiles on a 5×5 lattice, several heights, HRRR / RRFS / GFS |
| No ensemble | One draw hides timing, height, size, and forecast error | Members vary those inputs; the map shows the share of members |
| No deposition physics called out | Settling and washout change the surface footprint | Stokes settling, a simple dry velocity, rain scavenging — all labeled as assumptions |
| Streamlit map | Poor fit for a phone and for a static host | Static Next.js dashboard |
| A forecast archive CLI | Needed history kept across weather updates | Every snapshot is a new directory and is listed in `index.json` |

The EPA contour figures named in the task (0.18 µg/m³, 5 and 100 µg/ft²) were described as living in the missing README. They were not copied into this project. The model does not emit concentrations, so those contours are not drawn.

## HYSPLIT

Checked on 20 November 2026:

- Public download page: <https://www.ready.noaa.gov/HYSPLIT_linuxtrial.php>. The page requires an email acknowledgement. It also says the unregistered build will not run dispersion on forecast meteorology.
- Registered Linux builds require NOAA registration: <https://www.ready.noaa.gov/HYSPLIT_linux.php>.
- No `hycs_std` binary was on the system. `HYSPLIT_EXEC` was unset.
- The published maps are the screening ensemble, labeled **NOT HYSPLIT**. `docs/HYSPLIT.md` is the switch-on procedure. A trajectory `CONTROL` writer is tested; concentration output is not parsed, because that would mean pretending a format had been checked against the binary.

## Meteorology actually available

- Open-Meteo model id for HRRR is `ncep_hrrr_conus`. `hrrr_conus` is rejected.
- RRFS is `ncep_rrfs_conus`. NAM (`nam_conus`) is rejected; Open-Meteo documents NAM as discontinued on 2026-11-01.
- GFS (`gfs_seamless`) accepts 10 m, 80 m, and 925 / 850 hPa winds, boundary-layer height, and precipitation.
- Default Open-Meteo wind units are km/h. The client requests m/s and converts if the payload still says km/h. A unit test locks that conversion.
- Whether HRRR's file reaches Monday depends on the hour the snapshot runs. The ensemble drops any dataset that ends before the simulations finish and records the skip in the run JSON.

## Official pages

The fetcher tries EPA's emergency-permit notice, the EPA OSC profile, the Army advisory, the Army Sustainment Command notifications anchor, the Iowa HHS fact sheet, the Illinois EPA/IDPH PDF, and two news URLs (title only). A failed download stays in the list with `status: unavailable`. PDF bodies are not stored. News article bodies are not stored.

The live snapshot log is the current status; see the dashboard's official section for the last retrieval time in America/Chicago.

## Live snapshot, 20 November 2026, 9:51 AM CT

`python3 -m pytest -q` — 31 passed.

A real archive was written to `web/public/runs/20261120T155119Z` (and refreshed if a later id is `latest.json`).

- Engine: **NOT HYSPLIT**. `HYSPLIT_EXEC` is unset.
- Meteorology that covered Monday's window: GFS latest (10 m, 80 m, 925 hPa, 850 hPa) and GFS `previous_day1` (10 m and 80 m only).
- HRRR (`ncep_hrrr_conus`) was downloaded but its winds ended **2026-11-22 12:00 UTC**, before the Monday simulations, so it was not used. RRFS ended **2026-11-23 18:00 UTC** (noon CT), which does not cover an 8-hour run after a 2:00 PM CT release, so it was not used either. Later scheduled snapshots will pick them up when their valid times reach the window.
- Ensemble: 12 members, centered on noon CT Nov 23, window 10:00 AM–2:00 PM CT. Fairfield airborne overlap on this run: **0 of 12**. The relative airborne footprint lay mostly south-southwest of the installation. The nearest cell with any member was about 56 km from Fairfield. That is an overlap count, not a measurement.
- Official fetch: 8 of 8 URLs responded. EPA notice, EPA OSC profile, and the Army advisory returned excerpts. Iowa HHS and Illinois EPA/IDPH were PDF links (file not stored). CBS Chicago and ABC News titles were kept and not the article bodies. The Army page, as retrieved, still mentioned Friday; the CBS and ABC titles mentioned the delay / Monday. The dashboard shows both the schedule the model was built around and those retrieval flags.

## Prototype files re-sent individually

A follow-up said the originals were saved as `/workspace/uploads/README_4361.md`, `model_3413.py`, `app_ad38.py`, `run_snapshot_3a01.py`, `test_model_8816.py`, and `requirements_6c76.txt`. Those paths were not on this machine when checked (there is no `/workspace` directory). They were checked again after the ensemble was running. If they were still absent at commit time, `prototype/` was not invented and this paragraph is the record. Coordinates in use are the ones stated in the task (Fairfield 41.00761, -91.96369) and the OpenStreetMap installation centroid.

## Deployment

No GitHub, Cloudflare, Fly, or Render account was available to own a permanent host. The dashboard is running in this environment at http://127.0.0.1:43123 and, while the process stays up, at a temporary Cloudflare quick tunnel (no uptime guarantee; see the session report for the current hostname). GitHub Actions workflows are in the repo for when the owner pushes to GitHub and enables Pages. Details are in `README.md`.
