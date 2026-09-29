import { useEffect, useRef, useState } from "react";
import FlyLive from "./FlyLive";
import "./preloader.css";

/**
 * Заставка, пока /api/state не ответил. Ночная сцена мозга: по кольцу из 22 входных
 * каналов бежит волна спайков, внутри мерцают клетки Кеньона, в центре зависла муха.
 * Цикл идёт только пока идёт загрузка (правило «циклы — только пока модель считает»).
 * Когда данные пришли, полоска дописывается до конца и сцена уходит вверх — приложение
 * под ней уже отрисовано. При prefers-reduced-motion — статичный кадр без задержки.
 */
const STEPS = [
  "Opening the file",
  "Waking the connectome",
  "Reading every photo",
  "Briefing the agent",
];
const CHANNELS = 22;
const KENYON = 64;
const MIN_MS = 1500;
const STEP_MS = 520;

const ring = Array.from({ length: CHANNELS }, (_, i) => {
  const a = (i / CHANNELS) * Math.PI * 2 - Math.PI / 2;
  return { x: 100 + Math.cos(a) * 86, y: 100 + Math.sin(a) * 86, i };
});
// Золотой угол: ровное «облако» без случайности, одинаковое при каждой загрузке.
const cloud = Array.from({ length: KENYON }, (_, i) => {
  const r = 42 + 30 * Math.sqrt((i + 0.5) / KENYON),
    a = i * 2.39996;
  return {
    x: 100 + Math.cos(a) * r,
    y: 100 + Math.sin(a) * r,
    delay: ((i * 37) % KENYON) / KENYON,
  };
});

export default function Preloader({
  ready,
  error,
  onRetry,
  onExit,
}: {
  ready: boolean;
  error?: string;
  onRetry: () => void;
  onExit: () => void;
}) {
  const [step, setStep] = useState(0),
    [phase, setPhase] = useState<"load" | "done" | "leave">("load");
  const [go, setGo] = useState(false);
  const start = useRef(performance.now());
  // Первый кадр полоски — пустой, затем долгий переход к 86 %: он честно «ждёт» ответа.
  useEffect(() => {
    const f = requestAnimationFrame(() =>
      requestAnimationFrame(() => setGo(true)),
    );
    return () => cancelAnimationFrame(f);
  }, []);
  const still = useRef(
    matchMedia("(prefers-reduced-motion: reduce)").matches,
  ).current;

  useEffect(() => {
    if (error || phase !== "load") return;
    const t = setInterval(
      () => setStep((s) => Math.min(s + 1, STEPS.length - 1)),
      STEP_MS,
    );
    return () => clearInterval(t);
  }, [error, phase]);

  useEffect(() => {
    if (!ready || phase !== "load") return;
    if (still) return onExit();
    const wait = Math.max(0, MIN_MS - (performance.now() - start.current));
    const t = setTimeout(() => {
      setStep(STEPS.length - 1);
      setPhase("done");
    }, wait);
    return () => clearTimeout(t);
  }, [ready, phase, still, onExit]);

  return (
    <div
      className={`preloader ${phase}${go ? " go" : ""}`}
      role="status"
      aria-live="polite"
      onTransitionEnd={(e) => {
        if (e.target !== e.currentTarget) {
          if (phase === "done" && e.propertyName === "transform")
            setPhase("leave");
          return;
        }
        if (phase === "leave" && e.propertyName === "opacity") onExit();
      }}
    >
      <div className="preloader-stage">
        <svg className="preloader-net" viewBox="0 0 200 200" aria-hidden="true">
          <circle className="preloader-orbit" cx="100" cy="100" r="86" />
          {cloud.map((p, i) => (
            <circle
              key={i}
              className="kc"
              cx={p.x}
              cy={p.y}
              r="1.2"
              style={{ animationDelay: `calc(var(--dur-sheen) * ${-p.delay})` }}
            />
          ))}
          {ring.map((p) => (
            <circle
              key={p.i}
              className="orn"
              cx={p.x}
              cy={p.y}
              r="2.6"
              style={{
                animationDelay: `calc(var(--dur-scan) * ${p.i / CHANNELS - 1})`,
              }}
            />
          ))}
        </svg>
        <FlyLive still size={64} className="preloader-fly" />
      </div>
      <div className="preloader-copy">
        <strong>Fly Estate</strong>
        {error ? (
          <>
            <p className="preloader-error">{error}</p>
            <button onClick={onRetry}>Try again</button>
          </>
        ) : (
          <>
            <p key={step} className="preloader-step">
              {STEPS[step]}
            </p>
            <span className="preloader-bar">
              <span />
            </span>
            <small>
              {String(step + 1).padStart(2, "0")} /{" "}
              {String(STEPS.length).padStart(2, "0")}
            </small>
          </>
        )}
      </div>
    </div>
  );
}
