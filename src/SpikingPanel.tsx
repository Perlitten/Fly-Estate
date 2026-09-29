import { useState } from "react";
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
  photoIndex,
  onPhoto,
  gallery,
  galleryError,
  onRefresh,
  onVisualize,
  onJob,
  onAnalysisError,
}: {
  listing: Listing;
  photoIndex: number;
  onPhoto: (index: number) => void;
  gallery: Gallery | undefined;
  galleryError: string;
  onRefresh: () => void;
  onVisualize: (replayOnly: boolean) => void;
  onJob: (listingId: string, jobId: string) => void;
  onAnalysisError: () => void;
}) {
  const [error, setError] = useState(""),
    [sending, setSending] = useState(false);
  const active =
    gallery?.job?.status === "queued" || gallery?.job?.status === "running";

  const act = (path: string, body?: unknown) => {
    setError("");
    setSending(true);
    api(path, "POST", body)
      .then(onRefresh)
      .catch((e) => setError(e.message))
      .finally(() => setSending(false));
  };

  const analyze = () => {
    onVisualize(replayable);
    if (replayable) return;
    setSending(true);
    setError("");
    api<{ job: { id: string } }>("/api/simulations", "POST", {
      listing_id: listing.id,
    })
      .then(({ job }) => {
        onJob(listing.id, job.id);
        onRefresh();
      })
      .catch((e) => {
        setError(e.message);
        onAnalysisError();
      })
      .finally(() => setSending(false));
  };

  const g = gallery?.listing_id === listing.id ? gallery : undefined;
  const ready = g?.counts.ready || 0,
    stale = g?.counts.stale || 0,
    job = g?.job,
    worker = g?.engine.worker.alive,
    current = photoIndex >= 0 ? g?.photos[photoIndex] : undefined;
  const replayable =
    !!g?.total && g.photos.every((p) => p.status === "ready" && p.replay_key);

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
                disabled={
                  p.position >= (listing.vision?.per_photo?.length || 0)
                }
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
                disabled={sending || !g.total}
                onClick={analyze}
              >
                <Play size={11} />
                {sending
                  ? "Preparing analysis…"
                  : replayable
                    ? "Replay analysis"
                    : "Analyze in 3D"}
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
                  : g.live
                    ? `Photo ${g.live.position + 1} · ${g.live.bins * g.live.bin_ms} / 500 ms`
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
                  <b>{(current.result.kc_active_fraction * 100).toFixed(1)}%</b>
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
              Analyze in 3D to follow each photo through the spiking brain.
            </p>
          )}
        </>
      )}
      {(error || galleryError) && (
        <p className="spiking-error">{error || galleryError}</p>
      )}
    </div>
  );
}
