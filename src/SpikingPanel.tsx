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
  const active = job?.status === "queued" || job?.status === "running";
  const progress = job ? (job.done / Math.max(job.total, 1)) * 100 : 0;

  return (
    <div className="spiking-panel inspection-analysis">
      <div className="spiking-heading">
        <strong>Photo analysis</strong>
        <Play size={16} />
      </div>
      <p className="spiking-intro">
        {active
          ? "Following each photo through the spiking brain."
          : replayable
            ? "Every photo has a recorded response. Replay it in the connectome."
            : "Follow every photo through the brain and see which neurons respond."}
      </p>
      {g && (
        <>
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
                <Square size={14} />
                {job.cancel_requested ? "Stopping" : "Stop"}
              </button>
            ) : (
              <button
                className="spiking-action primary-run"
                disabled={sending || !g.total}
                onClick={analyze}
              >
                <Play size={14} />
                {sending
                  ? "Preparing analysis…"
                  : replayable
                    ? "Replay analysis"
                    : "Analyze in 3D"}
              </button>
            )}
          </div>
          {active && job && (
            <div
              className="spiking-progress"
              role="progressbar"
              aria-label="Simulation progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress)}
            >
              <div>
                <i
                  style={{
                    width: `${progress}%`,
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
            <p className="spiking-error" role="alert">
              {job.error}
            </p>
          )}
          <details className="analysis-photos">
            <summary>Photo gallery · {g.total} images</summary>
            <div
              className="spiking-strip"
              role="group"
              aria-label="Analysis photos"
            >
              {g.photos.map((p) => (
                <button
                  key={p.position}
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
            <p className="spiking-note">
              Select a photo to inspect its response.
            </p>
          </details>
        </>
      )}
      <p className={`spiking-worker ${worker ? "alive" : ""}`}>
        <i />
        {!g
          ? "Checking the engine"
          : worker
            ? "Engine available"
            : "Engine offline · runs are queued until it starts"}
      </p>
      {g && (
        <details className="analysis-details">
          <summary>Neural response details</summary>
          <small>Spiking model · {g.codec}</small>
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
              Select an individual photo to read its measured neural response.
            </p>
          )}
        </details>
      )}
      {(error || galleryError) && (
        <p className="spiking-error" role="alert">
          {error || galleryError}
        </p>
      )}
    </div>
  );
}
