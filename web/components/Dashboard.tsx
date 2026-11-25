"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Climatology } from "@/components/Climatology";
import { MapView } from "@/components/MapView";
import { publicPath } from "@/lib/publicPath";
import type { CellReadout, Hindcast, HysplitTrajectories, LayerName, Run, RunIndex } from "@/lib/types";

const MONDAY = "2026-11-23";
const TUESDAY = "2026-11-24";
const WEDNESDAY = "2026-11-25";
const THURSDAY = "2026-11-26";
const FRIDAY = "2026-11-27";

const DAY_NAMES: Record<string, string> = {
  [MONDAY]: "Monday",
  [TUESDAY]: "Tuesday",
  [WEDNESDAY]: "Wednesday",
  [THURSDAY]: "Thursday",
  [FRIDAY]: "Friday",
};

function dayFromHash() {
  if (typeof window === "undefined") return WEDNESDAY;
  const hash = window.location.hash.replace("#", "");
  if (hash === "thu" || hash === THURSDAY) return THURSDAY;
  if (hash === "fri" || hash === FRIDAY) return FRIDAY;
  return WEDNESDAY;
}

const LAYERS: { id: LayerName; label: string }[] = [
  { id: "air", label: "Air overlap" },
  { id: "deposition", label: "Deposition overlap" },
  { id: "arrival", label: "First arrival" },
  { id: "hysplit", label: "HYSPLIT trajectories (real HYSPLIT, forecast met)" },
  { id: "hindcast", label: "post-event hindcast" },
];

