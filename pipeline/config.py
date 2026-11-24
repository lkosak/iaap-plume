"""Fixed places, dates, and grid. Narrative assumptions live in ASSUMPTIONS.md."""

from datetime import date

# OpenStreetMap relation 13087513, retrieved 2026-11-20.
# Centroid of the installation, not a surveyed detonation point.
SOURCE_NAME = "Iowa Army Ammunition Plant"
SOURCE_LAT = 40.7858281
SOURCE_LON = -91.2444371
# south, west, north, east — members sample release points inside this box.
SOURCE_BBOX = (40.7536225, -91.3098773, 40.8270411, -91.1798628)

FAIRFIELD_NAME = "Fairfield, Iowa"
FAIRFIELD_LAT = 41.00761
FAIRFIELD_LON = -91.96369

EVENT_DATE = date(2026, 11, 25)
# The clock time is unannounced. Screen all three afternoons the same way.
RELEASE_DATES = (date(2026, 11, 25), date(2026, 11, 26), date(2026, 11, 27))
TIMEZONE = "America/Chicago"

# Unattended forecast updates stop after the evening of Nov 27 CT.
UPDATE_UNTIL_UTC = "2026-11-28T06:00:00+00:00"

SIM_HOURS = 8
DT_SECONDS = 600
N_PARTICLES = 500
ENSEMBLE_SEED = 20261123

# About 960 km from the installation in each direction: a day of transport at
# about 11 m/s, and more than 300 km. 0.08° is about 7–9 km.
GRID_LAT_MIN = 32.16
GRID_LON_MIN = -102.64
GRID_DLAT = 0.08
GRID_DLON = 0.08
GRID_NLAT = 216  # through 49.44 N
GRID_NLON = 285  # through 79.84 W

# Forecast profiles sampled across that same window, including a point at the plant.
MET_LATS = (33.0, 36.0, 39.0, 41.0, 43.0, 46.0, 49.0)
MET_LONS = (-102.0, -98.0, -94.5, -91.2, -88.0, -84.0, -80.0)

# (Open-Meteo model id, short label). NAM ended 2026-11-01 and is not used.
MODELS = (
    ("ncep_hrrr_conus", "HRRR"),
    ("ncep_rrfs_conus", "RRFS"),
    ("gfs_seamless", "GFS"),
)

DISCLAIMER = (
    "These maps are relative model footprints from an unvalidated screening ensemble. "
    "They are not measurements of lead in air, soil, or dust, and they are not concentrations, "
    "doses, or a health determination. Follow instructions from the U.S. Army, U.S. EPA, "
    "Iowa HHS, and local emergency managers."
)

ENGINE_LABEL = "NOT HYSPLIT"
ENGINE_NAME = "screening-lagrangian-ensemble"
# The screening footprint keeps ENGINE_LABEL. These names are only for the
# separate HYSPLIT layers.
HYSPLIT_TRAJECTORY_LABEL = "HYSPLIT trajectories (real HYSPLIT, forecast met)"
HYSPLIT_HINDCAST_LABEL = "post-event hindcast"
HYSPLIT_HEIGHTS_M = (50, 250, 500)
HYSPLIT_RELEASE_HOURS_CT = (10, 11, 12, 13, 14)
# Public static build. The acknowledgement form is not stored here.
HYSPLIT_TARBALL_URL = (
    "https://www.ready.noaa.gov/data/web/models/hysplit4/linux_trial/"
    "hysplit.v5.4.2_x86_64_public.tar.gz"
)
HYSPLIT_TARBALL_SHA1 = "1e2de556b5794749c950770218751ab863d9f2ce"
ENGINE_SUMMARY = (
    "Relative footprints from a local Lagrangian ensemble driven by Open-Meteo wind "
    "profiles (NOAA HRRR, RRFS, and GFS, when each forecast covers the release window). "
    "This is not NOAA HYSPLIT and not a regulatory dispersion model."
)
