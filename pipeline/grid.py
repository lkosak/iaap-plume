"""Regular lat/lon accumulation grid. Row 0 is the south edge."""

from dataclasses import dataclass

import numpy as np

from pipeline.config import (
    GRID_DLAT,
    GRID_DLON,
    GRID_LAT_MIN,
    GRID_LON_MIN,
    GRID_NLAT,
    GRID_NLON,
)


@dataclass(frozen=True)
class Grid:
    lat_min: float = GRID_LAT_MIN
    lon_min: float = GRID_LON_MIN
    dlat: float = GRID_DLAT
    dlon: float = GRID_DLON
    nlat: int = GRID_NLAT
    nlon: int = GRID_NLON

    @property
    def lat_max(self) -> float:
        return self.lat_min + self.nlat * self.dlat

    @property
    def lon_max(self) -> float:
        return self.lon_min + self.nlon * self.dlon

    @property
    def shape(self) -> tuple[int, int]:
        return (self.nlat, self.nlon)

    def index(self, lat, lon):
        i = np.floor((np.asarray(lat) - self.lat_min) / self.dlat).astype(np.int32)
        j = np.floor((np.asarray(lon) - self.lon_min) / self.dlon).astype(np.int32)
        return i, j

    def inside(self, i, j) -> np.ndarray:
        return (i >= 0) & (i < self.nlat) & (j >= 0) & (j < self.nlon)

    def index_scalar(self, lat: float, lon: float) -> tuple[int, int]:
        i, j = self.index(lat, lon)
        i = int(i)
        j = int(j)
        if not (0 <= i < self.nlat and 0 <= j < self.nlon):
            raise ValueError(f"{lat}, {lon} is outside the grid")
        return i, j

    def as_dict(self) -> dict:
        return {
            "lat_min": self.lat_min,
            "lon_min": self.lon_min,
            "lat_max": self.lat_max,
            "lon_max": self.lon_max,
            "dlat": self.dlat,
            "dlon": self.dlon,
            "nlat": self.nlat,
            "nlon": self.nlon,
            "row_order": "south_to_north",
        }
