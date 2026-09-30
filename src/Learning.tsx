import { useEffect, useState } from "react";
import { api, count } from "./api";
import "./learning.css";

export type MemoryEdge = {
  pre: number;
  post: number;
  pre_id: string;
  post_id: string;
  before_mv: number;
  after_mv: number;
};
export type MemoryRun = {
  revision: number;
  status: "done" | "error";
  listing_id: string;
  title?: string;
  changed_connections: number;
  shown_connections: number;
  checkpoint: string;
  active_choices: number;
  rewarded_choices: number;
  episodes: number;
  error?: string;
  probe?: {
    before: { photos: number; mbon_spikes: number };
    after: { photos: number; mbon_spikes: number };
  };
};
type Metric = {
  pairwise_accuracy: number | null;
  pairs: number;
  correct: number;
  wilson_95: number[] | null;
  auc: number | null;
  ties: number;
  cluster_95?: number[] | null;
  independent_components?: number;
  precision_at_k?: number | null;
  ranking_k?: number;
  rated_apartments?: number;
};
export type LearningState = {
  feedback_counts?: { human: number; agent: number };
  revision: number;
  target: number;
  pending: boolean;
  checkpoint: string | null;
  analysis_stamp: [number, string | null];
  worker: { alive: boolean };
  runs: MemoryRun[];
  progress: { phase: string; done: number; total: number } | null;
  evaluation_progress: { phase: string; done: number; total: number } | null;
  prospective?: {
    id: string;
    status: string;
    created: string;
    checkpoint: string;
    revision: number;
    held_groups: number;
    test_ids: string[];
    choices: number;
    can_evaluate: boolean;
    evaluation_id?: string | null;
  } | null;
  evaluation: {
    id: string;
    status: string;
    revision: number;
    error: string | null;
    result: {
      label_sources?: {
        train: { human: number; agent: number };
        test: { human: number; agent: number };
      };
      protocol?: string;
      cohort?: string | null;
      frozen_checkpoint?: string | null;
      sensory?: {
        evaluation_mode: string;
        memory_training_modes: string[];
        cross_codec: boolean;
      };
      independent_components?: number;
      worker_peak_rss_mb?: number;
      rss_scope?: string;
      latency?: Record<
        string,
        {
          photos: number;
          mean_photo_seconds: number;
          p95_photo_seconds: number;
        }
      >;
      plasticity_cluster_95?: number[] | null;
      train_choices: number;
      test_choices: number;
      test_apartments: number;
      train_apartments: number;
      photo_coverage: number;
      seconds: number;
      plasticity_delta: number | null;
      conclusion: string;
      models: Record<string, Metric>;
      test_predictions: { id: string; title: string; score: number }[];
    } | null;
  } | null;
};
export function useLearning() {
  const [memory, setMemory] = useState<LearningState>();
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true,
      running = false;
    const poll = async () => {
      if (running) return;
      running = true;
      try {
        const result = await api<LearningState>("/api/learning");
        if (alive) {
          setMemory(result);
          setError("");
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      } finally {
        running = false;
      }
    };
    void poll();
    const timer = setInterval(poll, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  return { memory, error };
}

export function MemoryDetails({
  memory,
  listingId,
  onConnections,
  onReplay,
  onReport,
}: {
  memory?: LearningState;
  listingId: string;
  onConnections: (run: MemoryRun) => Promise<void>;
  onReplay: (run: MemoryRun, phase: "before" | "after") => Promise<void>;
  onReport: () => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const run = memory?.runs.find(
    (r) => r.status === "done" && r.listing_id === listingId,
  );
  const act = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="memory-details">
      <summary>
        Learned memory
        {memory?.pending
          ? " · updating"
          : run
            ? ` · ${count(run.changed_connections)} changed connections`
            : ""}
      </summary>
      {memory?.progress && (
        <p role="status">
          Replaying choices · {memory.progress.done} / {memory.progress.total}{" "}
          photos
        </p>
      )}
      {run ? (
        <>
          <p>
            {count(run.changed_connections)} KC → MBON connections changed in
            this revision. {run.shown_connections} strongest changes available
            in 3D.
          </p>
          <div className="memory-actions">
            <button
              disabled={busy}
              onClick={() => void act(() => onConnections(run))}
            >
              Show changed connections
            </button>
            <button
              disabled={busy || !run.probe}
              onClick={() => void act(() => onReplay(run, "before"))}
            >
              Before learning
            </button>
            <button
              disabled={busy || !run.probe}
              onClick={() => void act(() => onReplay(run, "after"))}
            >
              After learning
            </button>
          </div>
          {run.probe ? (
            <p>
              Matched photo and random seed. Average MBON spikes across{" "}
              {run.probe?.before.photos} photos:{" "}
              {run.probe?.before.mbon_spikes.toFixed(1)} →{" "}
              {run.probe?.after.mbon_spikes.toFixed(1)}.
            </p>
          ) : (
            <p>
              Memory was updated. This revision has no available photo for a
              matched replay.
            </p>
          )}
          <small>
            Lower activity demonstrates a memory effect; recommendation quality
            is measured separately.
          </small>
        </>
      ) : (
        <p>
          “Would visit” rewards this apartment’s photos. A pairwise winner
          receives the same reinforcement. Dislikes and ties train the
          recommendation readout without a dopamine pulse.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <button className="memory-link" onClick={onReport}>
        Open learning report →
      </button>
    </details>
  );
}

export { default } from "./LearningScreen";
