"use client";

import { useEffect, useState } from "react";
import { publicPath } from "@/lib/publicPath";

type RoseSector = {
  sector: string;
  from_deg: number;
  pct: number;
  toward_fairfield: boolean;
};

type Level = {
  n_hours: number;
  n_days: number;
  calm_pct: number;
  toward_fairfield_22_5_pct: number;
  toward_fairfield_45_pct: number;
  full_window_22_5_pct_of_days: number;
  full_window_45_pct_of_days: number;
  prevailing: { sector: string; pct: number }[];
  rose: RoseSector[];
};

type ClimatologyFile = {
  title: string;
  note: string;
  period: string;
  window: string;
  fairfield: { bearing_deg: number; distance_km: number; wind_from_deg: number };
  era5_10m: Level;
  era5_100m: Level;
  kbrl: { station: string; n_hours: number; toward_fairfield_22_5_pct: number; toward_fairfield_45_pct: number };
};

export function Climatology() {
  const [data, setData] = useState<ClimatologyFile | null>(null);

  useEffect(() => {
    let stop = false;
    fetch(publicPath("/climatology.json"))
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (!stop) setData(body);
      })
      .catch(() => {
        if (!stop) setData(null);
      });
    return () => {
      stop = true;
    };
  }, []);

  if (!data) return null;
  const level = data.era5_10m;
  const peak = Math.max(...level.rose.map((item) => item.pct), 1);
  return (
    <details className="mt-4 rounded-2xl border border-[#1c1915]/15 bg-[#f7f4ef] px-3 py-3">
      <summary className="cursor-pointer text-sm font-semibold text-[#1c1915]">
        Historical wind context (climatology, not a forecast)
      </summary>
      <div className="mt-3 space-y-3 text-sm leading-relaxed text-[#1c1915]">
        <p>
          {data.note} This panel is ERA5 reanalysis for {data.period}, daytime hours {data.window}. Fairfield is {data.fairfield.distance_km} km
          from the installation on a bearing of {data.fairfield.bearing_deg}°. Wind that blows toward Fairfield comes from about {data.fairfield.wind_from_deg}°.
        </p>
        <div className="space-y-1">
          {level.rose.map((item) => (
            <div key={item.sector} className="grid grid-cols-[3rem_1fr_3rem] items-center gap-2 text-xs">
              <span className={item.toward_fairfield ? "font-semibold text-[#8a3b12]" : "text-[#3d3832]"}>{item.sector}</span>
              <span className="h-2 overflow-hidden rounded-full bg-[#e4dfd6]">
                <span
                  className="block h-2 rounded-full"
                  style={{
                    width: `${(100 * item.pct) / peak}%`,
                    background: item.toward_fairfield ? "#8a3b12" : "#243e73",
                  }}
                />
              </span>
              <span className="text-right tabular-nums">{item.pct.toFixed(1)}%</span>
            </div>
          ))}
        </div>
        <p className="text-xs text-[#5c564e]">The brown bar is the 22.5° sector centered on wind from {data.fairfield.wind_from_deg}° (toward Fairfield). Other bars are where the wind came from.</p>
        <ul className="list-disc space-y-1 pl-4">
          <li>
            Daytime 10 m winds within ±22.5° of toward-Fairfield: {level.toward_fairfield_22_5_pct}% of hours. Within ±45°: {level.toward_fairfield_45_pct}%.
            Calm, under 1 m/s: {level.calm_pct}%.
          </li>
          <li>
            Most common directions at 10 m: {level.prevailing.map((item) => `${item.sector} ${item.pct}%`).join(", ")}.
          </li>
          <li>
            Days when every hour from 10 AM to 2 PM stayed in that ±22.5° sector: {level.full_window_22_5_pct_of_days}% of {level.n_days} days.
            Within ±45°: {level.full_window_45_pct_of_days}%.
          </li>
          <li>
            At 100 m the toward-Fairfield shares are {data.era5_100m.toward_fairfield_22_5_pct}% (±22.5°) and {data.era5_100m.toward_fairfield_45_pct}% (±45°).
          </li>
          <li>
            Burlington airport (KBRL) observations over the same dates and hours: {data.kbrl.toward_fairfield_22_5_pct}% within ±22.5° and {data.kbrl.toward_fairfield_45_pct}% within ±45°, from {data.kbrl.n_hours} reports.
          </li>
        </ul>
      </div>
    </details>
  );
}
