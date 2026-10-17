import { useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import type { MemoryEdge } from "./Learning";
import { token } from "./tokens";

type Circuit = { positions: Float32Array; edges: MemoryEdge[] };

/** A projection of real annotation anchors and the revision's recorded edges. */
export default function MemoryMap({ revision }: { revision?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [circuit, setCircuit] = useState<Circuit>();
  const [phase, setPhase] = useState<"before" | "after">("after");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setCircuit(undefined);
    setError("");
    const binary = async () => {
      const response = await fetch("/api/brain/geometry", {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Neuron positions are unavailable.");
      return new Float32Array(await response.arrayBuffer());
    };
    const connections = async () => {
      if (!revision) return [];
      const response = await fetch(`/api/learning/connections/${revision}`, {
        signal: controller.signal,
      });
      if (!response.ok)
        throw new Error("Recorded connections are unavailable.");
      const result = (await response.json()) as { edges: MemoryEdge[] };
      return result.edges;
    };
    Promise.all([binary(), connections()])
      .then(([positions, edges]) => {
        if (!controller.signal.aborted) setCircuit({ positions, edges });
      })
      .catch((exception: Error) => {
        if (!controller.signal.aborted) setError(exception.message);
      });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || !circuit) return;
    const draw = () => {
      const context = element.getContext("2d");
      if (!context) return;
      const { width, height } = element.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      element.width = Math.round(width * ratio);
      element.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const { positions, edges } = circuit;
      let minX = Infinity,
        maxX = -Infinity,
        minY = Infinity,
        maxY = -Infinity;
      for (let i = 0; i < positions.length / 4; i++) {
        if (positions[i * 4 + 3] < 0) continue;
        minX = Math.min(minX, positions[i * 4]);
        maxX = Math.max(maxX, positions[i * 4]);
        minY = Math.min(minY, positions[i * 4 + 1]);
        maxY = Math.max(maxY, positions[i * 4 + 1]);
      }
      const scale = Math.min(
        width / ((maxX - minX) * 1.1),
        height / ((maxY - minY) * 1.15),
      );
      const centreX = (minX + maxX) / 2,
        centreY = (minY + maxY) / 2;
      const project = (index: number): [number, number] => [
        width / 2 + (positions[index * 4] - centreX) * scale,
        height / 2 - (positions[index * 4 + 1] - centreY) * scale,
      ];
      // Every valid anchor is shown; brightness here encodes anatomy, not spikes.
      const groups = [0, 1, 3, 5, 6, 2, 4];
      for (const group of groups) {
        context.fillStyle = token(
          group === 2 ? "leaf" : group === 4 ? "lime" : "night-muted",
        );
        context.globalAlpha =
          group === 2 ? 0.55 : group === 4 ? 0.95 : group === 1 ? 0.16 : 0.11;
        for (let i = 0; i < positions.length / 4; i++) {
          if (positions[i * 4 + 3] !== group) continue;
          const [x, y] = project(i);
          const size = group === 4 ? 2.1 : group === 2 ? 1.25 : 0.8;
          context.fillRect(x, y, size, size);
        }
      }
      const maxWeight = Math.max(
        0.001,
        ...edges.map((edge) => Math.abs(edge.before_mv)),
      );
      context.lineWidth = 0.7;
      for (const edge of edges) {
        const [x1, y1] = project(edge.pre);
        const [x2, y2] = project(edge.post);
        const weight = Math.abs(
          phase === "before" ? edge.before_mv : edge.after_mv,
        );
        context.globalAlpha = 0.08 + 0.65 * Math.min(1, weight / maxWeight);
        context.strokeStyle = token(
          phase === "before"
            ? "night-text"
            : Math.abs(edge.after_mv) < Math.abs(edge.before_mv)
              ? "sand"
              : "lime",
        );
        context.beginPath();
        context.moveTo(x1, y1);
        context.lineTo(x2, y2);
        context.stroke();
      }
      context.globalAlpha = 1;
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(element);
    return () => observer.disconnect();
  }, [circuit, phase]);

  return (
    <figure className="memory-map">
      <div className="memory-map-top">
        <span className="eyebrow">CIRCUIT MEMORY / v783</span>
        <div
          className="memory-phase"
          role="group"
          aria-label="Connection weights"
        >
          <button
            aria-pressed={phase === "before"}
            className={phase === "before" ? "active" : ""}
            onClick={() => setPhase("before")}
            disabled={!circuit?.edges.length}
          >
            Before
          </button>
          <button
            aria-pressed={phase === "after"}
            className={phase === "after" ? "active" : ""}
            onClick={() => setPhase("after")}
            disabled={!circuit?.edges.length}
          >
            After
          </button>
        </div>
      </div>
      <div className="memory-map-canvas">
        <canvas
          ref={canvas}
          role="img"
          aria-label={`Real FlyWire neuron positions. ${circuit?.edges.length || 0} recorded KC to MBON connections, ${phase} learning. Line opacity encodes connection weight.`}
        />
        {!circuit && (
          <p className="memory-map-message" role="status">
            {error || "Opening the connectome…"}
          </p>
        )}
      </div>
      <figcaption>
        <span>
          <i className="circuit-key" /> {circuit?.edges.length || 0} strongest
          recorded connections
        </span>
        <span>Real neuron positions · 2D projection</span>
        {phase === "before" && (
          <button
            onClick={() => setPhase("after")}
            aria-label="Return to learned connection weights"
          >
            <RotateCcw size={14} />
          </button>
        )}
      </figcaption>
    </figure>
  );
}
