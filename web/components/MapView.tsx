"use client";

import { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import type * as Leaflet from "leaflet";
import type { CellReadout, Hindcast, LayerName, Run } from "@/lib/types";
import { cellEdges, decodeU16, decodeU8 } from "@/lib/grid";

type Props = {
  run: Run;
  layer: LayerName;
  hindcast: Hindcast | null;
  hindcastField: "air" | "deposition";
  onPick: (cell: CellReadout | null) => void;
};

const HEIGHT_COLOR: Record<number, string> = { 50: "#243e73", 250: "#1f7a4d", 500: "#8a5a12" };

export function MapView({ run, layer, hindcast, hindcastField, onPick }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Leaflet.Map | null>(null);
  const groupRef = useRef<Leaflet.LayerGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const onPickRef = useRef(onPick);
  const layerRef = useRef(layer);
  const hindcastRef = useRef(hindcast);
  const hindcastFieldRef = useRef(hindcastField);
  layerRef.current = layer;
  hindcastRef.current = hindcast;
  hindcastFieldRef.current = hindcastField;
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
        const detail = layerRef.current === "hindcast"
          ? readHindcast(hindcastRef.current, hindcastFieldRef.current, event.latlng.lat, event.latlng.lng)
          : readCell(runRef.current, event.latlng.lat, event.latlng.lng);
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
        const row: number = grid.nlat - 1 - i;
        const pixel = (row * grid.nlon + j) * 4;
        const shown = layer === "hysplit" ? "air" : layer;
        const color = colorFor(shown, air[k], dep[k], early[k], n, grid.no_arrival, minMinute, maxMinute);
        if (!color) continue;
        image.data[pixel] = color[0];
        image.data[pixel + 1] = color[1];
        image.data[pixel + 2] = color[2];
        image.data[pixel + 3] = color[3];
      }
    }
    ctx.putImageData(image, 0, 0);
    // One image stretched from the southwest corner to the northeast corner is
    // linear in Web Mercator, not in latitude. On the 17° grid that put the
    // plant's cell about 63 km north of IAAAP. Each cell is drawn from its
    // own stored edges instead.
    if (layer !== "hindcast") {
      paintCells(L, map, group, coloredCells(grid, image), layer === "hysplit" ? 0.35 : 0.92);
    }
    if (layer === "hindcast" && hindcast?.grid) {
      const relative = hindcastField === "deposition" ? hindcast.grid.relative_deposition : hindcast.grid.relative_air;
      const values = decodeU8(relative, hindcast.grid.nlat * hindcast.grid.nlon);
      const board = document.createElement("canvas");
      board.width = hindcast.grid.nlon;
      board.height = hindcast.grid.nlat;
      const boardCtx = board.getContext("2d");
      if (boardCtx) {
        const pixels = boardCtx.createImageData(board.width, board.height);
        for (let i = 0; i < hindcast.grid.nlat; i += 1) {
          for (let j = 0; j < hindcast.grid.nlon; j += 1) {
            const value = values[i * hindcast.grid.nlon + j];
            if (value <= 0) continue;
            const row: number = hindcast.grid.nlat - 1 - i;
            const pixel = (row * hindcast.grid.nlon + j) * 4;
            const tone = hindcastField === "deposition" ? [146, 90, 42] : [20, 90, 70];
            pixels.data[pixel] = tone[0];
            pixels.data[pixel + 1] = tone[1];
            pixels.data[pixel + 2] = tone[2];
            pixels.data[pixel + 3] = Math.round(40 + 2 * value);
          }
        }
        boardCtx.putImageData(pixels, 0, 0);
        paintCells(L, map, group, coloredCells(hindcast.grid, pixels), 0.9);
      }
    }
    if (layer === "hysplit") {
      for (const track of run.hysplit?.trajectories ?? []) {
        const latlngs = track.points.map((point) => [point.lat, point.lon] as [number, number]);
        if (latlngs.length === 0) continue;
        const color = HEIGHT_COLOR[track.height_m_agl] ?? "#243e73";
        L.polyline(latlngs, { color, weight: 3, opacity: 0.95 }).addTo(group);
        L.circleMarker(latlngs[0], { radius: 4, color, weight: 1, fillOpacity: 0.9 }).bindPopup(
          `${run.hysplit?.label ?? "HYSPLIT"}<br/>${track.height_m_agl} m AGL<br/>${track.release_chicago}<br/>${run.hysplit?.met?.model ?? ""} ${run.hysplit?.met?.cycle ?? ""}`,
        ).addTo(group);
      }
    }

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
  }, [ready, run, layer, hindcast, hindcastField]);

  return <div ref={host} className="h-[58dvh] min-h-[320px] w-full md:h-full md:min-h-[560px]" />;
}

