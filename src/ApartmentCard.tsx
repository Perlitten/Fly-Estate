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
  waiting: "Муха ещё учится",
  approach: "Муха хочет сюда",
  avoid: "Муха разворачивается",
  maybe: "Муха сомневается",
  no_photo: "Нужны фотографии",
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
        aria-label="Посмотрел бы"
      >
        <Heart size={18} />
        Посмотрел бы
      </button>
      <button
        disabled={busy}
        className={listing.rating === 0 ? "chosen neutral" : "neutral"}
        onClick={() => onRate(listing.id, listing.rating === 0 ? null : 0)}
        aria-label="Может быть"
      >
        <Minus size={18} />
        Может быть
      </button>
      <button
        disabled={busy}
        className={listing.rating === -1 ? "chosen nope" : "nope"}
        onClick={() => onRate(listing.id, listing.rating === -1 ? null : -1)}
        aria-label="Не моё"
      >
        <ThumbsDown size={18} />
        Не моё
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
            alt={`${l.title} — фото ${photo + 1}`}
            loading="lazy"
          />
        ) : (
          <div className="no-photo">Фотографий пока нет</div>
        )}
        <span className="photo-tag">{l.area}</span>
        {l.photos.length > 1 && !compact && (
          <>
            <button
              className="photo-prev"
              aria-label="Предыдущее фото"
              onClick={() =>
                setPhoto((photo + l.photos.length - 1) % l.photos.length)
              }
            >
              <ChevronLeft size={18} />
            </button>
            <button
              className="photo-next"
              aria-label="Следующее фото"
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
          <small>/ месяц</small>
          {l.url && (
            <a
              href={l.url}
              target="_blank"
              rel="noreferrer"
              aria-label="Открыть исходное объявление"
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
            {l.bedrooms} сп.
          </span>
          <span>
            <Maximize size={14} />
            {l.size} м²
          </span>
          <span>
            <CarFront size={16} />
            {l.parking === "covered"
              ? "Крытая"
              : l.parking === "uncovered"
                ? "Открытая"
                : l.parking === "none"
                  ? "Нет"
                  : "Не указана"}
          </span>
        </div>
        <div className="balcony-note">
          <Fence size={13} />
          {l.balcony
            ? l.balcony_size
              ? "Балкон / веранда · " + l.balcony_size + " м²"
              : "Балкон / веранда есть"
            : "Балкон не подтверждён"}
          <small>
            {l.vision?.photos_analyzed || 0} /{" "}
            {Math.max(l.photo_urls.length, l.photos.length)} фото
          </small>
        </div>
        <div
          className={`decision ${l.filter_reasons.length ? "excluded" : l.prediction.decision}`}
        >
          <span className="status-dot" />
          {l.filter_reasons.length
            ? l.filter_reasons[0]
            : decisions[l.prediction.decision]}
          {l.prediction.distance !== null && (
            <small>
              <MapPin size={12} />≈ {l.prediction.distance} км
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