export function Dashboard() {
  const [run, setRun] = useState<Run | null>(null);
  const [index, setIndex] = useState<RunIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [layer, setLayer] = useState<LayerName>("air");
  const [hindcast, setHindcast] = useState<Hindcast | null>(null);
  const [trajectoryFile, setTrajectoryFile] = useState<HysplitTrajectories | null>(null);
  const [hindcastHour, setHindcastHour] = useState("");
  const [hindcastField, setHindcastField] = useState<"air" | "deposition">("air");
  const [picked, setPicked] = useState<CellReadout | null>(null);
  const [releaseDay, setReleaseDay] = useState(WEDNESDAY);

  useEffect(() => {
    const apply = () => setReleaseDay(dayFromHash());
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, []);

  function chooseDay(day: string) {
    setReleaseDay(day);
    setPicked(null);
    const hash = day === THURSDAY ? "#thu" : day === FRIDAY ? "#fri" : "#wed";
    window.history.replaceState(null, "", hash);
  }

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const [latestRes, indexRes, hindcastRes, trajectoryRes] = await Promise.all([
          fetch(publicPath("/runs/latest.json"), { cache: "no-store" }),
          fetch(publicPath("/runs/index.json"), { cache: "no-store" }),
          fetch(publicPath("/hindcast/latest.json"), { cache: "no-store" }),
          fetch(publicPath("/hysplit/latest.json"), { cache: "no-store" }),
        ]);
        if (!latestRes.ok) throw new Error(`No archived run yet (HTTP ${latestRes.status}).`);
        const latest = (await latestRes.json()) as Run;
        const listing = indexRes.ok ? ((await indexRes.json()) as RunIndex) : null;
        const hindcastBody = hindcastRes.ok ? ((await hindcastRes.json()) as Hindcast) : null;
        const trajectoryBody = trajectoryRes.ok ? ((await trajectoryRes.json()) as HysplitTrajectories) : null;
        if (!stop) {
          setRun(latest);
          setIndex(listing);
          setHindcast(hindcastBody);
          setTrajectoryFile(trajectoryBody);
          setError(null);
        }
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : "Could not load a run.");
      } finally {
        if (!stop) setLoading(false);
      }
    }
    load();
    const timer = setInterval(load, 20000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, []);

  async function openRun(id: string) {
    const res = await fetch(publicPath(`/runs/${id}/run.json`), { cache: "no-store" });
    if (!res.ok) return;
    setRun((await res.json()) as Run);
    setPicked(null);
  }

  const showingLatest = !index || !run || index.latest_id === run.run_id;
  const hysplit =
    showingLatest && trajectoryFile && (trajectoryFile.real_hysplit || !run?.hysplit?.real_hysplit)
      ? trajectoryFile
      : run?.hysplit;
  const day = run?.release_days?.[releaseDay];
  const dayRun = run && day
    ? {
        ...run,
        narrative: day.narrative,
        receptor: day.receptor,
        footprint: { ...run.footprint, ...day.footprint },
        grid: day.grid.cells ? { ...run.grid, ...day.grid } : run.grid,
        ensemble: { ...run.ensemble, n_members: day.n_members, members: day.members },
        forecast: { ...run.forecast, used: day.used, skipped: day.skipped },
        event: { ...run.event, release_window_chicago: day.release_window_chicago },
      }
    : run;
  const hourly = hindcast?.grid?.hourly;
  const selectedHour = hourly?.find((hour) => hour.end_utc === hindcastHour);
  const mappedHindcast = hindcast?.grid && selectedHour
    ? { ...hindcast, grid: { ...hindcast.grid, ...selectedHour } }
    : hindcast;
  const displayRun = dayRun && hysplit ? { ...dayRun, hysplit } : dayRun;

  return (
    <main className="mx-auto min-h-dvh max-w-6xl px-3 py-4 md:px-6 md:py-6">
      <header className="mb-3">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#243e73]">Independent screening</p>
        <h1 className="font-serif text-3xl leading-tight text-[#1c1915] md:text-4xl">IAAAP plume screening</h1>
        <p className="mt-1 max-w-2xl text-sm text-[#3d3832]">
          Relative ensemble footprints for the planned lead-azide detonations at the Iowa Army Ammunition Plant.
          Fairfield is marked. This is not a measurement and not an official advisory.
        </p>
      </header>

      {run ? <ScheduleBanner run={run} /> : null}

      <p className="mb-3 rounded-xl border border-[#1c1915]/15 bg-[#fffdf8] px-3 py-2 text-sm leading-relaxed text-[#1c1915]">
        {run?.disclaimer ??
          "These maps are relative model footprints. They are not measurements of lead and they are not concentrations. Follow the U.S. Army, U.S. EPA, Iowa HHS, and local emergency managers."}
      </p>

      {loading && !run ? <p className="text-sm">Loading the latest archived run…</p> : null}
      {error && !run ? (
        <Card>
          <CardHeader>
            <CardTitle>No forecast archive yet</CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-relaxed">
            <p>{error}</p>
            <p className="mt-2">
              From the repo root, run <code className="rounded bg-[#efeae2] px-1">python3 -m pipeline.run_snapshot --out web/public/runs</code>.
              This page checks again every 20 seconds.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {run ? (
        <div className="mb-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#243e73]">Release day</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Release day">
            <Button size="sm" variant={releaseDay === WEDNESDAY ? "default" : "outline"} aria-pressed={releaseDay === WEDNESDAY} onClick={() => chooseDay(WEDNESDAY)} disabled={!run.release_days}>
              Wed Nov 25
            </Button>
            <Button size="sm" variant={releaseDay === THURSDAY ? "default" : "outline"} aria-pressed={releaseDay === THURSDAY} onClick={() => chooseDay(THURSDAY)} disabled={!run.release_days}>
              Thu Nov 26
            </Button>
            <Button size="sm" variant={releaseDay === FRIDAY ? "default" : "outline"} aria-pressed={releaseDay === FRIDAY} onClick={() => chooseDay(FRIDAY)} disabled={!run.release_days}>
              Fri Nov 27
            </Button>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-[#3d3832]">
            The planned detonation is Wednesday, Nov 25 at 9:00 AM CT.
            {day ? ` This run modeled ${day.release_window_chicago}.` : ""}
            {day ? ` This day uses ${day.n_members} ensemble members.` : " This archived run has no separate window for the selected day."}
            {day && day.n_members === 0 ? ` No model in this run reaches ${DAY_NAMES[releaseDay] ?? "that day"} evening.` : ""}
          </p>
        </div>
      ) : null}

      {displayRun ? (
        <div className="grid gap-3 md:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.8fr)] md:items-start">
          <div className="overflow-hidden rounded-2xl border border-[#1c1915]/10 bg-white">
            <div className="flex flex-wrap gap-2 px-3 py-2">
              {LAYERS.map((item) => (
                <Button
                  key={item.id}
                  size="sm"
                  variant={layer === item.id ? "default" : "outline"}
                  onClick={() => setLayer(item.id)}
                  aria-pressed={layer === item.id}
                >
                  {item.label}
                </Button>
              ))}
            </div>
            <MapView run={displayRun} layer={layer} hindcast={mappedHindcast} hindcastField={hindcastField} releaseDay={releaseDay} onPick={setPicked} />
            <Legend layer={layer} members={displayRun.ensemble.n_members} hindcastField={hindcastField} />
            {layer === "hindcast" ? (
              <div className="flex flex-wrap items-center gap-2 px-3 py-2">
                {hourly?.length ? (
                  <label className="flex flex-wrap items-center gap-2 text-sm">
                    Time window
                    <select
                      className="max-w-full rounded border bg-white px-2 py-1"
                      value={selectedHour?.end_utc ?? ""}
                      onChange={(event) => {
                        setHindcastHour(event.target.value);
                        setPicked(null);
                      }}
                    >
                      <option value="">Peak across all hours</option>
                      {hourly.map((hour) => <option key={hour.end_utc} value={hour.end_utc}>{hour.label}</option>)}
                    </select>
                  </label>
                ) : null}
                <Button size="sm" variant={hindcastField === "air" ? "default" : "outline"} onClick={() => setHindcastField("air")}>Hindcast air</Button>
                <Button size="sm" variant={hindcastField === "deposition" ? "default" : "outline"} onClick={() => setHindcastField("deposition")}>Hindcast deposition</Button>
              </div>
            ) : null}
            {picked ? <CellCard run={displayRun} cell={picked} layer={layer} hindcastField={hindcastField} /> : (
              <p className="px-3 py-2 text-xs text-[#5c564e]">Tap the map to read one cell. Counts are ensemble members, not a measurement.</p>
            )}
          </div>

          <div className="flex flex-col gap-3">
            <StatusChips run={displayRun} />
            <TrajectoryCard run={displayRun} releaseDay={releaseDay} />
            <FairfieldCard run={displayRun} />
            <Card>
              <CardHeader>
                <CardTitle>This run</CardTitle>
              </CardHeader>
              <CardContent className="text-sm leading-relaxed text-[#1c1915]">
                <p>{displayRun.narrative}</p>
                <p className="mt-2 text-[#5c564e]">{displayRun.engine.summary}</p>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      <Climatology />

      {run ? (
        <>
          <History index={index} active={run.run_id} onOpen={openRun} />
          <Uncertainty run={displayRun ?? run} />
          <Official run={run} />
          <Limits />
        </>
      ) : null}
    </main>
  );
}

function ScheduleBanner({ run }: { run: Run }) {
  const schedule = run.schedule;
  if (!schedule) return null;
  return (
    <section className="mb-3 rounded-2xl border-2 border-[#243e73] bg-[#e7eef8] px-3 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#243e73]">Schedule the model is built around</p>
      <p className="mt-1 font-serif text-lg leading-snug text-[#1c1915]">{schedule.change}</p>
      <p className="mt-1 text-sm text-[#1c1915]">
        Ensemble center: {schedule.ensemble_center_chicago}. Window: {schedule.ensemble_window_chicago}.
      </p>
      <p className="mt-1 text-xs leading-relaxed text-[#3d3832]">{schedule.change_basis}</p>
      {schedule.fetched_mentions?.length ? (
        <ul className="mt-2 space-y-1 text-xs">
          {schedule.fetched_mentions.map((item) => (
            <li key={item.url}>
              <a className="font-semibold underline" href={item.url}>
                {item.publisher}
              </a>
              {item.kind === "press" ? " (news, not an official advisory)" : " (official)"}: {item.flags.join("; ")}. {item.title}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-[#3d3832]">The latest page retrieval did not yield date language to quote. Open the official section for links.</p>
      )}
    </section>
  );
}

function StatusChips({ run }: { run: Run }) {
  const models = run.forecast.used.map((item) => `${item.label} ${item.cycle}`).join(" · ") || "none";
  return (
    <div className="flex flex-wrap gap-2">
      <Badge>Model run {run.generated_at_chicago}</Badge>
      <Badge>Forecast retrieved {run.forecast.retrieved_at_chicago ?? "unknown"}</Badge>
      <Badge>{run.engine.label}</Badge>
      <Badge className="normal-case tracking-normal">{models}</Badge>
      {run.hysplit?.real_hysplit ? (
        <Badge className="normal-case tracking-normal">
          {run.hysplit.label}. {run.hysplit.met?.model} cycle {run.hysplit.met?.cycle}.
        </Badge>
      ) : null}
    </div>
  );
}

function TrajectoryCard({ run, releaseDay }: { run: Run; releaseDay: string }) {
  const hysplit = run.hysplit;
  if (!hysplit) return null;
  const tracks = (hysplit.trajectories ?? []).filter((track) => (track.release_day ? track.release_day === releaseDay : releaseDay === WEDNESDAY));
  const mondayTracks = (hysplit.trajectories ?? []).filter((track) => (track.release_day ? track.release_day === WEDNESDAY : true));
  const mondayOnlyNote = releaseDay !== WEDNESDAY && mondayTracks.length > 0 && tracks.length === 0;
  const dayName = DAY_NAMES[releaseDay] ?? "that day";
  return (
    <Card>
      <CardHeader>
        <CardTitle>{hysplit.label}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm leading-relaxed">
        <p>{hysplit.note}</p>
        {mondayOnlyNote ? (
          <p className="mt-2">The HYSPLIT trajectories in this product are Wednesday-only. The shaded footprint for {dayName} is the screening ensemble, labeled NOT HYSPLIT.</p>
        ) : null}
        {hysplit.met ? (
          <p className="mt-2">
            Met {hysplit.met.model} cycle {hysplit.met.cycle}. Valid {hysplit.met.valid_start} to {hysplit.met.valid_end}. Files: {hysplit.met.files.join(", ")}.
          </p>
        ) : null}
        {hysplit.real_hysplit && !mondayOnlyNote ? (
          <p className="mt-2">{tracks.length} trajectories from 50, 250, and 500 m AGL.</p>
        ) : hysplit.real_hysplit ? null : (
          <p className="mt-2">{hysplit.reason}</p>
        )}
        {hysplit.skipped?.length ? (
          <ul className="mt-2 text-xs text-[#5c564e]">
            {hysplit.skipped.map((item) => (
              <li key={`${item.model}-${item.cycle}`}>Skipped {item.model} {item.cycle}: {item.reason}</li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

function FairfieldCard({ run }: { run: Run }) {
  const rec = run.receptor;
  const miles = Math.round(rec.distance_km * 0.621371);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Fairfield</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-serif text-4xl text-[#1c1915]">
          {rec.air_hits} <span className="text-xl">of {rec.n_members}</span>
        </p>
        <p className="text-sm text-[#3d3832]">ensemble members put an airborne particle in the Fairfield cell.</p>
        <p className="mt-2 text-sm">
          Highest in that cell or a neighbor: {rec.air_neighbor_hits} of {rec.n_members}. Surface-deposition overlap in the cell: {rec.deposition_hits} of {rec.n_members}.
        </p>
        <p className="mt-2 text-sm">
          {miles} miles ({rec.distance_km} km) {rec.bearing_word} of the installation centroid, bearing {rec.bearing_deg_from_source.toFixed(0)}°.
        </p>
        {rec.arrival_earliest_chicago ? (
          <p className="mt-2 text-sm">
            First arrival in the cell: {rec.arrival_earliest_chicago}
            {rec.arrival_latest_chicago && rec.arrival_latest_chicago !== rec.arrival_earliest_chicago
              ? ` to ${rec.arrival_latest_chicago}`
              : ""}.
          </p>
        ) : null}
        {rec.air_hits === 0 && rec.nearest_overlap_km != null ? (
          <p className="mt-2 text-sm">Nearest cell with any member is about {rec.nearest_overlap_km} km from Fairfield.</p>
        ) : null}
        {rec.size_height_sensitivity?.length ? (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer font-semibold">Fairfield by particle size and release height</summary>
            <p className="mt-2">Each cell shows weather runs reaching Fairfield in air / depositing there. All pairs use the same weather inputs, source point, and particle density (2,500 kg/m³). Counts are relative model results.</p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-center text-xs">
                <thead>
                  <tr className="border-b">
                    <th scope="col" className="p-1 text-left">Height</th>
                    {[...new Set(rec.size_height_sensitivity.map((row) => row.diameter_um))].map((size) => (
                      <th scope="col" key={size} className="p-1">{size} µm</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...new Set(rec.size_height_sensitivity.map((row) => row.height_m))].map((height) => (
                    <tr key={height} className="border-b">
                      <th scope="row" className="whitespace-nowrap p-1 text-left">{height} m</th>
                      {rec.size_height_sensitivity?.filter((row) => row.height_m === height).map((row) => (
                        <td key={row.diameter_um} className="whitespace-nowrap p-1">
                          {row.air_hits}/{row.deposition_hits}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-xs">Each pair uses {rec.size_height_sensitivity[0].n_members} weather runs.</p>
          </details>
        ) : null}
        <p className="mt-2 text-xs text-[#5c564e]">A zero is not a measurement of clean air. A nonzero count is not a measurement of lead.</p>
      </CardContent>
    </Card>
  );
}

function Legend({ layer, members, hindcastField }: { layer: LayerName; members: number; hindcastField: "air" | "deposition" }) {
  const label =
    layer === "hysplit"
      ? "Lines are HYSPLIT trajectories (real HYSPLIT, forecast met). The faint cells are the separate NOT HYSPLIT screening footprint."
      : layer === "hindcast"
        ? `post-event hindcast, ${hindcastField === "deposition" ? "deposition" : "air"} field, as a percent of this run's peak. Not a concentration.`
      : layer === "deposition"
      ? "Share of members that deposited a particle in the cell"
      : layer === "arrival"
        ? "Earliest first-arrival among members that reach the cell. Darker is later."
        : "Share of members with any airborne particle in the cell";
  return (
    <div className="flex items-center gap-3 px-3 py-2 text-xs text-[#3d3832]">
      <span className="h-3 w-24 rounded-full" style={{ background: layer === "deposition" ? "linear-gradient(90deg, rgba(146,90,42,0.25), rgba(146,90,42,0.95))" : "linear-gradient(90deg, rgba(36,62,140,0.25), rgba(36,62,140,0.95))" }} />
      <span>0 of {members} → {members} of {members}. {label}</span>
    </div>
  );
}

function CellCard({ run, cell, layer, hindcastField }: { run: Run; cell: CellReadout; layer: LayerName; hindcastField: "air" | "deposition" }) {
  const none = run.grid.no_arrival;
  if (layer === "hindcast") {
    return (
      <div className="border-t border-[#1c1915]/10 px-3 py-2 text-sm">
        <p className="font-semibold">Cell near {cell.lat.toFixed(2)}°, {cell.lon.toFixed(2)}°</p>
        <p>post-event hindcast {hindcastField} field: {hindcastField === "deposition" ? cell.depPct : cell.airPct} percent of this run&apos;s peak.</p>
        <p className="text-xs text-[#5c564e]">Not a concentration. Not a measurement of lead. Release mass is unknown.</p>
      </div>
    );
  }
  return (
    <div className="border-t border-[#1c1915]/10 px-3 py-2 text-sm">
      <p className="font-semibold">Cell near {cell.lat.toFixed(2)}°, {cell.lon.toFixed(2)}°</p>
      <p>Airborne overlap: {cell.airHits} of {run.ensemble.n_members}. Relative dwell (peak = 100): {cell.airPct}.</p>
      <p>Deposition overlap: {cell.depHits} of {run.ensemble.n_members}. Relative deposited weight (peak = 100): {cell.depPct}.</p>
      {cell.earliest !== none ? <p>First arrivals span minute {cell.earliest} to {cell.latest} after {run.grid.arrival_origin}.</p> : <p>No member reached this cell.</p>}
      <p className="text-xs text-[#5c564e]">Not a measurement of lead. Not a concentration.</p>
    </div>
  );
}

function History({ index, active, onOpen }: { index: RunIndex | null; active: string; onOpen: (id: string) => void }) {
  const runs = [...(index?.runs ?? [])].reverse();
  const max = Math.max(1, ...runs.map((item) => item.n_members || 1));
  return (
    <Card className="mt-3">
      <CardHeader>
        <CardTitle>Archived runs</CardTitle>
      </CardHeader>
      <CardContent>
        {runs.length === 0 ? <p className="text-sm">History appears here after the first snapshot. Later weather updates are kept.</p> : null}
        <ul className="space-y-2">
          {runs.map((item) => {
            const hits = item.fairfield_air_hits ?? 0;
            const n = item.n_members || max;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onOpen(item.id)}
                  className={`flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left text-sm ${item.id === active ? "bg-[#e7eef8]" : "hover:bg-[#f6f3ee]"}`}
                >
                  <span className="w-16 shrink-0 font-semibold">{hits}/{n}</span>
                  <span className="h-2 flex-1 rounded-full bg-[#e4dfd6]">
                    <span className="block h-2 rounded-full bg-[#243e73]" style={{ width: `${(100 * hits) / n}%` }} />
                  </span>
                  <span className="max-w-[46%] text-xs text-[#3d3832]">
                    {item.generated_at_chicago}
                    <span className="block">{item.engine_label}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-xs text-[#5c564e]">The bar is Fairfield airborne overlap for that archive entry. It is not a measurement trend.</p>
      </CardContent>
    </Card>
  );
}

function Uncertainty({ run }: { run: Run }) {
  return (
    <Card className="mt-3">
      <CardHeader>
        <CardTitle>What the ensemble varies</CardTitle>
      </CardHeader>
      <CardContent className="text-sm leading-relaxed">
        <ul className="list-disc space-y-1 pl-4">
          {run.ensemble.varied.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="mt-2 text-[#5c564e]">
          {run.ensemble.n_members} members, {run.ensemble.particles_per_member} particles each, followed {run.event.simulation_hours_after_release} hours.
          {run.footprint.fraction_particles_left_map >= 0.15
            ? ` About ${Math.round(run.footprint.fraction_particles_left_map * 100)}% of particles left the map window.`
            : ""}
        </p>
        {run.forecast.skipped.length ? (
          <ul className="mt-2 text-[#5c564e]">
            {run.forecast.skipped.map((item) => (
              <li key={`${item.label}-${item.cycle}`}>Skipped {item.label} {item.cycle}: {item.reason}</li>
            ))}
          </ul>
        ) : null}
        <p className="mt-2 text-xs text-[#5c564e]">{run.forecast.attribution}</p>
      </CardContent>
    </Card>
  );
}

function Official({ run }: { run: Run }) {
  const official = run.official;
  const sources = official?.sources ?? [];
  return (
    <section className="mt-4 rounded-2xl border-4 border-double border-[#8a5a12] bg-[#fff6e4] px-4 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8a5a12]">Official agency material — not this model</p>
      <h2 className="font-serif text-2xl text-[#1c1915]">Army, EPA, and state pages</h2>
      <p className="mt-1 text-sm">{official?.preface}</p>
      <p className="mt-1 text-xs text-[#5c564e]">Retrieved {official?.retrieved_at_chicago ?? "—"} (America/Chicago). Excerpts are trimmed leftovers of that download.</p>
      <ul className="mt-3 space-y-3">
        {sources.map((source) => (
          <li key={source.id} className={source.kind === "press" ? "rounded-xl bg-white/70 p-3" : "rounded-xl bg-white p-3"}>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-[#8a5a12]">
              {source.kind === "press" ? "News report, not an official advisory" : "Official"} · {source.publisher} · {source.status}
            </p>
            <a className="font-semibold underline" href={source.url}>{source.title}</a>
            {source.excerpt ? <p className="mt-1 text-sm leading-relaxed">{source.excerpt}</p> : null}
            {source.note ? <p className="mt-1 text-xs text-[#5c564e]">{source.note}</p> : null}
          </li>
        ))}
      </ul>
      <div className="mt-3 rounded-xl bg-white p-3 text-sm">
        <p className="font-semibold">Monitoring data</p>
        <p className="mt-1">{official?.monitoring?.note}</p>
        {official?.monitoring?.rows?.length ? (
          <ul className="mt-2 space-y-1 text-xs">
            {official.monitoring.rows.slice(0, 8).map((row) => (
              <li key={`${row.time}-${row.source}`}>{row.time}: {row.value} {row.unit} at {row.lat}, {row.lon} ({row.source})</li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

function Limits() {
  return (
    <Card className="mt-3 mb-8">
      <CardHeader>
        <CardTitle>What this cannot tell you</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm leading-relaxed">
        <p>A colored cell is a count of model scenarios. It is not a measurement of lead in air, soil, or dust, and it is not a concentration.</p>
        <p>A cell with no members is not evidence that lead will be absent. Follow Army, EPA, Iowa HHS, and county instructions if they differ from this map.</p>
        <p>The engine is labeled NOT HYSPLIT unless a run says otherwise. Winds are forecast profiles, not a full three-dimensional weather grid, and the release size mix is an assumption.</p>
      </CardContent>
    </Card>
  );
}
