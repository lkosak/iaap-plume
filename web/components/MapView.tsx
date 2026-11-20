"use client";

import { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import type * as Leaflet from "leaflet";
import type { CellReadout, LayerName, Run } from "@/lib/types";
import { decodeU16, decodeU8 } from "@/lib/grid";

type Props = {
  run: Run;
  layer: LayerName;
  onPick: (cell: CellReadout | null) => void;
};

export function MapView({ run, layer, onPick }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Leaflet.Map | null>(null);
  const groupRef = useRef<Leaflet.LayerGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const onPickRef = useRef(onPick);
  const [ready, setReady] = useState(false);
  const fitted = useRef<string>("");
  onPickRef.current = onPick;

  useEffect(() => {
    let dead = false;
    (async () => {
      const imported = await import("leaflet");
      const L = ("default" in imported && imported.default ? imported.default : imported) as typeof import("leaflet");
      if (dead || !host.current || mapRef.current) return;
      const map = L.map(host.current, { zoomControl: true });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 18,
      }).addTo(map);
      L.control.scale({ imperial: true, metric: true }).addTo(map);
      map.on("click", (event) => {
        const detail = readCell(runRef.current, event.latlng.lat, event.latlng.lng);
        onPickRef.current(detail);
      });
      mapRef.current = map;
      leafletRef.current = L;
      setReady(true);
    })();
    return () => {
      dead = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    const map = mapRef.current;
    const L = leafletRef.current;
    if (!ready || !map || !L) return;
    if (groupRef.current) {
      groupRef.current.remove();
    }
    const group = L.layerGroup().addTo(map);
    groupRef.current = group;
    const grid = run.grid;
    const count = grid.nlat * grid.nlon;
    const air = decodeU8(grid.air_member_hits, count);
    const dep = decodeU8(grid.deposition_member_hits, count);
    const early = decodeU16(grid.arrival_earliest_min, count);
    const canvas = document.createElement("canvas");
    canvas.width = grid.nlon;
    canvas.height = grid.nlat;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const image = ctx.createImageData(grid.nlon, grid.nlat);
    const n = Math.max(grid.n_members, 1);
    let minMinute = 65535;
    let maxMinute = 0;
    if (layer === "arrival") {
      for (let k = 0; k < count; k += 1) {
        if (air[k] > 0 && early[k] !== grid.no_arrival) {
          minMinute = Math.min(minMinute, early[k]);
          maxMinute = Math.max(maxMinute, early[k]);
        }
      }
    }
    for (let i = 0; i < grid.nlat; i += 1) {
      for (let j = 0; j < grid.nlon; j += 1) {
        const k = i * grid.nlon + j;
        const y = grid.nlat - 1 - i;
        const pixel = (y * grid.nlon + j) * 4;
        const color = colorFor(layer, air[k], dep[k], early[k], n, grid.no_arrival, minMinute, maxMinute);
        if (!color) continue;
        image.data[pixel] = color[0];
        image.data[pixel + 1] = color[1];
        image.data[pixel + 2] = color[2];
        image.data[pixel + 3] = color[3];
      }
    }
    ctx.putImageData(image, 0, 0);
    L.imageOverlay(canvas.toDataURL(), [[grid.lat_min, grid.lon_min], [grid.lat_max, grid.lon_max]], {
      opacity: 0.92,
      interactive: false,
    }).addTo(group);

    const box = run.source.bbox;
    L.rectangle([[box.south, box.west], [box.north, box.east]], {
      color: "#243e73",
      weight: 1.5,
      fillOpacity: 0.04,
    }).addTo(group);
    for (const member of run.ensemble.members) {
      L.circleMarker([member.source_lat, member.source_lon], {
        radius: 3,
        color: "#243e73",
        weight: 1,
        fillOpacity: 0.45,
      }).addTo(group);
    }
    const plant = L.marker([run.source.lat, run.source.lon], {
      icon: L.divIcon({
        className: "",
        html: '<div style="background:#243e73;color:white;font:600 11px sans-serif;padding:3px 6px;border-radius:4px;white-space:nowrap">IAAAP</div>',
        iconSize: [52, 22],
        iconAnchor: [26, 22],
      }),
    });
    plant.bindPopup(`${run.source.name}<br/>Installation centroid. Release points are the small dots inside the outline.`);
    plant.addTo(group);
    const fair = L.marker([run.receptor.lat, run.receptor.lon], {
      icon: L.divIcon({
        className: "",
        html: '<div style="background:#1c1915;color:white;font:600 11px sans-serif;padding:3px 6px;border-radius:999px;white-space:nowrap">Fairfield</div>',
        iconSize: [72, 22],
        iconAnchor: [36, 11],
      }),
    });
    fair.bindPopup(
      `${run.receptor.name}<br/>${run.receptor.distance_km} km ${run.receptor.bearing_word} of the installation centroid.`,
    );
    fair.addTo(group);

    if (fitted.current !== run.run_id) {
      const bounds = L.latLngBounds([
        [run.source.lat, run.source.lon],
        [run.receptor.lat, run.receptor.lon],
      ]);
      for (let k = 0; k < count; k += 1) {
        if (air[k] <= 0) continue;
        const i = Math.floor(k / grid.nlon);
        const j = k % grid.nlon;
        bounds.extend([grid.lat_min + (i + 0.5) * grid.dlat, grid.lon_min + (j + 0.5) * grid.dlon]);
      }
      map.fitBounds(bounds, { padding: [28, 28] });
      fitted.current = run.run_id;
    }
  }, [ready, run, layer]);

  return <div ref={host} className="h-[58dvh] min-h-[320px] w-full md:h-full md:min-h-[560px]" />;
}

