"""Distance and bearing on a sphere. Good to about a kilometer at this scale."""

import numpy as np

_EARTH_M = 6_371_000.0
_CARDINALS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)
_CARDINAL_WORDS = {
    "N": "north",
    "NNE": "north-northeast",
    "NE": "northeast",
    "ENE": "east-northeast",
    "E": "east",
    "ESE": "east-southeast",
    "SE": "southeast",
    "SSE": "south-southeast",
    "S": "south",
    "SSW": "south-southwest",
    "SW": "southwest",
    "WSW": "west-southwest",
    "W": "west",
    "WNW": "west-northwest",
    "NW": "northwest",
    "NNW": "north-northwest",
}


def haversine_km(lat1, lon1, lat2, lon2):
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(np.asarray(lat2) - np.asarray(lat1))
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * _EARTH_M * np.arcsin(np.sqrt(a)) / 1000.0


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return float((np.degrees(np.arctan2(y, x)) + 360.0) % 360.0)


def cardinal(bearing: float) -> str:
    idx = int((bearing + 11.25) // 22.5) % 16
    return _CARDINALS[idx]


def cardinal_word(bearing: float) -> str:
    return _CARDINAL_WORDS[cardinal(bearing)]
