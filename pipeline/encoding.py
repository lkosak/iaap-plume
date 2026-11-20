"""Pack grids as little-endian base64 so the dashboard can decode them."""

import base64

import numpy as np


def pack_u8(arr: np.ndarray) -> str:
    raw = np.ascontiguousarray(arr, dtype=np.uint8).tobytes()
    return base64.b64encode(raw).decode("ascii")


def pack_u16(arr: np.ndarray) -> str:
    raw = np.ascontiguousarray(arr, dtype="<u2").tobytes()
    return base64.b64encode(raw).decode("ascii")


def unpack_u8(payload: str, count: int) -> np.ndarray:
    raw = base64.b64decode(payload)
    if len(raw) != count:
        raise ValueError(f"expected {count} bytes, got {len(raw)}")
    return np.frombuffer(raw, dtype=np.uint8).copy()


def unpack_u16(payload: str, count: int) -> np.ndarray:
    raw = base64.b64decode(payload)
    if len(raw) != count * 2:
        raise ValueError(f"expected {count * 2} bytes, got {len(raw)}")
    return np.frombuffer(raw, dtype="<u2").copy()
