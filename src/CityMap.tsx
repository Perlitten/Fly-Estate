import { memo, useEffect, useMemo, useState } from "react";
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
import {
  ExternalLink,
  Layers,
  LocateFixed,
  MousePointer2,
  Navigation,
  MapPin,
  Plus,
} from "lucide-react";
import type { Job, Listing, MarketOffer, Settings } from "./types";
import { money } from "./api";
import { token } from "./tokens";
import { JobProgress, type AgentSearch } from "./Market";

// Preferred point: a teardrop pin anchored at its tip. Colours come from CSS (.ideal-pin).
const originIcon = L.divIcon({
  className: "ideal-pin",
  html: '<svg width="28" height="36" viewBox="0 0 28 36" aria-hidden="true"><path d="M14 1.5C7.1 1.5 1.5 6.9 1.5 13.6 1.5 22.2 14 34.4 14 34.4S26.5 22.2 26.5 13.6C26.5 6.9 20.9 1.5 14 1.5Z"/><circle cx="14" cy="13.4" r="4.4"/></svg>',
  iconSize: [28, 36],
  iconAnchor: [14, 35],
  popupAnchor: [0, -32],
});
const flyIcon = L.divIcon({
  className: "map-fly",
  html: '<img src="/fly.svg" width="28" height="28" alt="Your agent"/>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});
function Controller({
  choose,
  setIdeal,
  items,
  extra,
  ideal,
  fitTick,
  onPopup,
}: {
  choose: boolean;
  setIdeal: (p: [number, number]) => void;
  items: Listing[];
  extra: [number, number][];
  ideal: [number, number];
  fitTick: number;
  onPopup: (open: boolean) => void;
}) {
  const map = useMap();
  useMapEvents({
    click: (e) => {
      if (choose) setIdeal([e.latlng.lat, e.latlng.lng]);
    },
    popupopen: () => onPopup(true),
    popupclose: () => onPopup(false),
  });
  useEffect(() => {
    if (!fitTick) return;
    const p: [number, number][] = [
      ideal,
      ...items.flatMap((l) => (l.coords ? [l.coords] : [])),
      ...extra,
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
const offerLine = (o: MarketOffer) =>
  [
    o.price ? money(o.price) : "Price on request",
    o.bedrooms === null ? null : o.bedrooms ? `${o.bedrooms} bed` : "Studio",
    o.size ? `${o.size} m²` : null,
  ]
    .filter(Boolean)
    .join(" · ");
/**
 * Bazaraki offers not yet in the file. Offers placed at an area centre share
 * one point, so they are grouped by coordinates and shown with a count.
 * Memoised: the fly animation re-renders the map every 50 ms.
 */
const MarketLayer = memo(function MarketLayer({
  offers,
  job,
  jobUrl,
  failed,
  onAdd,
}: {
  offers: MarketOffer[];
  job: Job | undefined;
  jobUrl: string;
  failed: AgentSearch["failed"];
  onAdd: (url: string) => void;
}) {
  const groups = useMemo(() => {
    const byPoint = new Map<string, MarketOffer[]>();
    for (const o of offers) {
      if (o.listing_id || !o.coords) continue;
      const k = o.coords.map((v) => v.toFixed(5)).join(",");
      byPoint.set(k, [...(byPoint.get(k) || []), o]);
    }
    return [...byPoint.entries()].map(([k, g]) => {
      const approx = g.some((o) => o.coord_kind !== "source"),
        muted = g.every((o) => o.excluded_area),
        size = g.length > 1 ? 24 : approx ? 16 : 12,
        prices = g.flatMap((o) => (o.price ? [o.price] : []));
      const title =
        g.length === 1 || !prices.length
          ? offerLine(g[0])
          : `${g.length} offers · ${money(Math.min(...prices))}–${money(Math.max(...prices))}`;
      const icon = L.divIcon({
        className: `market-marker ${approx ? "approx" : "exact"}${muted ? " muted" : ""}`,
        html: `<span>${g.length > 1 ? g.length : ""}</span>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        popupAnchor: [0, -size / 2],
      });
      return { k, g, approx, title, icon };
    });
  }, [offers]);
  const running = job?.status === "running";
  // Keep the popup clear of the map tools on the right and the legend below.
  const room = useMap().getSize().x - 96,
    popupWidth = { minWidth: Math.min(250, room), maxWidth: Math.min(290, room) };
  return (
    <>
      {groups.map(({ k, g, approx, title, icon }) => (
        <Marker
          key={k}
          position={g[0].coords!}
          icon={icon}
          title={title}
          zIndexOffset={-200}
        >
          <Popup
            className="market-popup-wrap"
            {...popupWidth}
            autoPanPaddingTopLeft={[16, 16]}
            autoPanPaddingBottomRight={[70, 76]}
          >
            <div className="market-popup">
              <header>
                <strong>
                  {g[0].area || g[0].city}
                  {g.length > 1 ? ` · ${g.length} offers` : ""}
                </strong>
                <small>
                  {approx
                    ? "On Bazaraki · placed at the area centre, not the address"
                    : "On Bazaraki · point from the advert map"}
                </small>
              </header>
              <ul>
                {g.map((o) => (
                  <li key={o.id} className={o.excluded_area ? "muted" : ""}>
                    {o.thumb ? (
                      <img
                        src={o.thumb}
                        alt=""
                        width={56}
                        height={42}
                        loading="lazy"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <span className="market-thumb-empty" />
                    )}
                    <div>
                      <b>{offerLine(o)}</b>
                      <small>
                        {[o.area || o.city, o.published]
                          .filter(Boolean)
                          .join(" · ")}
                      </small>
                      {o.excluded_area && (
                        <small>Area excluded in your brief</small>
                      )}
                      {running && job && jobUrl === o.url ? (
                        <JobProgress
                          job={job}
                          label={job.total ? "Reading the advert" : "Starting"}
                        />
                      ) : (
                        <button
                          className="market-add"
                          disabled={running}
                          title={
                            running
                              ? "Your agent is reading other adverts"
                              : undefined
                          }
                          onClick={() => onAdd(o.url)}
                        >
                          <Plus size={13} />
                          Add to the file
                        </button>
                      )}
                      {failed?.url === o.url && (
                        <small className="market-error">{failed.message}</small>
                      )}
                    </div>
                    <a
                      href={o.url}
                      target="_blank"
                      rel="noopener"
                      title="Open on Bazaraki"
                      aria-label={`Open ${offerLine(o)} on Bazaraki`}
                    >
                      <ExternalLink size={15} />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  );
});
export default function CityMap({
  items,
  selected,
  settings,
  onSelect,
  onIdeal,
  agent,
}: {
  items: Listing[];
  selected: Listing | undefined;
  settings: Settings;
  onSelect: (id: string) => void;
  onIdeal: (p: [number, number]) => void;
  agent?: AgentSearch;
}) {
  const [choose, setChoose] = useState(false),
    [fitTick, setFitTick] = useState(0),
    [flyPoint, setFlyPoint] = useState<[number, number]>(settings.ideal),
    [tileErrors, setTileErrors] = useState(0),
    [showMarket, setShowMarket] = useState(true),
    [popupOpen, setPopupOpen] = useState(false);
  const offers = agent?.market?.offers,
    pending = useMemo(
      () => (offers || []).filter((o) => !o.listing_id && o.coords),
      [offers],
    ),
    marketPoints = useMemo(
      () => (showMarket ? pending.map((o) => o.coords!) : []),
      [pending, showMarket],
    ),
    hasApprox = pending.some((o) => o.coord_kind !== "source"),
    marketShown = showMarket && pending.length > 0;
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
    <div
      className={`city-map ${choose ? "choosing" : ""} ${popupOpen ? "popup-open" : ""}`}
    >
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
        <ZoomControl position="bottomright" />
        <Controller
          choose={choose}
          setIdeal={(p) => {
            setChoose(false);
            onIdeal(p);
          }}
          items={items}
          extra={marketPoints}
          ideal={settings.ideal}
          fitTick={fitTick}
          onPopup={setPopupOpen}
        />
        <Circle
          center={settings.ideal}
          radius={settings.radius * 1000}
          pathOptions={{
            color: token("moss"),
            weight: 1.5,
            dashArray: "6 8",
            fillColor: token("leaf"),
            fillOpacity: 0.18,
          }}
        />
        {marketShown && agent && (
          <MarketLayer
            offers={pending}
            job={agent.job}
            jobUrl={agent.jobUrl}
            failed={agent.failed}
            onAdd={agent.add}
          />
        )}
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
                  ? token("clay")
                  : token("ink-2"),
              weight: 2,
              dashArray: "3 8",
              opacity: 0.7,
            }}
          />
        )}
        <Marker position={flyPoint} icon={flyIcon} interactive={false} />
        <Marker
          position={settings.ideal}
          icon={originIcon}
          title="Preferred point · drag to move"
          draggable
          zIndexOffset={1000}
          eventHandlers={{
            dragend: (e) =>
              onIdeal([e.target.getLatLng().lat, e.target.getLatLng().lng]),
          }}
        >
          <Popup>Preferred point · drag the pin to move it</Popup>
        </Marker>
      </MapContainer>
      <div className="map-title">
        <span className="live-dot" />
        <b>CYPRUS</b>
        <small>Your agent’s interest map</small>
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
        {pending.length > 0 && (
          <button
            className={showMarket ? "active" : ""}
            onClick={() => setShowMarket(!showMarket)}
            aria-pressed={showMarket}
            title={
              showMarket ? "Hide offers on Bazaraki" : "Show offers on Bazaraki"
            }
            aria-label="Offers on Bazaraki"
          >
            <Layers size={19} />
          </button>
        )}
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
        {marketShown && (
          <span>
            <i className="legend-dot" />
            On Bazaraki
          </span>
        )}
      </div>
      <div className="map-precision">
        <Navigation size={13} />
        {marketShown
          ? hasApprox
            ? "Dots: advert map pins · dashed rings: area centres · straight-line distance"
            : "Dots: advert map pins · straight-line distance"
          : "Area locations are approximate · straight-line distance"}
      </div>
    </div>
  );
}
