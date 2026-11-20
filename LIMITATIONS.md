# What this can and cannot establish

## In one minute

This dashboard draws a **relative** picture of where a puff of particles **might** travel if the detonations happen on Monday and the weather forecast is roughly right. A colored cell means "this many of the imagined weather-and-release scenarios passed through here." It is **not a measurement** of lead in the air or on the ground. It does not say what is in anyone's yard, school, or lungs.

The U.S. Army, U.S. EPA, Iowa HHS, and your county emergency managers are the sources to follow. Their pages are linked in the official section of the dashboard. If they disagree with this map, follow them.

## What a color means

The main layer counts ensemble members. If 6 of 24 members put any airborne particle in a cell, the cell is 6 of 24. That is an overlap count.

A second layer shows where the same runs removed particles onto the surface, under the deposition assumptions in `ASSUMPTIONS.md`. A third layer shows the earliest and latest **first arrival** among members that reach the cell. Arrival times are model clocks, not observed arrival.

Fairfield's card uses the same counts for the grid cell that contains 41.00761, -91.96369, and for the eight cells around it. The grid is about 6 km across, so a puff that clips a corner can fall in a neighbor cell.

## What this cannot establish

- It cannot show that lead is present, and it cannot show that lead is absent. A cell with zero members is still not a measurement.
- It cannot give a concentration, a dose, or a comparison with a permit contour. No release mass is in the model, so those numbers cannot be computed honestly.
- It cannot replace a monitor, a wipe sample, or a blood-lead test.
- The colored footprint is not NOAA HYSPLIT. Trajectory lines are NOAA HYSPLIT only on the layer that says so. The post-event hindcast, when it exists, is a percent of that run's peak because the release mass is unknown. Details are in `docs/HYSPLIT.md`.
- The winds are forecast profiles at a few dozen points, blended between those points. They are not a full three-dimensional weather-model grid. Hills, the river, and the exact detonation column are not resolved.
- Particle size, density, release height, and deposition rates are spans we chose because the emitted mix was not published. A different span would move the deposition layer.
- Particles that leave the map window are counted in the run summary. Color at the edge of the map can be cut off.
- The release clock is a daytime window, not an announced hour. When the Army publishes an hour, the window in `pipeline/ensemble.py` should be narrowed and a new run archived.
- Official text shown in the dashboard is whatever the page returned at the time of that run. Pages change. The link is the source; the excerpt is a leftover of one download.

## How to read a change between runs

Later runs use later forecasts. A footprint that swings from one archive entry to the next is the forecast moving, or a model (often HRRR) becoming available for Monday. That swing is a reason to look again, not a measurement trend.

## What to do with it

Use it as an independent sketch of transport direction and of whether Fairfield sits inside this particular ensemble. Then read the Army plume products and the EPA and state notices, which this site does not replace.
