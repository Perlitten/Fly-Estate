import { useState } from "react";
import {
  ArrowUpRight,
  BedDouble,
  CarFront,
  Maximize,
  ChevronLeft,
  ChevronRight,
  MapPin,
  Heart,
  Minus,
  ThumbsDown,
  Fence,
} from "lucide-react";
import type { Listing } from "./types";
import { money } from "./api";
export const decisions = {
  waiting: "Your agent is forming a view",
  approach: "Recommended for a viewing",
  avoid: "Not recommended",
  maybe: "Worth a second look",
  no_photo: "Photos needed",
};
export function RatingButtons({
  listing,
  busy,
  onRate,
}: {
  listing: Listing;
  busy: boolean;
  onRate: (id: string, v: number | null) => void;
}) {
  return (
    <div className="rating-buttons">
      <button
        disabled={busy}
        className={listing.rating === 1 ? "chosen love" : "love"}
        onClick={() => onRate(listing.id, listing.rating === 1 ? null : 1)}
        aria-label="Would visit"
      >
        <Heart size={18} />
        Would visit
      </button>
      <button
        disabled={busy}
        className={listing.rating === 0 ? "chosen neutral" : "neutral"}
        onClick={() => onRate(listing.id, listing.rating === 0 ? null : 0)}
        aria-label="Maybe"
      >
        <Minus size={18} />
        Maybe
      </button>
      <button
        disabled={busy}
        className={listing.rating === -1 ? "chosen nope" : "nope"}
        onClick={() => onRate(listing.id, listing.rating === -1 ? null : -1)}
        aria-label="Not for me"
      >
        <ThumbsDown size={18} />
        Not for me
      </button>
    </div>
  );
}
export default function ApartmentCard({
  listing,
  compact = false,
  selected = false,
  onSelect,
  onRate,
  busy = false,
}: {
  listing: Listing;
  compact?: boolean;
  selected?: boolean;
  onSelect?: (id: string) => void;
  onRate?: (id: string, v: number | null) => void;
  busy?: boolean;
}) {
  const [photo, setPhoto] = useState(0);
  const l = listing;
  return (
    <article
      className={`apartment-card ${compact ? "compact" : ""} ${selected ? "selected" : ""} ${l.filter_reasons.length ? "filtered" : ""}`}
    >
      <div className="photo-wrap">
        {l.photos.length ? (
          <img
            src={l.photos[photo % l.photos.length]}
            alt={`${l.title} — photo ${photo + 1}`}
            loading="lazy"
          />
        ) : (
          <div className="no-photo">No photos yet</div>
        )}
        <span className="photo-tag">{l.area}</span>
        {l.photos.length > 1 && !compact && (
          <>
            <button
              className="photo-prev"
              aria-label="Previous photo"
              onClick={() =>
                setPhoto((photo + l.photos.length - 1) % l.photos.length)
              }
            >
              <ChevronLeft size={18} />
            </button>
            <button
              className="photo-next"
              aria-label="Next photo"
              onClick={() => setPhoto((photo + 1) % l.photos.length)}
            >
              <ChevronRight size={18} />
            </button>
            <span className="photo-count">
              {photo + 1} / {l.photos.length}
            </span>
          </>
        )}
      </div>
      <div className="card-content">
        <div className="card-price-row">
          <strong>{money(l.price)}</strong>
          <small>/ month</small>
          {l.url && (
            <a
              href={l.url}
              target="_blank"
              rel="noreferrer"
              aria-label="Open original listing"
            >
              <ArrowUpRight size={19} />
            </a>
          )}
        </div>
        <button
          className="card-title"
          onClick={() => onSelect?.(l.id)}
          disabled={!onSelect}
        >
          {l.title}
        </button>
        <div className="amenities">
          <span>
            <BedDouble size={15} />
            {l.bedrooms} bed
          </span>
          <span>
            <Maximize size={14} />
            {l.size} m²
          </span>
          <span>
            <CarFront size={16} />
            {l.parking === "covered"
              ? "Covered"
              : l.parking === "uncovered"
                ? "Uncovered"
                : l.parking === "none"
                  ? "None"
                  : "Unspecified"}
          </span>
        </div>
        <div className="balcony-note">
          <Fence size={13} />
          {l.balcony
            ? l.balcony_size
              ? "Balcony / veranda · " + l.balcony_size + " m²"
              : "Balcony / veranda available"
            : "Balcony unconfirmed"}
          <small>
            {l.vision?.photos_analyzed || 0} /{" "}
            {Math.max(l.photo_urls.length, l.photos.length)} photos
          </small>
        </div>
        {l.photo_downloads?.some((photo) => photo.status !== "available") && (
          <details className="photo-download-status">
            <summary>
              {l.photo_downloads.filter((photo) => photo.status === "unavailable").length} unavailable photos
              {l.photo_downloads.some((photo) => photo.status === "cached") && " · cached copies used"}
            </summary>
            <ul>
              {l.photo_downloads.filter((photo) => photo.status !== "available").map((photo) => (
                <li key={photo.url}>
                  {photo.status === "cached" ? "Cached" : "Unavailable"}: {photo.error || "Download failed"}
                </li>
              ))}
            </ul>
          </details>
        )}
        <div
          className={`decision ${l.filter_reasons.length ? "excluded" : l.prediction.decision}`}
        >
          <span className="status-dot" />
          {l.filter_reasons.length
            ? l.filter_reasons[0]
            : decisions[l.prediction.decision]}
          {l.prediction.distance !== null && (
            <small>
              <MapPin size={12} />≈ {l.prediction.distance} km
            </small>
          )}
        </div>
        {onRate && !l.filter_reasons.length && l.vision && (
          <RatingButtons listing={l} busy={busy} onRate={onRate} />
        )}
      </div>
    </article>
  );
}