function colorFor(
  layer: LayerName,
  airHits: number,
  depHits: number,
  earliest: number,
  nMembers: number,
  noArrival: number,
  minMinute: number,
  maxMinute: number,
): [number, number, number, number] | null {
  if (layer === "deposition") {
    if (depHits <= 0) return null;
    const t = depHits / nMembers;
    return [146, 90, 42, Math.round(255 * (0.22 + 0.7 * t))];
  }
  if (airHits <= 0) return null;
  if (layer === "arrival" && earliest !== noArrival && maxMinute > minMinute) {
    const t = (earliest - minMinute) / (maxMinute - minMinute);
    const r = Math.round(190 - 150 * t);
    const g = Math.round(210 - 130 * t);
    const b = Math.round(230 - 80 * t);
    return [r, g, b, Math.round(255 * (0.35 + 0.5 * (airHits / nMembers)))];
  }
  const t = airHits / nMembers;
  return [36, 62, 140, Math.round(255 * (0.2 + 0.72 * t))];
}

function readCell(run: Run | null, lat: number, lon: number): CellReadout | null {
  if (!run) return null;
  const grid = run.grid;
  const i = Math.floor((lat - grid.lat_min) / grid.dlat);
  const j = Math.floor((lon - grid.lon_min) / grid.dlon);
  if (i < 0 || j < 0 || i >= grid.nlat || j >= grid.nlon) return null;
  const count = grid.nlat * grid.nlon;
  const offset = i * grid.nlon + j;
  const air = decodeU8(grid.air_member_hits, count);
  const dep = decodeU8(grid.deposition_member_hits, count);
  const airPct = decodeU8(grid.air_relative_pct, count);
  const depPct = decodeU8(grid.deposition_relative_pct, count);
  const early = decodeU16(grid.arrival_earliest_min, count);
  const late = decodeU16(grid.arrival_latest_min, count);
  return {
    lat: grid.lat_min + (i + 0.5) * grid.dlat,
    lon: grid.lon_min + (j + 0.5) * grid.dlon,
    airHits: air[offset],
    depHits: dep[offset],
    airPct: airPct[offset],
    depPct: depPct[offset],
    earliest: early[offset],
    latest: late[offset],
  };
}
