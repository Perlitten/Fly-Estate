import { useEffect, useRef, useState } from "react";
import "./fly.css";

type Act = "" | "rub" | "buzz";

/**
 * Фирменный знак — одна муха на весь продукт (стили в fly.css). В шапке она живая:
 * сидит неподвижно, время от времени потирает передние лапки или коротко жужжит;
 * наведение на ссылку бренда — тоже жужжание. При prefers-reduced-motion не двигается.
 * С `still` — статичная метка (Fly.tsx) для вердикта, плашки обучения и брендбука.
 */
export default function FlyLive({
  size = 34,
  still = false,
  className = "",
}: {
  size?: number;
  still?: boolean;
  className?: string;
}) {
  const [act, setAct] = useState<Act>("");
  const ref = useRef<SVGSVGElement>(null);
  const first = useRef(true);

  useEffect(() => {
    if (still) return;
    const host = ref.current?.closest("a, button");
    const buzz = () => setAct((a) => a || "buzz");
    host?.addEventListener("pointerenter", buzz);
    return () => host?.removeEventListener("pointerenter", buzz);
  }, [still]);

  useEffect(() => {
    if (still || act || matchMedia("(prefers-reduced-motion: reduce)").matches)
      return;
    const wait = first.current ? 1200 : 3500 + Math.random() * 5000;
    first.current = false;
    const t = setTimeout(
      () => setAct(Math.random() < 0.6 ? "rub" : "buzz"),
      wait,
    );
    return () => clearTimeout(t);
  }, [act, still]);

  const leg = (side: "l" | "r", pair: string, d: string) => (
    <path className={`leg leg-${pair}-${side}`} d={d} />
  );
  const front = (side: "l" | "r") => {
    const m = side === "l" ? 1 : -1,
      x = (v: number) => 40 - m * (40 - v);
    return (
      <g className={`femur femur-${side}`}>
        <path d={`M${x(36)} 31 L${x(28)} 25`} />
        <g className={`tibia tibia-${side}`}>
          <path d={`M${x(28)} 25 L${x(27)} 17 L${x(29)} 13`} />
        </g>
      </g>
    );
  };

  return (
    <svg
      ref={ref}
      className={`fly-mark fly-live ${act} ${className}`}
      width={size}
      height={size}
      viewBox="0 0 80 80"
      aria-hidden="true"
      onAnimationEnd={(e) => {
        if (e.animationName === "fly-rub-l" || e.animationName === "fly-lift")
          setAct("");
      }}
    >
      <g className="fly-body">
        <g className="legs">
          {leg("l", "mid", "M34 36 L23 35 L15 42")}
          {leg("r", "mid", "M46 36 L57 35 L65 42")}
          {leg("l", "hind", "M35 41 L26 49 L22 61")}
          {leg("r", "hind", "M45 41 L54 49 L58 61")}
          {front("l")}
          {front("r")}
        </g>
        <ellipse className="abdomen" cx="40" cy="52" rx="7.5" ry="11.5" />
        <path className="stripe" d="M33.5 49 Q40 51.5 46.5 49" />
        <path className="stripe" d="M33.8 55 Q40 57.5 46.2 55" />
        <g className="wing wing-l">
          <path d="M37.5 34 C29 36 21 49 22.5 59 C24 66 31 64.5 34 56 C36.5 48 38.5 40 37.5 34 Z" />
          <path className="vein" d="M36.5 37 Q29.5 48 25.5 59" />
        </g>
        <g className="wing wing-r">
          <path d="M42.5 34 C51 36 59 49 57.5 59 C56 66 49 64.5 46 56 C43.5 48 41.5 40 42.5 34 Z" />
          <path className="vein" d="M43.5 37 Q50.5 48 54.5 59" />
        </g>
        <ellipse className="thorax" cx="40" cy="35" rx="8.5" ry="8" />
        <g className="head">
          <ellipse cx="40" cy="22.5" rx="8" ry="6.5" />
          <ellipse className="eye" cx="35" cy="21.5" rx="3.6" ry="4.6" />
          <ellipse className="eye" cx="45" cy="21.5" rx="3.6" ry="4.6" />
        </g>
      </g>
    </svg>
  );
}
