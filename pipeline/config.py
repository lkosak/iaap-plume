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

EVENT_DATE = date(2026, 11, 23)
TIMEZONE = "America/Chicago"

# Unattended forecast updates stop after the evening of Nov 24 CT.
UPDATE_UNTIL_UTC = "2026-11-25T06:00:00+00:00"

SIM_HOURS = 8
DT_SECONDS = 600
N_PARTICLES = 500
ENSEMBLE_SEED = 20261123

# Regional window: roughly Des Moines to western Illinois, Quincy to Iowa City.
GRID_LAT_MIN = 39.20
GRID_LON_MIN = -94.20
GRID_DLAT = 0.06
GRID_DLON = 0.06
GRID_NLAT = 70  # through 43.40 N
GRID_NLON = 90  # through 88.80 W

# Paired forecast points (cartesian product is built in met.fetch).
MET_LATS = (39.6, 40.4, 41.2, 42.0, 42.8)
MET_LONS = (-93.6, -92.6, -91.6, -90.6, -89.6)

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
ENGINE_SUMMARY = (
    "Relative footprints from a local Lagrangian ensemble driven by Open-Meteo wind "
    "profiles (NOAA HRRR, RRFS, and GFS, when each forecast covers the release window). "
    "This is not NOAA HYSPLIT and not a regulatory dispersion model."
)
