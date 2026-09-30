import { ArrowRight, Download, Snowflake } from "lucide-react";
import type { LearningState } from "./Learning";
import type { Listing } from "./types";

export default function StudyNext({
  memory,
  listings,
  choices,
  busy,
  onAction,
  onInspect,
  onReview,
}: {
  memory?: LearningState;
  listings: Listing[];
  choices: number;
  busy: boolean;
  onAction: (path: string) => Promise<void>;
  onInspect: (id: string) => void;
  onReview: () => void;
}) {
  const cohort = memory?.prospective;
  const held = listings.filter((l) => cohort?.test_ids.includes(l.id));
  const next =
    held.find((l) => l.rating === null && !l.filter_reasons.length) ||
    held.find((l) => !l.filter_reasons.length);
  const areaCount = new Set(
    listings.filter((l) => l.rating !== null).map((l) => l.area),
  ).size;
  const working =
    memory?.evaluation?.status === "queued" ||
    memory?.evaluation?.status === "running";
  return (
    <section className="study-next" aria-label="Next learning experiment">
      <div>
        <span className="eyebrow">NEXT / YOUR OWN CHOICES</span>
        <h3>{choices} of 50 choices</h3>
        <progress
          value={Math.min(choices, 50)}
          max={50}
          aria-label="Real choices towards the 50-choice pilot"
        />
        <p>
          {(memory?.feedback_counts?.agent || 0) > 0 &&
            `${memory?.feedback_counts?.agent} assistant reviews are tracked separately. `}
          Build a broader record across areas, budgets and interiors.{" "}
          {areaCount > 0
            ? `${areaCount} areas have individual ratings. `
            : "Pairwise choices also count. "}
          Counts describe saved feedback; they do not prove quality.
        </p>
        <button className="learning-button" onClick={onReview}>
          Review apartments <ArrowRight size={16} />
        </button>
        <a className="backup-link" href="/api/session/export" download>
          <Download size={15} />
          Save the full session
        </a>
      </div>
      <div>
        <span className="eyebrow">PROSPECTIVE / FROZEN MODEL</span>
        <h3>
          {cohort
            ? `${cohort.held_groups} unseen groups reserved`
            : "Reserve before you rate"}
        </h3>
        <p>
          {cohort
            ? `Model revision ${cohort.revision} and the brief were frozen before labels were saved. ${cohort.choices} evaluation choices saved. These apartments and their duplicate photos remain excluded from training.`
            : "Reserve up to ten unseen groups, spread across areas. The current checkpoint, training choices and brief are frozen. Feedback on those apartments is saved only for evaluation."}
        </p>
        <div className="study-next-actions">
          {cohort ? (
            <>
              {next && (
                <button
                  className="learning-button"
                  onClick={() => onInspect(next.id)}
                >
                  Review reserved apartments <ArrowRight size={16} />
                </button>
              )}
              <button
                className="learning-button primary"
                disabled={
                  busy ||
                  working ||
                  !cohort.can_evaluate ||
                  !memory?.worker.alive
                }
                onClick={() =>
                  void onAction("/api/learning/evaluate-prospective")
                }
              >
                {cohort.evaluation_id
                  ? "View frozen evaluation"
                  : "Evaluate frozen model"}
              </button>
              {cohort.status === "frozen" && !working && (
                <button
                  className="learning-button"
                  disabled={busy || memory?.pending}
                  onClick={() => void onAction("/api/learning/reserve")}
                >
                  Reserve the next cohort
                </button>
              )}
            </>
          ) : (
            <button
              className="learning-button"
              disabled={
                busy ||
                working ||
                memory?.pending ||
                choices < 5 ||
                !memory?.worker.alive
              }
              onClick={() => void onAction("/api/learning/reserve")}
            >
              <Snowflake size={16} />
              Reserve unseen apartments
            </button>
          )}
        </div>
        {cohort && !cohort.can_evaluate && (
          <p>Save at least three evaluation choices to run the comparison.</p>
        )}
      </div>
    </section>
  );
}
