export function decodeU8(payload: string, count: number): Uint8Array {
  const binary = atob(payload);
  if (binary.length !== count) {
    throw new Error(`grid byte length ${binary.length} != ${count}`);
  }
  const out = new Uint8Array(count);
  for (let i = 0; i < count; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

export function decodeU16(payload: string, count: number): Uint16Array {
  const bytes = decodeU8(payload, count * 2);
  const view = new DataView(bytes.buffer);
  const out = new Uint16Array(count);
  for (let i = 0; i < count; i += 1) out[i] = view.getUint16(i * 2, true);
  return out;
}

export type GridSpec = {
  lat_min: number;
  lon_min: number;
  dlat: number;
  dlon: number;
  nlat: number;
  nlon: number;
};

export function cellIndex(lat: number, lon: number, grid: GridSpec) {
  const i = Math.floor((lat - grid.lat_min) / grid.dlat);
  const j = Math.floor((lon - grid.lon_min) / grid.dlon);
  if (i < 0 || j < 0 || i >= grid.nlat || j >= grid.nlon) return null;
  return { i, j, offset: i * grid.nlon + j };
}

/** South/west edges and north/east edges of one cell. Row 0 is the south edge. */
export function cellEdges(grid: GridSpec, i: number, j: number) {
  return {
    south: grid.lat_min + i * grid.dlat,
    north: grid.lat_min + (i + 1) * grid.dlat,
    west: grid.lon_min + j * grid.dlon,
    east: grid.lon_min + (j + 1) * grid.dlon,
  };
}
