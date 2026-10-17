import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import L from "leaflet";
import { useMap } from "react-leaflet";
import FlyLive from "./FlyLive";

/** A point the agent may visit: one price marker (listings sharing coordinates share a stop). */
export type Stop = {
  key: string;
  id: string;
  coords: [number, number];
  decision: "approach" | "avoid" | "learning";
  weight: number;
  area: string;
};

type Flight = {
  from: L.Point;
  ctrl: L.Point;
  to: L.Point;
  zoom: number;
  t0: number;
  dur: number;
  stop: Stop | null;
  land: boolean;
  dwell: number;
};

const NOTE = {
  approach: "Wants to go here",
  learning: "Still learning",
  avoid: "Turns away",
};
// How long the agent stays: it sits on listings it likes, hovers briefly by the ones it rejects.
const DWELL = { approach: 3400, learning: 2000, avoid: 650 };
const FOCUS_DWELL = 7000;
const HOVER_GAP = 46; // px short of a rejected listing

const ease = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
const bezier = (a: L.Point, c: L.Point, b: L.Point, t: number) =>
  a
    .multiplyBy((1 - t) ** 2)
    .add(c.multiplyBy(2 * (1 - t) * t))
    .add(b.multiplyBy(t * t));
const tangent = (a: L.Point, c: L.Point, b: L.Point, t: number) =>
  c
    .subtract(a)
    .multiplyBy(2 * (1 - t))
    .add(b.subtract(c).multiplyBy(2 * t));

/**
 * The agent on the map: it makes rounds of the portfolio, darting from listing to listing,
 * lands on the ones it likes, hovers by the ones it rejects, and flies straight to a listing
 * the client opens. One Leaflet marker moved by requestAnimationFrame, so the map itself
 * does not re-render while it flies. Under reduced motion it sits on the open listing.
 */
