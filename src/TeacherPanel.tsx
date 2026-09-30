import { ArrowRight, Check, Eye } from "lucide-react";
import type { Listing } from "./types";
import { money } from "./api";

export function AssistantInspection({ listing }: { listing: Listing }) {
  const review = listing.teacher_review;
  if (!review) return null;
  return (
    <details className="sensory-details assistant-inspection">
      <summary>
        Assistant inspection ·{" "}
        {review.stale
          ? "needs a fresh check"
          : review.value === 1
            ? "shortlisted"
            : review.value === -1
              ? "rejected"
              : "needs confirmation"}
      </summary>
      <p>
        {listing.evaluation_only
          ? "Saved only for evaluation; this review did not reinforce memory."
          : "An assistant review based on your brief. Your own rating takes priority."}
      </p>
      <ul>
        {review.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <p>Unconfirmed: {review.unknowns.join("; ")}.</p>
      <details>
        <summary>{review.photo_notes.length} photos inspected</summary>
        <ol>
          {review.photo_notes.map((note, index) => (
            <li key={index}>
              Photo {index + 1}: {note}
            </li>
          ))}
        </ol>
      </details>
    </details>
  );
}

export default function TeacherPanel({
  listings,
  onInspect,
}: {
  listings: Listing[];
  onInspect: (id: string) => void;
}) {
  const reviewed = listings.filter((l) => l.teacher_review);
  if (!reviewed.length) return null;
  const accepted = reviewed
    .filter(
      (l) =>
        l.teacher_review?.value === 1 &&
        !l.teacher_review.stale &&
        !l.filter_reasons.length,
    )
    .sort(
      (a, b) =>
        (a.teacher_review?.price_per_m2 ?? Infinity) -
        (b.teacher_review?.price_per_m2 ?? Infinity),
    );
  return (
    <section className="teacher-panel" aria-label="Assistant apartment reviews">
      <div className="learning-section-heading">
        <span className="eyebrow">ASSISTANT / YOUR BRIEF</span>
        <span>
          {reviewed.length} inspected apartments · {accepted.length} shortlisted
        </span>
      </div>
      <h3>A calm interior. Space for the rent.</h3>
      <p>
        Modern condition, visible appliances, no dominant red interiors, a
        checked position relative to the A1 and value per stated square metre.
        These are assistant judgements based on your instructions. Your own
        ratings take priority.
      </p>
      <div className="teacher-cards">
        {accepted.slice(0, 6).map((listing) => {
          const review = listing.teacher_review!;
          return (
            <article className="teacher-card" key={listing.id}>
              <button
                className="teacher-image"
                onClick={() => onInspect(listing.id)}
                aria-label={`Inspect ${listing.area}`}
              >
                <img
                  src={listing.photos[0]}
                  alt={listing.title}
                  loading="lazy"
                />
              </button>
              <div className="teacher-card-copy">
                <span className="eyebrow">
                  <Check size={12} /> Assistant shortlist
                  {listing.evaluation_only ? " · evaluation only" : ""}
                </span>
                <h4>{listing.area}</h4>
                <p>
                  {money(listing.price)} / month · {listing.size} m² ·{" "}
                  {review.price_per_m2?.toFixed(1)} €/m²
                </p>
                <ul>
                  {review.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
                <details>
                  <summary>
                    <Eye size={13} /> {review.inspected_photo_sha256.length}{" "}
                    photos inspected · {review.confidence} confidence
                  </summary>
                  <ol>
                    {review.photo_notes.map((note, index) => (
                      <li key={index}>
                        Photo {index + 1}: {note}
                      </li>
                    ))}
                  </ol>
                  {review.unknowns.length > 0 && (
                    <p>Unconfirmed: {review.unknowns.join("; ")}.</p>
                  )}
                </details>
                <button
                  className="learning-button"
                  onClick={() => onInspect(listing.id)}
                >
                  Inspect apartment <ArrowRight size={15} />
                </button>
                {listing.url && (
                  <a
                    className="backup-link"
                    href={listing.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Original advert ↗
                  </a>
                )}
              </div>
            </article>
          );
        })}
      </div>
      <details className="teacher-rejections">
        <summary>
          Other reviews · {reviewed.length - accepted.length} apartments
        </summary>
        {reviewed
          .filter((l) => !accepted.includes(l))
          .map((l) => (
            <div key={l.id}>
              <button onClick={() => onInspect(l.id)}>
                {l.area} · {money(l.price)} ·{" "}
                {l.teacher_review?.stale
                  ? "Review needs refreshing"
                  : l.teacher_review?.value === -1
                    ? "Rejected"
                    : "Needs confirmation"}
              </button>
              <p>{l.teacher_review?.reasons.join(" · ")}</p>
            </div>
          ))}
      </details>
      <p className="teacher-caveat">
        An evaluation using assistant labels measures how well the models
        reproduce this brief. It does not establish agreement with your own
        taste. Reserved apartments never reinforce memory.
      </p>
    </section>
  );
}
