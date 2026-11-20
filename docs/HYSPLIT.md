# Turning NOAA HYSPLIT on

The colored screening footprint is still labeled **NOT HYSPLIT**. A separate map layer, **HYSPLIT trajectories (real HYSPLIT, forecast met)**, is NOAA HYSPLIT when `hyts_std` from the public unregistered Linux build and an ARL forecast file are both available. Dispersion on forecast meteorology stays off. A **post-event hindcast** can run `hycs_std` on archived HRRR or NAM12 after Nov 23 and is stored as a percent of that run's peak, not as a concentration.

## Why it is off here

1. The public Linux download page, [HYSPLIT for Linux — unregistered](https://www.ready.noaa.gov/HYSPLIT_linuxtrial.php), requires an email acknowledgement of the [use agreement](https://www.ready.noaa.gov/HYSPLIT_agreement.php). There is no direct tarball link to fetch without that step. This environment did not submit an email.
2. NOAA states that the unregistered build is the same as the registered build **except that dispersion will not run on forecast meteorological fields**. A Monday forecast product needs forecast fields (HRRR, RRFS, or GFS). The unregistered binary cannot produce that product.
3. The registered Linux build is issued after [registration](https://www.ready.noaa.gov/HYSPLIT_register.php), from [HYSPLIT for LINUX](https://www.ready.noaa.gov/HYSPLIT_linux.php). Source access, if a prebuilt binary does not match the OS, is a separate request to `arl.webmaster@noaa.gov` and is not guaranteed.
4. `HYSPLIT_EXEC` was not set in this environment. `pipeline/hysplit.py` checks that variable on every snapshot and stores the result under `engine.hysplit_check`. `engine.is_hysplit` stays false.

`python -m pipeline.hysplit` is not a runner. The module exposes `check_hysplit()` and `write_trajectory_control()`.

## What is already implemented

- `check_hysplit()` runs whatever `HYSPLIT_EXEC` points at, with a 20-second timeout, and records whether the output says forecast dispersion is disabled.
- `write_trajectory_control()` writes a trajectory `CONTROL` file in the layout used by NOAA's trajectory runs and by the public `pysplit` writer: start time, one lat/lon/height, duration, vertical motion `0`, model top `10000.0`, meteorology directory and file, output name `tdump`. Tests cover that layout. Trajectory output is **not** a footprint and is **not** wired into the map.

Concentration setup (`hycs_std`, `cdump`, `con2asc`) is intentionally not guessed. The tutorial that creates a concentration `CONTROL` is the Concentration / Setup Run menu described at [the HYSPLIT tutorial](https://www.ready.noaa.gov/documents/Tutorial/html/test_conc.html). Confirm the file against a registered binary before trusting it.

## Steps for the owner

1. Read the use agreement and register: <https://www.ready.noaa.gov/HYSPLIT_register.php>.
2. Download the **registered** Linux build for this OS (Ubuntu-family, x86_64): <https://www.ready.noaa.gov/HYSPLIT_linux.php>. The unregistered build will not run Monday's forecast dispersion.
3. Install shared libraries the binary needs. On Ubuntu that is commonly `libnetcdff7`, `libeccodes0`, and an MPI library such as `libmpich12`. Check with `ldd` on `exec/hycs_std` and install whatever it lists as not found.
4. Download ARL-format forecast meteorology from NOAA ARL / READY. Useful starting points:
   - READY data index: <https://www.ready.noaa.gov/archives.php>
   - ARL FTP: `ftp://arlftp.arlhq.noaa.gov/archives/` and `ftp://arlftp.arlhq.noaa.gov/pub/archives/`
   - HRRR is the preferred short-range field while it is still produced (Open-Meteo lists HRRR as discontinued at the end of November 2026). GFS 0.25° ARL is the global fallback. READY's news page has said NAM and HREF ARL files were expected to stop on 6 October 2026, with RRFS ARL files as the replacement — confirm the live filenames on the FTP server the day you download.
5. Put the ARL files in one directory, for example `/var/lib/hysplit/met`.
6. Smoke-test a trajectory, which does not feed the map but proves the binary and the files:

   ```bash
   export HYSPLIT_EXEC=/opt/hysplit/exec/hyts_std
   python - << 'PY'
   from pathlib import Path
   from pipeline.hysplit import check_hysplit, write_trajectory_control
   print(check_hysplit())
   write_trajectory_control(
       Path("CONTROL"),
       year=2026, month=11, day=23, hour=14,
       lat=40.7858281, lon=-91.2444371, height_m=50,
       hours=8, met_dir="/var/lib/hysplit/met", met_files=["YOUR_FILE.arl"],
   )
   PY
   # From the directory that contains CONTROL, run hyts_std and confirm tdump exists.
   ```

7. To publish a HYSPLIT footprint, a concentration run has to be added on top of that smoke test:
   - Working directory with `CONTROL` and `SETUP.CFG` (`numpar` around 500–2500 is the tutorial's order of magnitude).
   - Meteorology path in `CONTROL`.
   - Run `hycs_std` (the concentration executable in the registered `exec/` directory).
   - Convert `cdump` with `con2asc` (ships with HYSPLIT).
   - Normalize the ASCII grid to a **share of members or a relative particle density**. Do not publish the raw concentration units. This project has no validated release mass.
   - Set `engine.is_hysplit` to true only after that file parses, and set `engine.label` to `HYSPLIT` plus the ARL filename and cycle. Keep the same disclaimer: the result is still not a measurement.
8. Re-run `python -m pipeline.run_snapshot --out web/public/runs`. Until step 7 is actually coded and green, the snapshot will keep the screening ensemble and will keep saying `NOT HYSPLIT`. That is intentional.

## Meteorology the screening ensemble uses instead

Open-Meteo serves HRRR (`ncep_hrrr_conus`), RRFS (`ncep_rrfs_conus`), and GFS (`gfs_seamless`) as point profiles. That is documented in `ASSUMPTIONS.md`. It is not a substitute label for HYSPLIT.