export default function MapAgent({
  stops,
  home,
  focus,
  paused,
  onVisit,
  onOpen,
}: {
  stops: Stop[];
  home: [number, number];
  focus: Stop | undefined;
  paused: boolean;
  onVisit: (key: string | undefined) => void;
  onOpen: (id: string) => void;
}) {
  const map = useMap();
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [note, setNote] = useState<{
    text: string;
    area: string;
    left: boolean;
  } | null>(null);
  const marker = useRef<L.Marker | null>(null);
  const body = useRef<HTMLElement | null>(null);
  const live = useRef({ stops, focus, paused, onVisit, onOpen });
  live.current = { stops, focus, paused, onVisit, onOpen };
  const at = useRef<{ stop: Stop | null; landed: boolean }>({
    stop: null,
    landed: false,
  });
  const flight = useRef<Flight | null>(null);
  const until = useRef(0);
  const heading = useRef(0);
  const recent = useRef<string[]>([]);
  const zooming = useRef(false);
  const still = useRef(
    matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  const setFlying = (on: boolean) =>
    marker.current?.getElement()?.classList.toggle("flying", on);
  const turn = (deg: number, snap = false) => {
    let d = deg - heading.current;
    d = ((((d + 180) % 360) + 360) % 360) - 180;
    heading.current += snap ? d : d * 0.22;
    if (body.current)
      body.current.style.transform = `rotate(${heading.current}deg)`;
  };

  const arrive = (stop: Stop | null, land: boolean) => {
    at.current = { stop, landed: land };
    if (!stop) {
      setNote(null);
      live.current.onVisit(undefined);
      return;
    }
    // Near the right edge the note goes to the fly's left, so the map does not clip it.
    const left =
      map.latLngToContainerPoint(stop.coords).x > map.getSize().x - 230;
    setNote({ text: NOTE[stop.decision], area: stop.area, left });
    live.current.onVisit(land ? stop.key : undefined);
  };

  const depart = (stop: Stop | null, now: number, dwell: number) => {
    const m = marker.current;
    if (!m) return;
    const zoom = map.getZoom();
    const from = map.project(m.getLatLng(), zoom);
    const target = map.project(stop ? stop.coords : home, zoom);
    const span = target.distanceTo(from);
    let to = target,
      land = true;
    if (stop?.decision === "avoid" && span > HOVER_GAP * 1.5) {
      to = target.subtract(
        target.subtract(from).multiplyBy(HOVER_GAP / span),
      );
      land = false;
    }
    const dist = to.distanceTo(from);
    until.current = Infinity;
    at.current = { stop: null, landed: false };
    setNote(null);
    live.current.onVisit(undefined);
    if (dist < 2) {
      until.current = now + dwell;
      arrive(stop, land);
      return;
    }
    // A slight arc, bent to either side, so rounds never look like a conveyor belt.
    const side = Math.random() < 0.5 ? -1 : 1,
      bend = side * (0.14 + Math.random() * 0.2),
      mid = from.add(to).divideBy(2),
      normal = L.point(from.y - to.y, to.x - from.x);
    flight.current = {
      from,
      to,
      zoom,
      ctrl: mid.add(normal.multiplyBy(bend)),
      t0: now,
      dur: Math.min(2100, Math.max(620, 420 + dist * 1.25)),
      stop,
      land,
      dwell,
    };
    setFlying(true);
  };

  const pick = (): Stop | null => {
    const all = live.current.stops;
    if (!all.length) return null;
    const view = map.getBounds().pad(0.05);
    const seen = new Set(recent.current);
    let pool = all.filter(
      (s) => view.contains(s.coords) && !seen.has(s.key),
    );
    if (!pool.length) pool = all.filter((s) => !seen.has(s.key));
    if (!pool.length) pool = all;
    const total = pool.reduce((a, s) => a + s.weight, 0);
    let r = Math.random() * total;
    for (const s of pool) if ((r -= s.weight) <= 0) return s;
    return pool[pool.length - 1];
  };

  // The marker and its React content (the fly and its note) live outside the map's render.
  useEffect(() => {
    // Its own pane above popups: an open listing's popup must not hide the agent sitting on it.
    const pane = map.getPane("agent") || map.createPane("agent");
    pane.style.zIndex = "710";
    const m = L.marker(home, {
      pane: "agent",
      icon: L.divIcon({
        className: "map-agent",
        html: "",
        iconSize: [34, 34],
        // Sits on the top-right corner of a price marker, not over the price.
        iconAnchor: [-9, 35],
      }),
      zIndexOffset: 2000,
      keyboard: false,
      title: "Your agent",
    }).addTo(map);
    marker.current = m;
    m.on("click", () => {
      const s = at.current.stop;
      if (s) live.current.onOpen(s.id);
    });
    setHost(m.getElement() || null);
    const zs = () => (zooming.current = true),
      ze = () => (zooming.current = false);
    map.on("zoomstart", zs).on("zoomend", ze);
    return () => {
      map.off("zoomstart", zs).off("zoomend", ze);
      m.remove();
    };
  }, [map]);

  // The client opened a listing: the agent goes there first and stays a while.
  useEffect(() => {
    const stop = focus || null;
    if (!marker.current) return;
    if (still.current) {
      marker.current.setLatLng(stop ? stop.coords : home);
      arrive(stop, true);
      return;
    }
    if (!stop) return;
    recent.current = [stop.key, ...recent.current].slice(0, 4);
    depart(stop, performance.now(), FOCUS_DWELL);
  }, [focus?.key, host]);

  useEffect(() => {
    if (still.current || !host) return;
    until.current = performance.now() + 1400;
    let raf = 0;
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      const f = flight.current;
      if (zooming.current) return;
      if (f) {
        if (f.zoom !== map.getZoom()) {
          // Zoom changed mid-flight: rescale the path to the new pixel space.
          const k = map.getZoomScale(map.getZoom(), f.zoom);
          f.from = f.from.multiplyBy(k);
          f.ctrl = f.ctrl.multiplyBy(k);
          f.to = f.to.multiplyBy(k);
          f.zoom = map.getZoom();
        }
        const t = Math.min(1, (now - f.t0) / f.dur),
          e = ease(t),
          p = bezier(f.from, f.ctrl, f.to, e),
          v = tangent(f.from, f.ctrl, f.to, Math.min(e, 0.98));
        marker.current!.setLatLng(map.unproject(p, f.zoom));
        if (v.x || v.y) turn((Math.atan2(v.y, v.x) * 180) / Math.PI + 90);
        if (t >= 1) {
          flight.current = null;
          if (f.land) setFlying(false);
          until.current = now + f.dwell;
          arrive(f.stop, f.land);
        }
        return;
      }
      if (live.current.paused || now < until.current) return;
      const next = pick();
      if (!next) return;
      recent.current = [next.key, ...recent.current].slice(
        0,
        Math.min(4, Math.max(1, live.current.stops.length - 1)),
      );
      depart(next, now, DWELL[next.decision]);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [host]);

  // Pausing mid-hover lets the agent settle instead of hanging in the air.
  useEffect(() => {
    if (paused && !flight.current) setFlying(false);
  }, [paused]);

  if (!host) return null;
  return createPortal(
    <>
      <span
        className="map-agent-body"
        ref={(el) => {
          body.current = el;
        }}
      >
        <FlyLive size={34} still={false} />
      </span>
      {note && (
        <span
          className={`map-agent-note ${note.left ? "left" : ""}`}
          key={note.area + note.text}
        >
          {note.area} · {note.text.toLowerCase()}
        </span>
      )}
    </>,
    host,
  );
}
