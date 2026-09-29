import { useEffect, useState } from "react";
import { Play, Square } from "lucide-react";
import type { Gallery, Listing, PhotoReadiness } from "./types";
import { api, count } from "./api";

const labels: Record<PhotoReadiness, string> = {
  ready: "Simulated",
  stale: "Earlier weights or brief",
  queued: "Queued",
  running: "Simulating",
  error: "Failed",
  missing: "Not simulated",
  unavailable: "Cannot be encoded",
};

export default function SpikingPanel({
  listing,
  settingsKey,
  photoIndex,
  onPhoto,
}: {
  listing: Listing;
  settingsKey: string;
  photoIndex: number;
  onPhoto: (index: number) => void;
}) {
  const [gallery, setGallery] = useState<Gallery>(),
    [error, setError] = useState(""),
    [sending, setSending] = useState(false),
    [tick, setTick] = useState(0);
  const active =
    gallery?.job?.status === "queued" || gallery?.job?.status === "running";

  useEffect(() => {
    let alive = true;
    api<Gallery>("/api/engine/gallery/" + listing.id)
      .then((g) => {
        if (!alive) return;
        setGallery(g);
        setError("");
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [listing.id, listing.updated_at, settingsKey, tick]);

  useEffect(() => {
    if (!active) return;
    const t = setTimeout(() => setTick((x) => x + 1), 1500);
    return () => clearTimeout(t);
  }, [active, gallery]);

  const act = (path: string, body?: unknown) => {
    setSending(true);
    api(path, "POST", body)
      .then(() => setTick((x) => x + 1))
      .catch((e) => setError(e.message))
      .finally(() => setSending(false));
  };

  const g = gallery?.listing_id === listing.id ? gallery : undefined;
  const ready = g?.counts.ready || 0,
    stale = g?.counts.stale || 0,
    job = g?.job,
    worker = g?.engine.worker.alive,
    current = photoIndex >= 0 ? g?.photos[photoIndex] : undefined;

  return (
    <div className="spiking-panel">
      <div className="signal-heading">
        <span>04</span>
        <b>Spiking model</b>
        <small>{g?.codec || "LIF"}</small>
      </div>
      <p className={`spiking-worker ${worker ? "alive" : ""}`}>
        <i />
        {!g
          ? "Checking the engine"
          : worker
            ? "Engine on duty"
            : "Engine offline · runs are queued until it starts"}
      </p>
      {g && (
        <>
          <div className="spiking-strip" role="list">
            {g.photos.map((p) => (
              <button
                key={p.position}
                role="listitem"
                className={`${p.status} ${p.position === photoIndex ? "active" : ""}`}
                title={`Photo ${p.position + 1} · ${labels[p.status]}${p.error ? " · " + p.error : ""}`}
                aria-label={`Photo ${p.position + 1}, ${labels[p.status]}`}
                aria-pressed={p.position === photoIndex}
                disabled={p.position >= (listing.vision?.per_photo?.length || 0)}
                onClick={() => onPhoto(p.position)}
              >
                <img src={p.photo} alt="" loading="lazy" />
                <i />
              </button>
            ))}
          </div>
          <div className="spiking-count">
            <span>
              {ready} of {g.total} photos simulated
              {stale ? ` · ${stale} from earlier weights or brief` : ""}
            </span>
            {active && job ? (
              <button
                className="spiking-action"
                disabled={sending || job.cancel_requested > 0}
                onClick={() => act(`/api/simulations/${job.id}/cancel`)}
              >
                <Square size={11} />
                {job.cancel_requested ? "Stopping" : "Stop"}
              </button>
            ) : (
              <button
                className="spiking-action primary-run"
                disabled={sending || ready === g.total}
                onClick={() =>
                  act("/api/simulations", { listing_id: listing.id })
                }
              >
                <Play size={11} />
                {ready === g.total ? "Up to date" : "Run the model"}
              </button>
            )}
          </div>
          {active && job && (
            <div className="spiking-progress" aria-label="Simulation progress">
              <div>
                <i
                  style={{
                    width: `${(job.done / Math.max(job.total, 1)) * 100}%`,
                  }}
                />
              </div>
              <small>
                {job.status === "queued"
                  ? "Waiting for the engine"
                  : `${job.done} / ${job.total} photos`}
                {job.cached ? ` · ${job.cached} from cache` : ""}
              </small>
            </div>
          )}
          {job?.status === "error" && job.error && (
            <p className="spiking-error">{job.error}</p>
          )}
          {current ? (
            current.result ? (
              <div className="spiking-result">
                <div>
                  <span>Kenyon cells active</span>
                  <b>
                    {(current.result.kc_active_fraction * 100).toFixed(1)}%
                  </b>
                </div>
                <div>
                  <span>MBON spikes</span>
                  <b>{count(current.result.mbon_spikes)}</b>
                </div>
                <div>
                  <span>Dopamine (PAM)</span>
                  <b>{current.result.pam_hz.toFixed(1)} Hz</b>
                </div>
                <small>
                  Photo {current.position + 1} · 0.5 s episode
                  {current.status === "stale"
                    ? " · computed with earlier weights or brief"
                    : ""}
                </small>
              </div>
            ) : (
              <p className="spiking-note">
                Photo {current.position + 1}: {labels[current.status]}
                {current.error ? ` · ${current.error}` : ""}
              </p>
            )
          ) : (
            <p className="spiking-note">
              Select a photo to read its mushroom-body response.
            </p>
          )}
        </>
      )}
      {error && <p className="spiking-error">{error}</p>}
    </div>
  );
}
