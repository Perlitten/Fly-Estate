import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "./api";
import type { Job, Listing } from "./types";

export default function ListingSource({
  listing,
  onReload,
}: {
  listing: Listing;
  onReload: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      clearTimeout(timer.current);
    };
  }, []);
  const refresh = async () => {
    setBusy(true);
    setMessage("");
    try {
      const result = await api<{ job: string }>(
        `/api/catalogue/refresh/${listing.id}`,
        "POST",
      );
      const poll = async () => {
        try {
          const job = await api<Job>(`/api/jobs/${result.job}`);
          if (!alive.current) return;
          if (job.status === "running") {
            setMessage(job.phase);
            timer.current = setTimeout(() => void poll(), 1500);
          } else {
            setBusy(false);
            setMessage(
              job.status === "error"
                ? job.error || "Refresh failed"
                : "Source and gallery updated · your choices were preserved",
            );
            await onReload();
          }
        } catch (error) {
          if (alive.current) {
            setBusy(false);
            setMessage((error as Error).message);
          }
        }
      };
      void poll();
    } catch (error) {
      if (alive.current) {
        setBusy(false);
        setMessage((error as Error).message);
      }
    }
  };
  return (
    <details className="sensory-details source-details">
      <summary>
        Source &amp; freshness
        {listing.freshness?.stale ? " · needs a fresh check" : ""}
      </summary>
      <p>
        Last read: {listing.freshness?.checked_at?.slice(0, 10) || "unknown"}.
        Availability is a source snapshot. A listing disappearing from a search
        does not establish that it was removed.
      </p>
      <p>
        Stated floor area: {listing.size} m² · {listing.size_kind || "unknown"}{" "}
        area. Balcony size:{" "}
        {listing.balcony_size == null
          ? "not stated"
          : `${listing.balcony_size} m²`}
        . Shelter:{" "}
        {listing.balcony_covered === true
          ? "confirmed covered"
          : listing.balcony_covered === false
            ? "confirmed uncovered"
            : "not stated"}
        .
      </p>
      <button
        type="button"
        className="learning-button"
        disabled={busy || !listing.url}
        onClick={() => void refresh()}
      >
        <RefreshCw size={15} />
        {busy ? "Refreshing source…" : "Refresh from source"}
      </button>
      {message && <p role="status">{message}</p>}
    </details>
  );
}
