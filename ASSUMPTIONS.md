# Assumptions

Every number below is an assumption of this screening ensemble. None of them is a measured property of the detonation, and none of them is a concentration.

The colored footprint on every run is **NOT HYSPLIT**. When the trajectory layer is present it is labeled HYSPLIT trajectories (real HYSPLIT, forecast met) and is a separate NOAA HYSPLIT calculation. It is not a concentration.

The collapsed panel "Historical wind context (climatology, not a forecast)" is ERA5 reanalysis for 9 November–7 December, 2000–2025. It describes how often the wind in that calendar window has blown toward Fairfield. It is not a forecast for 23 November 2026, not a plume, and not an exposure estimate. The Monday forecast layers take precedence.

## Place

- The installation marker is the OpenStreetMap centroid of the Iowa Army Ammunition Plant, relation 13087513, retrieved 2026-11-20: **40.7858281, -91.2444371**.
- The installation outline used for release-point sampling is the same relation's bounding box: 40.7536225 to 40.8270411 N, -91.3098773 to -91.1798628 W.
- The permitted activity is an in-place detonation somewhere on the installation. A surveyed release coordinate was not in the sources this project could read, so each ensemble member draws a point inside that box.
- Fairfield, the requester's location, is **41.00761, -91.96369**. Distance and bearing on the map are measured from the installation centroid to that point.
- Fairfield is in Jefferson County. The installation is in Des Moines County, near Middletown. The street address on the EPA emergency-permit notice is 17571 Des Moines County Highway 79, Middletown, IA 52638-5000. That address is not used as the release point.

## When particles are released

- The date used for releases is **23 November 2026**.
- The Friday, Nov 20, about-noon CT plan was postponed to Monday, Nov 23 (reported by CBS Chicago and attributed to the Army). Members are centered on **noon America/Chicago**, with a window of **10:00, 11:00, 12:00 (twice), 13:00, and 14:00** because the Monday clock time can still change. The dashboard repeats that schedule change and shows whatever the latest official-page retrieval actually said.
- The two detonations described by the Army are treated as one release. A gap of minutes is smaller than the grid cell.
- Each member is followed for **8 hours**. That is longer than the Army's statement that visible dust may linger on the order of an hour, because smaller particles can stay aloft. It is still only a same-day regional window.

## Release height

- Heights used across members: **20 m, 30 m, 60 m, 150 m, 200 m, and 300 m** above ground.
- No plume-rise calculation is done. There is no yield and no heat release in this model. The heights are a spread of possibilities, not a predicted column.

## Particle size and density

- Diameters used across members: **2, 8, 10, and 25 µm**.
- Densities used across members: **2500, 3000, 6000, and 8000 kg/m³**. The high end is meant to stand in for lead-rich particles and the low end for lighter dust. The actual mix of particle sizes and densities was not published.
- Settling uses Stokes' law with a Cunningham slip correction (mean free path 0.065 µm, air viscosity 1.81×10⁻⁵ Pa·s).

## Meteorology