type PaintedCell = { south: number; north: number; west: number; east: number; color: string };

function coloredCells(
  grid: { lat_min: number; lon_min: number; dlat: number; dlon: number; nlat: number; nlon: number },
  image: ImageData,
): PaintedCell[] {
  const cells: PaintedCell[] = [];
  for (let i = 0; i < grid.nlat; i += 1) {
    for (let j = 0; j < grid.nlon; j += 1) {
      const row = grid.nlat - 1 - i;
      const pixel = (row * grid.nlon + j) * 4;
      const alpha = image.data[pixel + 3];
      if (alpha <= 0) continue;
      const edges = cellEdges(grid, i, j);
      cells.push({
        ...edges,
        color: `rgba(${image.data[pixel]},${image.data[pixel + 1]},${image.data[pixel + 2]},${alpha / 255})`,
      });
    }
  }
  return cells;
}

function paintCells(
  L: typeof import("leaflet"),
  map: Leaflet.Map,
  group: Leaflet.LayerGroup,
  cells: PaintedCell[],
  opacity: number,
) {
  const canvas = document.createElement("canvas");
  canvas.className = "iaap-grid";
  canvas.style.pointerEvents = "none";
  const pane = map.getPane("overlayPane");
  if (!pane) return;
  pane.appendChild(canvas);
  const draw = () => {
    if (map.getZoom() == null) return;
    const size = map.getSize();
    const dpr = window.devicePixelRatio || 1;
    const topLeft = map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(canvas, topLeft);
    canvas.width = Math.max(1, size.x) * dpr;
    canvas.height = Math.max(1, size.y) * dpr;
    canvas.style.width = `${size.x}px`;
    canvas.style.height = `${size.y}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);
    ctx.globalAlpha = opacity;
    for (const cell of cells) {
      const nw = map.latLngToContainerPoint([cell.north, cell.west]);
      const se = map.latLngToContainerPoint([cell.south, cell.east]);
      const width = se.x - nw.x;
      const height = se.y - nw.y;
      if (width <= 0 || height <= 0) continue;
      ctx.fillStyle = cell.color;
      ctx.fillRect(nw.x, nw.y, width, height);
    }
  };
  map.on("move zoom viewreset resize", draw);
  group.on("remove", () => {
    map.off("move zoom viewreset resize", draw);
    canvas.remove();
  });
  draw();
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

function readHindcast(hindcast: Hindcast | null, field: "air" | "deposition", lat: number, lon: number): CellReadout | null {
  const grid = hindcast?.grid;
  if (!grid) return null;
  const i = Math.floor((lat - grid.lat_min) / grid.dlat);
  const j = Math.floor((lon - grid.lon_min) / grid.dlon);
  if (i < 0 || j < 0 || i >= grid.nlat || j >= grid.nlon) return null;
  const count = grid.nlat * grid.nlon;
  const air = decodeU8(grid.relative_air, count);
  const dep = decodeU8(grid.relative_deposition, count);
  const offset = i * grid.nlon + j;
  return {
    lat: grid.lat_min + (i + 0.5) * grid.dlat,
    lon: grid.lon_min + (j + 0.5) * grid.dlon,
    airHits: 0,
    depHits: 0,
    airPct: field === "air" ? air[offset] : 0,
    depPct: field === "deposition" ? dep[offset] : 0,
    earliest: 65535,
    latest: 0,
  };
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
