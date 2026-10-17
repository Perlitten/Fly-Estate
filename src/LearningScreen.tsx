import { useState } from "react";
import {
  ArrowDownRight,
  ArrowRight,
  Check,
  ChevronDown,
  Eye,
  LoaderCircle,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { api, count, money } from "./api";
import { CountUp } from "./effects";
import MemoryMap from "./MemoryMap";
import StudyNext from "./StudyNext";
import TeacherPanel from "./TeacherPanel";
import type { LearningState } from "./Learning";
import type { Listing } from "./types";
import "./learning-screen.css";

const percent = (value: number | null | undefined) =>
  value == null ? "—" : `${Math.round(value * 100)}%`;
const modelNames: Record<string, string> = {
  price_distance: "Price & distance",
  rate_readout: "Rate model",
  spiking_fixed: "Fixed spiking brain",
  spiking_memory: "Learned spiking brain",
  clip_readout: "CLIP + simple readout",
  spiking_rewired: "Rewired KC→MBON control",
};
const modelOrder = [
  "spiking_memory",
  "spiking_fixed",
  "spiking_rewired",
  "clip_readout",
  "rate_readout",
  "price_distance",
];

export default function LearningScreen({
  memory,
  error,
  onInspect,
  onReview,
  choices,
  listings,
}: {
  memory?: LearningState;
  error: string;
  onInspect: (id: string, revision?: number) => void;
  onReview: () => void;
  choices: number;
  listings: Listing[];
}) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const action = async (path: string) => {
    setBusy(true);
    setActionError("");
    try {
      await api(path, "POST");
    } catch (exception) {
      setActionError((exception as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const evaluation = memory?.evaluation;
  const result = evaluation?.result;
  const runs = memory?.runs.filter((run) => run.status === "done") || [];
  const latest = runs[0];
  const apartment = listings.find(
    (listing) => listing.id === latest?.listing_id,
  );
  const before = latest?.probe?.before.mbon_spikes;
  const after = latest?.probe?.after.mbon_spikes;
  const responseChange =
    before != null && after != null && before > 0
      ? (after / before - 1) * 100
      : null;
  const working =
    evaluation?.status === "queued" || evaluation?.status === "running";
  const progress = memory?.evaluation_progress || memory?.progress;
  const failed = memory?.runs[0]?.status === "error";
  const stale =
    !!evaluation && !result?.cohort && evaluation.revision !== memory?.target;
  const learned = result?.models.spiking_memory;
  const ratingOnly =
    !!result && Object.values(result.models).every((metric) => !metric.pairs);
  const delta = ratingOnly
    ? learned?.auc != null && result?.models.spiking_fixed.auc != null
      ? learned.auc - result.models.spiking_fixed.auc
      : null
    : result?.plasticity_delta;
  const canEvaluate =
    !busy &&
    !working &&
    choices >= 7 &&
    !memory?.progress &&
    !!memory?.worker.alive;
  const photos = apartment?.photos || [];
  const teacherCount = memory?.feedback_counts?.agent || 0;
  const humanCount = memory?.feedback_counts?.human ?? choices;

  return (
    <section
      className="learning-view"
      aria-label="Learning and measured evidence"
    >
      {(error || actionError) && (
        <p className="error-banner" role="alert">
          {actionError || error}
        </p>
      )}

      <div className="learning-hero">
        <div className="learning-hero-main">
          <div className="learning-hero-copy">
            <div className="learning-kicker">
              <span className="eyebrow">YOUR AGENT’S MEMORY</span>
              <span className="memory-state">
                <i />
                {memory?.pending
                  ? "Updating"
                  : latest
                    ? `Saved · revision ${memory?.revision}`
                    : "Ready to learn"}
              </span>
            </div>
            <h2>
              {teacherCount ? "Learning your brief." : "Your choices"}
              <br />
              <em>
                {teacherCount
                  ? "Every choice leaves a trace."
                  : "leave a trace."}
              </em>
            </h2>
            <p>
              {teacherCount
                ? `${humanCount} human choices and ${teacherCount} assistant reviews, with every photo inspected. Assistant feedback follows your brief; your own ratings take priority.`
                : "Every apartment you choose changes how your agent responds. Here is the memory you have made."}
            </p>
            <button
              className="memory-hero-action"
              onClick={() =>
                latest
                  ? onInspect(latest.listing_id, latest.revision)
                  : onReview()
              }
            >
              {latest
                ? "Inspect this memory in 3D"
                : "Choose your first apartment"}
              <ArrowRight size={18} />
            </button>
            {!!photos.length && (
              <div className="memory-photo-strip">
                <div>
                  {photos.slice(0, 4).map((photo, index) => (
                    <img
                      key={`${photo}-${index}`}
                      src={photo}
                      alt={`Photo ${index + 1} from the latest memory probe`}
                      loading="lazy"
                    />
                  ))}
                </div>
                <span>
                  <b>{latest?.probe?.before.photos || photos.length} photos</b>
                  <br />
                  {latest?.probe
                    ? "in the latest recorded probe"
                    : "in the latest rewarded gallery"}
                </span>
              </div>
            )}
          </div>
          <MemoryMap revision={latest?.revision} />
        </div>
        <div className="learning-hero-stats">
          <div>
            <strong>
              <CountUp
                value={choices}
                format={(value) => count(Math.round(value))}
              />
            </strong>
            <span>
              {teacherCount ? "feedback entries on file" : "choices on file"}
            </span>
          </div>
          <div>
            <strong>
              <CountUp
                value={latest?.changed_connections || 0}
                format={(value) => count(Math.round(value))}
              />
            </strong>
            <span>connections changed in the latest revision</span>
          </div>
          <div>
            <strong>
              {responseChange == null
                ? "—"
                : `${responseChange > 0 ? "+" : "−"}${Math.abs(responseChange).toFixed(1)}%`}
            </strong>
            <span>MBON response change · matched photos</span>
          </div>
        </div>
      </div>

      {progress && (
        <div className="learning-progress" role="status">
          <LoaderCircle size={17} className="spin" />
          <span>
            {progress.phase === "reinforcement"
              ? "Reinforcing saved feedback"
              : progress.phase.replaceAll("_", " ")}{" "}
            · {progress.done} / {progress.total} photos
          </span>
          <progress max={Math.max(progress.total, 1)} value={progress.done} />
        </div>
      )}
      {memory?.pending && !progress && !failed && (
        <p className="learning-status" role="status">
          Memory update queued
          {memory.worker.alive ? "." : " · the engine worker is offline."}
        </p>
      )}
      {failed && (
        <div className="learning-status" role="alert">
          <span>{memory?.runs[0].error}</span>
          <button
            className="learning-button"
            disabled={busy}
            onClick={() => void action("/api/learning/retry")}
          >
            Retry memory update <RefreshCw size={15} />
          </button>
        </div>
      )}

      <TeacherPanel listings={listings} onInspect={onInspect} />

      <div className="learning-section-heading">
        <span className="eyebrow">01 / THE MEMORY EFFECT</span>
        <span>Observed neural change</span>
      </div>
      <div className="response-study">
        <div className="study-copy">
          <h3>
            A different response.
            <br />
            <em>The same photographs.</em>
          </h3>
          <p>
            The same photos and random seeds, replayed before and after
            learning. A changed response shows that memory has an effect.
          </p>
          <span className="study-disclaimer">
            Recommendation quality is measured separately below.
          </span>
        </div>
        <div
          className="response-plot"
          role="img"
          aria-label={
            before != null && after != null
              ? `Average MBON spikes per photo: ${before.toFixed(1)} before and ${after.toFixed(1)} after learning. ${latest?.probe?.before.photos} matched photos.`
              : "A matched before and after probe is not yet available."
          }
        >
          {before != null && after != null ? (
            <>
              <div className="response-bar-row">
                <span>Before learning</span>
                <b>
                  {count(Math.round(before))}
                  <small>spikes / photo</small>
                </b>
                <div className="response-bar-track">
                  <i
                    style={{
                      width: `${(100 * before) / Math.max(before, after, 1)}%`,
                    }}
                  />
                </div>
              </div>
              <div className="response-bar-row learned">
                <span>After learning</span>
                <b>
                  {count(Math.round(after))}
                  <small>spikes / photo</small>
                </b>
                <div className="response-bar-track">
                  <i
                    style={{
                      width: `${(100 * after) / Math.max(before, after, 1)}%`,
                    }}
                  />
                </div>
              </div>
              <div className="response-plot-note">
                <ArrowDownRight size={18} />
                <span>
                  {latest?.probe?.before.photos} matched photos · 500 ms per
                  photo
                </span>
              </div>
            </>
          ) : (
            <div className="learning-empty">
              <Sparkles size={24} />
              <p>
                Choose an apartment you would visit to create a recorded memory.
              </p>
              <button className="learning-button" onClick={onReview}>
                Browse apartments <ArrowRight size={16} />
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="learning-section-heading">
        <span className="eyebrow">02 / APARTMENTS IT HADN’T LEARNED FROM</span>
        <span>Preference agreement</span>
      </div>
      <article className="generalisation-study">
        <div className="generalisation-header">
          <div>
            <h3>
              {result?.label_sources?.test.agent
                ? "Can it follow your brief?"
                : "Does it see what you see?"}
            </h3>
            <p>
              {result
                ? `${result.test_choices} held-out choices · ${result.test_apartments} unseen apartments · ${result.train_choices} training choices`
                : "Reserve reviewed apartments, then compare each model on the same held-out choices."}
            </p>
          </div>
          <button
            className="learning-button primary"
            disabled={!canEvaluate}
            onClick={() =>
              void action(
                result?.cohort
                  ? "/api/learning/evaluate-prospective"
                  : "/api/learning/evaluate",
              )
            }
          >
            {working ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <RefreshCw size={16} />
            )}
            {working
              ? "Evaluating…"
              : result
                ? result.cohort
                  ? "Frozen evaluation"
                  : "Run evaluation again"
                : "Evaluate unseen apartments"}
          </button>
        </div>
        {choices < 7 && (
          <p className="learning-note">
            At least seven choices across distinct apartments are needed for a
            pilot.
          </p>
        )}
        {!memory?.worker.alive && (
          <p className="learning-note">
            Evaluation becomes available when the engine worker is online.
          </p>
        )}
        {evaluation?.error && (
          <p role="alert" className="inline-error">
            {evaluation.error}
          </p>
        )}
        {stale && (
          <p className="evaluation-stale" role="status">
            Your choices have changed. These results belong to revision{" "}
            {evaluation?.revision}; run again to evaluate the current history.
          </p>
        )}
        {result ? (
          <>
            {!!result.label_sources?.test.agent && (
              <p className="learning-note">
                {result.label_sources.test.agent} assistant labels,{" "}
                {result.label_sources.test.human} human labels. This measures
                imitation of the brief, not agreement with your personal taste.
              </p>
            )}
            <div className="evaluation-visual">
              <div
                className="agreement-chart"
                role="img"
                aria-label={`Agreement on held-out choices. ${modelOrder
                  .filter((key) => result.models[key])
                  .map((key) => {
                    const metric = result.models[key];
                    const interval = metric.cluster_95 || metric.wilson_95;
                    return ratingOnly
                      ? `${modelNames[key]}: rating AUC ${metric.auc?.toFixed(2) ?? "unavailable"} on ${metric.rated_apartments} decisive rated apartments`
                      : `${modelNames[key]}: ${metric.correct} of ${metric.pairs} choices, ${percent(metric.pairwise_accuracy)}, ${metric.cluster_95 ? "component bootstrap" : "descriptive Wilson"} 95% interval ${interval?.map(percent).join(" to ") || "unavailable"}`;
                  })
                  .join(". ")}`}
              >
                <div className="agreement-axis">
                  <span>{ratingOnly ? "AUC 0" : "0%"}</span>
                  <span>{ratingOnly ? "0.5" : "50%"}</span>
                  <span>{ratingOnly ? "1" : "100%"}</span>
                </div>
                {modelOrder
                  .filter((key) => result.models[key])
                  .map((key) => {
                    const metric = result.models[key];
                    const interval = ratingOnly
                      ? null
                      : metric.cluster_95 || metric.wilson_95;
                    const value = ratingOnly
                      ? metric.auc
                      : metric.pairwise_accuracy;
                    return (
                      <div
                        key={key}
                        className={`agreement-row ${key === "spiking_memory" ? "learned" : ""}`}
                      >
                        <div className="agreement-model">
                          <span>{modelNames[key]}</span>
                          <small>
                            {ratingOnly
                              ? `${metric.rated_apartments ?? 0} decisive ratings`
                              : `${metric.correct} / ${metric.pairs} choices`}
                          </small>
                        </div>
                        <div
                          className="agreement-track"
                          title={
                            ratingOnly
                              ? `${modelNames[key]} rating AUC: ${value?.toFixed(2) ?? "unavailable"}`
                              : `${modelNames[key]}: ${percent(value)}, ${metric.cluster_95 ? "component bootstrap" : "descriptive Wilson"} 95% interval ${interval?.map(percent).join("–") || "unavailable"}`
                          }
                        >
                          <i
                            className="agreement-fill"
                            style={{
                              width: percent(value ?? 0),
                            }}
                          />
                          {interval && (
                            <i
                              className="agreement-interval"
                              style={{
                                left: percent(interval[0]),
                                width: percent(interval[1] - interval[0]),
                              }}
                            />
                          )}
                          {value != null && (
                            <i
                              className="agreement-point"
                              style={{
                                left: percent(value),
                              }}
                            />
                          )}
                        </div>
                        <strong>
                          {ratingOnly
                            ? (value?.toFixed(2) ?? "—")
                            : percent(value)}
                        </strong>
                      </div>
                    );
                  })}
                <p className="chart-key">
                  <span />
                  {ratingOnly ? (
                    `AUC ranks positive against negative labels; 0.5 is chance ranking. Neutral reviews are excluded. No AUC uncertainty interval is estimated for this small pilot.`
                  ) : (
                    <>
                      Line:{" "}
                      {learned?.cluster_95
                        ? "component bootstrap"
                        : "descriptive Wilson"}{" "}
                      95% interval. {learned?.pairs || 0} test pairs.
                    </>
                  )}
                </p>
              </div>
              <aside className="evaluation-verdict">
                <span className="eyebrow">CURRENT EVIDENCE</span>
                <strong>
                  {delta == null
                    ? "—"
                    : `${delta > 0 ? "+" : ""}${(delta * (ratingOnly ? 1 : 100)).toFixed(ratingOnly ? 2 : 1)}`}
                </strong>
                <span className="verdict-unit">
                  {ratingOnly
                    ? "rating AUC difference vs. fixed weights"
                    : "percentage points vs. fixed weights"}
                </span>
                <h4>
                  {delta != null && delta < 0
                    ? "Below fixed weights in this pilot."
                    : delta === 0
                      ? "No measured gain yet."
                      : "An early pilot."}
                </h4>
                <p>{result.conclusion}</p>
                {result.plasticity_cluster_95 && (
                  <p>
                    Paired component bootstrap:{" "}
                    {result.plasticity_cluster_95
                      .map((v) => `${(v * 100).toFixed(1)} pp`)
                      .join(" to ")}
                    .
                  </p>
                )}
                <button onClick={onReview}>
                  Add more real choices <ArrowRight size={16} />
                </button>
              </aside>
            </div>
            <div className="held-out-gallery">
              {result.test_predictions.map((prediction) => {
                const listing = listings.find(
                  (item) => item.id === prediction.id,
                );
                return (
                  <button
                    className="held-out-card"
                    key={prediction.id}
                    onClick={() => onInspect(prediction.id)}
                  >
                    <div className="held-out-photo">
                      {listing?.photos[0] ? (
                        <img
                          src={listing.photos[0]}
                          alt={listing.title}
                          loading="lazy"
                        />
                      ) : (
                        <span>
                          <Eye size={24} />
                          Photo unavailable
                        </span>
                      )}
                      <span className="held-out-badge">
                        Held out from training
                      </span>
                      <span className="held-out-open">
                        <ArrowRight size={18} />
                      </span>
                    </div>
                    <div className="held-out-caption">
                      <div>
                        <strong>{listing?.area || prediction.title}</strong>
                        <span>
                          {listing
                            ? `${money(listing.price)} / month · ${listing.bedrooms} bedrooms`
                            : "Open this apartment"}
                        </span>
                      </div>
                      <span className="held-out-score">
                        <b>{percent(prediction.score)}</b>pilot fit
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
            <details className="learning-method">
              <summary>
                How this was measured <ChevronDown size={17} />
              </summary>
              <p>
                {result.cohort
                  ? "Groups were reserved and the model was frozen before labels were saved."
                  : "About 20% of reviewed apartment groups were held out for this retrospective pilot."}{" "}
                Their choices cannot reinforce the evaluation memory or train
                its readout. Duplicate photos stay in the same group.{" "}
                {percent(result.photo_coverage)} photo coverage ·{" "}
                {Math.round(result.seconds)} seconds · memory revision{" "}
                {evaluation?.revision}.
              </p>
              <p>
                Intervals are descriptive: comparisons sharing an apartment are
                correlated. Repeating this evaluation uses the same split and
                does not add independent evidence. The apartment cards show
                pilot scores; opening one shows your current saved memory.
              </p>
              {result.sensory && (
                <p>
                  Inference:{" "}
                  {result.sensory.evaluation_mode === "pure"
                    ? "Pure Fly"
                    : "Cyborg Fly"}
                  . Saved memory training:{" "}
                  {result.sensory.memory_training_modes
                    .map((mode) =>
                      mode === "pure" ? "Pure Fly" : "Cyborg Fly",
                    )
                    .join(", ") || "no rewarded episodes"}
                  .
                  {result.sensory.cross_codec &&
                    " This measures transfer between sensory codecs; the saved choices are replayed with their original codec."}
                </p>
              )}
              {result.label_sources && (
                <p>
                  Training labels: {result.label_sources.train.human} human,{" "}
                  {result.label_sources.train.agent} assistant. Evaluation
                  labels: {result.label_sources.test.human} human,{" "}
                  {result.label_sources.test.agent} assistant.{" "}
                  {result.label_sources.test.agent > 0 &&
                    "This measures agreement with the assistant's interpretation of your brief; it does not prove your personal preference agreement."}
                </p>
              )}
              {result.independent_components != null && (
                <p>
                  {result.independent_components} independent comparison{" "}
                  {result.independent_components === 1
                    ? "component"
                    : "components"}
                  . Component bootstrap requires at least three components; the
                  displayed Wilson intervals remain descriptive when that is
                  unavailable. Precision@k ranks only explicitly rated apartment
                  groups. Worker peak memory: {result.worker_peak_rss_mb} MB (
                  {result.rss_scope}).
                </p>
              )}
              {result.latency && (
                <p>
                  {Object.entries(result.latency)
                    .map(
                      ([key, value]) =>
                        `${modelNames[key]}: ${value.mean_photo_seconds.toFixed(2)} s/photo, p95 ${value.p95_photo_seconds.toFixed(2)} s`,
                    )
                    .join(" · ")}
                </p>
              )}
              <a className="backup-link" href="/api/learning/report" download>
                Download this evaluation as JSON
              </a>
              <div className="learning-table">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Model</th>
                      <th scope="col">Agreement</th>
                      <th scope="col">95% interval</th>
                      <th scope="col">Correct / pairs</th>
                      <th scope="col">Rating AUC</th>
                      <th scope="col">Precision@k</th>
                    </tr>
                  </thead>
                  <tbody>
                    {modelOrder
                      .filter((key) => result.models[key])
                      .map((key) => {
                        const metric = result.models[key];
                        return (
                          <tr key={key}>
                            <th scope="row">{modelNames[key]}</th>
                            <td>{percent(metric.pairwise_accuracy)}</td>
                            <td>
                              {(metric.cluster_95 || metric.wilson_95)
                                ?.map(percent)
                                .join("–") || "—"}
                            </td>
                            <td>
                              {metric.correct} / {metric.pairs}
                            </td>
                            <td>
                              {metric.auc == null ? "—" : metric.auc.toFixed(2)}
                            </td>
                            <td>
                              {metric.precision_at_k == null
                                ? "—"
                                : `${percent(metric.precision_at_k)} (k=${metric.ranking_k})`}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        ) : (
          <div className="evaluation-empty">
            <Eye size={28} />
            <h4>Your next evidence, waiting.</h4>
            <p>
              Run a pilot to compare learned memory, fixed weights, the rate
              model and price plus distance on unseen apartments.
            </p>
          </div>
        )}
      </article>

      <StudyNext
        memory={memory}
        listings={listings}
        choices={humanCount}
        busy={busy}
        onAction={action}
        onInspect={onInspect}
        onReview={onReview}
      />

      <div className="learning-section-heading">
        <span className="eyebrow">03 / THE RECORD</span>
        <span>Saved memory, traceable changes</span>
      </div>
      <details className="learning-history">
        <summary>
          <span>
            <Check size={17} />
            {runs.length
              ? `${runs.length} recorded ${runs.length === 1 ? "revision" : "revisions"}`
              : "Your first memory is waiting"}
          </span>
          <ChevronDown size={17} />
        </summary>
        <div className="memory-history-list">
          {runs.length ? (
            runs.map((run) => (
              <button
                key={run.revision}
                onClick={() => onInspect(run.listing_id, run.revision)}
              >
                <span className="history-number">
                  {String(run.revision).padStart(2, "0")}
                </span>
                <span>
                  <strong>{run.title || "Saved apartment"}</strong>
                  <small>
                    {run.active_choices} active choices · {run.episodes} photo
                    episodes
                  </small>
                </span>
                <span>
                  {count(run.changed_connections)} connections{" "}
                  <ArrowRight size={17} />
                </span>
              </button>
            ))
          ) : (
            <p>
              A positive choice or a winning apartment creates the first memory
              recording.
            </p>
          )}
        </div>
      </details>
      <div className="learning-maintenance">
        <p>
          Positive choices reinforce photo memories. Dislikes train the readout.
          Clearing a choice rebuilds memory from the original weights.
        </p>
        <button
          className="learning-button"
          disabled={busy || !!memory?.progress || working}
          onClick={() => void action("/api/learning/sync")}
        >
          Learn from saved choices <RefreshCw size={15} />
        </button>
      </div>
    </section>
  );
}
