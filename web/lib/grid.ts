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

export type SparseCell = {
  i: number;
  j: number;
  air: number;
  dep: number;
  air_pct: number;
  dep_pct: number;
  earliest: number;
  latest: number;
};

export type DrawableGrid = GridSpec & {
  no_arrival: number;
  n_members?: number;
  air_member_hits?: string;
  deposition_member_hits?: string;
  air_relative_pct?: string;
  deposition_relative_pct?: string;
  arrival_earliest_min?: string;
  arrival_latest_min?: string;
  cells?: SparseCell[];
};

export function gridArrays(grid: DrawableGrid) {
  const count = grid.nlat * grid.nlon;
  if (grid.cells) {
    const air = new Uint8Array(count);
    const dep = new Uint8Array(count);
    const airPct = new Uint8Array(count);
    const depPct = new Uint8Array(count);
    const early = new Uint16Array(count);
    const late = new Uint16Array(count);
    early.fill(grid.no_arrival);
    late.fill(grid.no_arrival);
    for (const cell of grid.cells) {
      const offset = cell.i * grid.nlon + cell.j;
      air[offset] = cell.air;
      dep[offset] = cell.dep;
      airPct[offset] = cell.air_pct;
      depPct[offset] = cell.dep_pct;
      early[offset] = cell.earliest;
      late[offset] = cell.latest;
    }
    return { air, dep, airPct, depPct, early, late };
  }
  return {
    air: decodeU8(grid.air_member_hits ?? "", count),
    dep: decodeU8(grid.deposition_member_hits ?? "", count),
    airPct: decodeU8(grid.air_relative_pct ?? "", count),
    depPct: decodeU8(grid.deposition_relative_pct ?? "", count),
    early: decodeU16(grid.arrival_earliest_min ?? "", count),
    late: decodeU16(grid.arrival_latest_min ?? "", count),
  };
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
