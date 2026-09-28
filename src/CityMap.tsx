import { useEffect, useState } from "react";
import {
  Circle,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  ZoomControl,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import { LocateFixed, MousePointer2, Navigation, MapPin } from "lucide-react";
import type { Listing, Settings } from "./types";
import { money } from "./api";

const originIcon = L.divIcon({
  className: "ideal-marker",
  html: "<span>⌖</span>",
  iconSize: [36, 36],
  iconAnchor: [18, 18],
});
const flyIcon = L.divIcon({
  className: "map-fly",
  html: '<img src="/fly.svg" width="44" height="44" alt="Fly"/>',
  iconSize: [44, 44],
  iconAnchor: [22, 22],
});
function Controller({
  choose,
  setIdeal,
  items,
  ideal,
  fitTick,
}: {
  choose: boolean;
  setIdeal: (p: [number, number]) => void;
  items: Listing[];
  ideal: [number, number];
  fitTick: number;
}) {
  const map = useMap();
  useMapEvents({
    click: (e) => {
      if (choose) setIdeal([e.latlng.lat, e.latlng.lng]);
    },
  });
  useEffect(() => {
    if (!fitTick) return;
    const p: [number, number][] = [
      ideal,
      ...items.flatMap((l) => (l.coords ? [l.coords] : [])),
    ];
    if (p.length)
      map.fitBounds(L.latLngBounds(p).pad(0.18), {
        maxZoom: 13,
        animate: false,
      });
  }, [fitTick]);
  useEffect(() => {
    map.invalidateSize();
  }, [map]);
  return null;
}
export default function CityMap({
  items,
  selected,
  settings,
  onSelect,
  onIdeal,
}: {
  items: Listing[];
  selected: Listing | undefined;
  settings: Settings;
  onSelect: (id: string) => void;
  onIdeal: (p: [number, number]) => void;
}) {
  const [choose, setChoose] = useState(false),
    [fitTick, setFitTick] = useState(0),
    [flyPoint, setFlyPoint] = useState<[number, number]>(settings.ideal),
    [tileErrors, setTileErrors] = useState(0);
  const groups = new Map<string, Listing[]>();
  items.forEach((l) => {
    if (l.coords) {
      const k = l.coords.join(",");
      groups.set(k, [...(groups.get(k) || []), l]);
    }
  });
  useEffect(() => {
    const target = selected?.coords;
    let step = 0;
    const max =
      selected?.prediction.decision === "approach"
        ? 1
        : selected?.prediction.decision === "avoid"
          ? 0.14
          : 0.48;
    setFlyPoint(settings.ideal);
    if (!target) return;
    const timer = setInterval(() => {
      step = Math.min(step + 0.025, max);
      setFlyPoint([
        settings.ideal[0] + (target[0] - settings.ideal[0]) * step,
        settings.ideal[1] + (target[1] - settings.ideal[1]) * step,
      ]);
      if (step >= max) clearInterval(timer);
    }, 50);
    return () => clearInterval(timer);
  }, [
    selected?.id,
    selected?.prediction.decision,
    settings.ideal[0],
    settings.ideal[1],
  ]);
  return (
    <div className={`city-map ${choose ? "choosing" : ""}`}>
      <MapContainer
        center={settings.ideal}
        zoom={12}
        scrollWheelZoom
        className="leaflet-map"
        zoomControl={false}
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors'
          eventHandlers={{ tileerror: () => setTileErrors((n) => n + 1) }}
        />
        <ZoomControl position="bottomleft" />
        <Controller
          choose={choose}
          setIdeal={(p) => {
            setChoose(false);
            onIdeal(p);
          }}
          items={items}
          ideal={settings.ideal}
          fitTick={fitTick}
        />
        <Circle
          center={settings.ideal}
          radius={settings.radius * 1000}
          pathOptions={{
            color: "#6f9842",
            weight: 1.5,
            dashArray: "6 8",
            fillColor: "#cde695",
            fillOpacity: 0.18,
          }}
        />
        <Marker
          position={settings.ideal}
          icon={originIcon}
          draggable
          eventHandlers={{
            dragend: (e) =>
              onIdeal([e.target.getLatLng().lat, e.target.getLatLng().lng]),
          }}
        >
          <Popup>Preferred area · drag the point</Popup>
        </Marker>
        {Array.from(groups.entries()).map(([k, g]) => {
          const chosen = g.find((l) => l.id === selected?.id) || g[0];
          const decision = chosen.filter_reasons.length
            ? "excluded"
            : chosen.prediction.decision;
          const icon = L.divIcon({
            className: `price-marker ${decision} ${g.some((l) => l.id === selected?.id) ? "active" : ""}`,
            html: `<span>€${Math.round(chosen.price).toLocaleString("en-US")}${g.length > 1 ? `<b>+${g.length - 1}</b>` : ""}</span>`,
            iconSize: [90, 34],
            iconAnchor: [45, 17],
          });
          return (
            <Marker
              key={k}
              position={chosen.coords!}
              icon={icon}
              eventHandlers={{ click: () => onSelect(chosen.id) }}
            >
              <Popup>
                <div className="map-popup">
                  <strong>{chosen.area}</strong>
                  <small>
                    Location:{" "}
                    {chosen.coord_kind === "area"
                      ? "approximate area location"
                      : "source coordinates"}
                  </small>
                  {g.map((l) => (
                    <button key={l.id} onClick={() => onSelect(l.id)}>
                      {l.bedrooms} bed · {l.size} m² <b>{money(l.price)}</b>
                    </button>
                  ))}
                </div>
              </Popup>
            </Marker>
          );
        })}
        {selected?.coords && (
          <Polyline
            positions={[settings.ideal, selected.coords]}
            pathOptions={{
              color:
                selected.prediction.decision === "avoid"
                  ? "#b98472"
                  : "#516b43",
              weight: 2,
              dashArray: "3 8",
              opacity: 0.7,
            }}
          />
        )}
        <Marker position={flyPoint} icon={flyIcon} interactive={false} />
      </MapContainer>
      <div className="map-title">
        <span className="live-dot" />
        <b>LIMASSOL, CYPRUS</b>
        <small>Your fly’s interest map</small>
      </div>
      <div className="map-tools">
        <button
          onClick={() => setFitTick((v) => v + 1)}
          title="Show all apartments"
          aria-label="Show all apartments"
        >
          <LocateFixed size={19} />
        </button>
        <button
          className={choose ? "active" : ""}
          onClick={() => setChoose(!choose)}
          title="Change preferred point"
          aria-label="Change preferred point"
        >
          <MousePointer2 size={19} />
        </button>
      </div>
      {choose && (
        <div className="map-instruction">
          <MapPin size={16} />
          Click on the map where you would like to live
        </div>
      )}
      {tileErrors > 5 && (
        <div className="map-instruction map-error">
          Could not load map tiles. Your markers are preserved.
        </div>
      )}
      <div className="map-legend">
        <span>
          <i className="legend-circle green" />
          Wants to go here
        </span>
        <span>
          <i className="legend-circle red" />
          Turns away
        </span>
        <span>
          <i className="legend-circle gray" />
          Still learning
        </span>
      </div>
      <div className="map-precision">
        <Navigation size={13} />
        Area locations are approximate · straight-line distance
      </div>
    </div>
  );
}
