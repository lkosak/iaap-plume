export type LayerName = "air" | "deposition" | "arrival" | "hysplit" | "hindcast";

export type TrajectoryPoint = { time: string; lat: number; lon: number; height_m: number; age_h?: number };

export type HysplitTrajectories = {
  label: string;
  real_hysplit: boolean;
  note?: string;
  reason?: string;
  met?: {
    model: string;
    cycle: string;
    files: string[];
    valid_start?: string;
    valid_end?: string;
    retrieved_at?: string;
  } | null;
  skipped?: { model: string; cycle?: string; reason: string }[];
  trajectories?: {
    height_m_agl: number;
    release_utc: string;
    release_chicago: string;
    release_day?: string;
    points: TrajectoryPoint[];
  }[];
  by_day?: Record<string, { real_hysplit: boolean; reason?: string; trajectories?: HysplitTrajectories["trajectories"] }>;
};

export type Hindcast = {
  label: string;
  real_hysplit: boolean;
  generated_at_chicago?: string;
  note?: string;
  reason?: string;
  met?: { model: string; cycle: string; files: string[]; valid_start?: string; valid_end?: string } | null;
  grid?: {
    lat_min: number;
    lon_min: number;
    lat_max: number;
    lon_max: number;
    dlat: number;
    dlon: number;
    nlat: number;
    nlon: number;
    relative_air: string;
    relative_deposition: string;
    scale?: string;
    hourly?: {
      end_utc: string;
      label: string;
      relative_air: string;
      relative_deposition: string;
    }[];
  };
};

export type OfficialSource = {
  id: string;
  publisher: string;
  kind: string;
  url: string;
  title: string;
  status: string;
  excerpt: string | null;
  note: string;
};

export type Run = {
  run_id: string;
  generated_at_chicago: string;
  disclaimer: string;
  narrative: string;
  engine: {
    label: string;
    is_hysplit: boolean;
    summary: string;
    hysplit_check?: { reason?: string };
  };
  event: {
    release_window_chicago: string;
    release_window_note: string;
    simulation_hours_after_release: number;
  };
  schedule: {
    change: string;
    change_basis: string;
    ensemble_center_chicago: string;
    ensemble_window_chicago: string;
    fetched_mentions: {
      publisher: string;
      kind: string;
      url: string;
      title: string;
      flags: string[];
      status: string;
    }[];
  };
  source: {
    name: string;
    lat: number;
    lon: number;
    bbox: { south: number; west: number; north: number; east: number };
    note: string;
  };
  receptor: {
    name: string;
    lat: number;
    lon: number;
    distance_km: number;
    bearing_deg_from_source: number;
    bearing_word: string;
    air_hits: number;
    air_neighbor_hits: number;
    size_height_sensitivity?: {
      height_m: number;
      diameter_um: number;
      air_hits: number;
      deposition_hits: number;
      n_members: number;
    }[];
    deposition_hits: number;
    n_members: number;
    arrival_earliest_chicago: string | null;
    arrival_latest_chicago: string | null;
    nearest_overlap_km: number | null;
    cell: { i: number; j: number };
  };
  footprint: {
    direction_word: string;
    fraction_particles_left_map: number;
  };
  forecast: {
    retrieved_at_chicago: string | null;
    attribution: string;
    used: { label: string; cycle: string; levels: string[]; notes: string[] }[];
    skipped: { label: string; cycle: string; reason: string }[];
  };
  ensemble: {
    n_members: number;
    particles_per_member: number;
    varied: string[];
    members: {
      id: string;
      model_label: string;
      cycle: string;
      release_local: string;
      source_lat: number;
      source_lon: number;
    }[];
  };
  grid: {
    lat_min: number;
    lon_min: number;
    lat_max: number;
    lon_max: number;
    dlat: number;
    dlon: number;
    nlat: number;
    nlon: number;
    air_member_hits?: string;
    deposition_member_hits?: string;
    air_relative_pct?: string;
    deposition_relative_pct?: string;
    arrival_earliest_min?: string;
    arrival_latest_min?: string;
    arrival_origin: string;
    no_arrival: number;
    n_members: number;
    encoding?: string;
    cells?: {
      i: number;
      j: number;
      air: number;
      dep: number;
      air_pct: number;
      dep_pct: number;
      earliest: number;
      latest: number;
    }[];
  };
  release_days?: Record<
    string,
    {
      id: string;
      label: string;
      weekday: string;
      date: string;
      n_members: number;
      particles_per_member: number;
      release_window_chicago: string;
      narrative: string;
      receptor: Run["receptor"];
      footprint: Run["footprint"] & {
        cells_with_air?: number;
        centroid_lat?: number | null;
        centroid_lon?: number | null;
        centroid_bearing_deg?: number | null;
      };
      used: Run["forecast"]["used"];
      skipped: Run["forecast"]["skipped"];
      members: Run["ensemble"]["members"];
      grid: Run["grid"];
    }
  >;
  hysplit?: HysplitTrajectories;
  official: {
    retrieved_at_chicago?: string;
    preface?: string;
    sources: OfficialSource[];
    monitoring: {
      status: string;
      note: string;
      rows: { time: string; lat: string; lon: string; value: string; unit: string; source: string }[];
    };
  };
};

export type RunIndex = {
  latest_id: string;
  updated_at_chicago?: string;
  runs: {
    id: string;
    generated_at_chicago?: string;
    engine_label?: string;
    fairfield_air_hits?: number;
    fairfield_deposition_hits?: number;
    n_members?: number;
    models?: string[];
    forecast_retrieved_at_chicago?: string;
  }[];
};

export type CellReadout = {
  lat: number;
  lon: number;
  airHits: number;
  depHits: number;
  airPct: number;
  depPct: number;
  earliest: number;
  latest: number;
};