- Winds, boundary-layer height, and precipitation come from [Open-Meteo](https://open-meteo.com/), not from NOAA ARL files.
- Model ids requested: `ncep_hrrr_conus` (HRRR), `ncep_rrfs_conus` (RRFS), and `gfs_seamless` (GFS). NAM is not used; Open-Meteo lists it as discontinued on 2026-11-01. RRFS is the regional model Open-Meteo offers in its place.
- Wind speed is requested in meters per second (`wind_speed_unit=ms`). If a response still says km/h, speeds are divided by 3.6.
- A dataset is used only when its winds cover the release window through the end of the 8-hour simulations. HRRR's native horizon is short. If the downloaded HRRR field does not reach Monday, that run says HRRR was skipped. Later scheduled runs can pick it up once it does.
- Extra meteorology, when the download succeeds: a GFS cycle about 12 hours older (`run=` on the forecast API) and the Open-Meteo `previous_day1` GFS field (the forecast made about a day earlier for the same valid time).
- Points are a 5×5 lattice from 39.6–42.8 N and 93.6–89.6 W. Wind at a particle is an inverse-distance blend of those points, then a linear blend between wind levels (10 m, 80 m, and 925 and 850 hPa when those levels exist). Pressure-level heights are geopotential height minus the point's elevation.
- Resolved vertical wind from the forecast is not used. Vertical motion is mixing plus gravitational settling.
- Additional wind uncertainty on every member: a rotation of the wind vector (0°, ±15°, ±20°, or +25°) and a speed factor between 0.85 and 1.20. See the scenario table.

## Mixing

- Eddy diffusivity, in m²/s, depends on whether the particle is inside the boundary layer and whether the local hour is 08–17:

  | | inside the boundary layer, daytime | inside, nighttime | above the boundary layer |
  | --- | ---: | ---: | ---: |
  | horizontal K | 250 | 40 | 10 |
  | vertical K | 5 | 1 | 0.3 |

- Each member multiplies those values by a factor between 0.7 and 1.4.
- If boundary-layer height is missing, 400 m is used for that decision only.
- Particles reflect at 1 m and at 3000 m above ground. The lid is there because the downloaded winds do not describe the flow above the highest level we keep.

## Deposition

These are screening parameters, not fitted to IAAAP.

- Dry removal is applied only while a particle is in the lowest **20 m**. The deposition velocity is the settling speed plus **0.00015 m/s**, multiplied by the member's dry-deposition scale (0.4 to 1.5).
- The chance of removal during a step of length Δt is `1 - exp(-v_d Δt / 20)`.
- Wet removal, when the forecast has precipitation, uses `Λ = 5.0e-5 × wet_scale × P^0.8` per second, with P in mm per hour. It is applied below 2500 m when P > 0.05 mm/h. Wet scales across members run from 0.5 to 1.6.
- If a dataset has no precipitation field, wet removal is off for members that use it, and the run says so.
- Removed particles are counted on the deposition footprint at the horizontal position where they were removed. They do not carry a mass in micrograms.

## What each member is

Six release scenarios are crossed with every meteorological dataset that covers the window:

| Local start | Height | Diameter | Density | Dry scale | Wet scale | Mixing scale | Wind rotation | Speed factor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10:00 | 20 m | 2 µm | 2500 | 0.5 | 0.5 | 0.7 | 0° | 1.00 |
| 11:00 | 200 m | 10 µm | 8000 | 1.2 | 1.0 | 1.2 | +20° | 0.85 |
| 12:00 | 60 m | 25 µm | 8000 | 1.5 | 1.3 | 1.0 | −20° | 1.15 |
| 12:00 | 300 m | 2 µm | 3000 | 0.6 | 0.8 | 1.4 | +15° | 1.05 |
| 13:00 | 30 m | 8 µm | 6000 | 1.0 | 1.6 | 0.8 | −15° | 0.90 |
| 14:00 | 150 m | 2 µm | 2500 | 0.4 | 1.2 | 1.3 | +25° | 1.20 |

- 500 particles per member on a full run (tests use fewer).
- The random seed is fixed (`20261123` plus a member offset) so the same inputs can be rerun.
- The map grid is 0.08° (about 7–9 km): 32.16–49.44 N, 102.64–79.84 W, about 960 km from the installation in each direction.
- The same ensemble is run for Monday, Nov 23 through Friday, Nov 27, each day from 10:00 AM to 2:00 PM CT, because the detonation date is unannounced. A model that does not reach that day's window is left out of that day only.

## What is deliberately not assumed

- No released mass, no emission rate, and no conversion to µg/m³ or µg/ft².
- No comparison with any permit contour, including any contour that may have been written in the prototype README. Those figures were not in the files available here and are not repeated.
- No judgment about whether a place is or is not affected in the sense a health agency would use.
- Official Army, EPA, and state pages are stored beside the model. They are not inputs to the particle loop.

## Scenario table and code

If this file and `pipeline/ensemble.py` disagree, the code is what ran. The archive JSON for each run lists the members that actually executed.
