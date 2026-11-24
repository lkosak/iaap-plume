# IAAAP plume screening

Independent, relative-footprint dashboard for the planned lead-azide controlled detonations at the Iowa Army Ammunition Plant near Middletown, Iowa, on **23 November 2026**. Fairfield, Iowa (41.00761, -91.96369) is marked on the map.

The maps count how many ensemble scenarios pass over a cell. They are **not measurements of lead**, not concentrations, and not a health determination. Read `LIMITATIONS.md` before using a run. The model is **not NOAA HYSPLIT**; see `docs/HYSPLIT.md` and `ASSUMPTIONS.md`.

Official Army, EPA, and state pages are shown in a separate section of the dashboard. Follow those agencies and local emergency managers.

## Run it locally

One command from the repository root:


```bash
./scripts/run_local.sh
```

That installs Python dependencies, runs the tests, creates a forecast archive if `web/public/runs/latest.json` is missing, and starts the site at <http://127.0.0.1:43123>.

Pieces, if you want them separately:

```bash
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q
python3 -m pipeline.run_snapshot --out web/public/runs
cd web && npm ci && npm run dev
```

A snapshot needs outbound HTTPS to Open-Meteo and to the agency pages. If a download fails, the previous archive is left in place.

## What a run stores

Each snapshot writes a new directory under `web/public/runs/<run id>/`:

- `run.json` — footprints, member list, Fairfield counts, official-page excerpts, timestamps in America/Chicago
- `met.npz` — the wind profiles used, so the run can be inspected later

`web/public/runs/index.json` lists every run. `latest.json` is the newest one. Older directories are not deleted.

## Scheduled updates

Unattended updates are intended every two hours through the evening of **24 November 2026** (the script exits after 2026-11-25 06:00 UTC unless you omit `--honor-deadline`).

On this machine, or any always-on host:

```cron
10 */2 * * * cd /path/to/this/repo && ./scripts/scheduled_update.sh >> /tmp/iaaap-screening.log 2>&1
```

`scripts/scheduled_update.sh` runs `python -m pipeline.run_snapshot --out web/public/runs --honor-deadline`.

GitHub Actions, if you push this repo to GitHub:

- `.github/workflows/test.yml` runs pytest on push.
- `.github/workflows/forecast.yml` runs the snapshot every two hours through the evening of 27 November 2026 CT, and on manual dispatch. It appends a directory under `web/public/runs/` and commits it. Each run requests the newest Open-Meteo HRRR and RRFS cycles and uses them only when their valid times cover the Monday window. It also runs NOAA HYSPLIT trajectories on ARL forecast files (HRRR, then NAM, then GFS) for releases from 10:00 AM to 2:00 PM CT at 50, 250, and 500 m. A push from this workflow does not start other workflows, so the same job builds the static export and deploys GitHub Pages.
- `.github/workflows/hindcast.yml` runs on 24–26 November at 9:10 AM and 3:10 PM CT, and on manual dispatch through 27 November. It writes `web/public/hindcast/` only after archived HRRR or NAM12 meteorology covers the Nov 23 window. The field is a percent of that run's peak.
- `.github/workflows/pages.yml` publishes the static site when `main` changes outside that forecast commit. Enable Pages with source **GitHub Actions**. The build sets `NEXT_PUBLIC_BASE_PATH=/iaap-plume`.

## Deploy a public URL

The site is a static Next.js export (`web/out` after `npm run build`). Pick one host.

### GitHub Pages

1. Push this branch to the public repository `lkosak/iaap-plume`.
2. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. The forecast workflow sets its own `contents: write` permission. If a push is rejected, Settings → Actions → General → Workflow permissions → **Read and write**.
4. Confirm `.github/workflows/pages.yml` and `forecast.yml` are on `main`.
5. Run the forecast workflow once from the Actions tab. It appends a run and deploys the site.
6. The Pages URL is <https://lkosak.github.io/iaap-plume/>.

### Cloudflare Pages

1. Push the repo to GitHub or GitLab.
2. Cloudflare dashboard → Workers & Pages → Create → Pages → Connect the repo.
3. Root directory: `web`. Build command: `npm ci && npm run build`. Output directory: `out`.
4. The forecast still has to run somewhere that can commit `web/public/runs` (the GitHub Action above, or cron on a machine you control) and push, so Pages rebuilds. Cloudflare will not run the Python model by itself with this setup.

### Any static host

```bash
python3 -m pipeline.run_snapshot --out web/public/runs
cd web && npm ci && npm run build
```

Upload the contents of `web/out`. Repeat the two commands on a schedule and re-upload, or automate the upload with the host's CLI once you have a token.

`./scripts/run_local.sh` serves the same dashboard at the site root, without the GitHub Pages base path.

## Tests

```bash
python3 -m pytest -q
```

Covers meteorology parsing (including km/h → m/s), settling and advection, ensemble overlap, the run archive, official-page failures, and the HYSPLIT detector. Live downloads are not part of pytest; `python3 -m pipeline.run_snapshot` is the live check.

## Layout

- `pipeline/` — forecast download, particle ensemble, archive, official-page fetch
- `web/` — phone-first dashboard
- `tests/` — unit tests
- `ASSUMPTIONS.md`, `LIMITATIONS.md`, `AUDIT.md`, `docs/HYSPLIT.md`
