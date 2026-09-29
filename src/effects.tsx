import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

/**
 * Эффекты интерфейса (стили — effects.css). Длительности читаются из tokens.css, поэтому
 * при prefers-reduced-motion они нулевые и всё сразу показывает итоговое состояние.
 */

const token = (name: string) =>
  parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue(name),
  ) || 0;
const dart = (t: number) => 1 - Math.pow(1 - t, 3);

/** Подложка под активной кнопкой группы: переезжает к новой, а не перекрашивает кнопки. */
export function useIndicator(
  ref: RefObject<HTMLElement | null>,
  active: unknown,
) {
  useLayoutEffect(() => {
    const host = ref.current;
    if (!host) return;
    const place = () => {
      const button = host.querySelector<HTMLElement>(":scope > .active");
      if (!button) return host.removeAttribute("data-indicator");
      host.style.setProperty("--ix", button.offsetLeft + "px");
      host.style.setProperty("--iy", button.offsetTop + "px");
      host.style.setProperty("--iw", button.offsetWidth + "px");
      host.style.setProperty("--ih", button.offsetHeight + "px");
      // Первое измерение без анимации, дальше — переезд.
      requestAnimationFrame(() => host.setAttribute("data-indicator", "on"));
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(host);
    return () => observer.disconnect();
  }, [ref, active]);
}

/** Число досчитывает до точного значения за --dur-count; итоговый кадр всегда точный. */
export function CountUp({
  value,
  format,
}: {
  value: number;
  format: (value: number) => string;
}) {
  const [shown, setShown] = useState(value);
  const from = useRef(0);
  useEffect(() => {
    const duration = token("--dur-count"),
      start = from.current;
    from.current = value;
    if (!duration || start === value) return setShown(value);
    let frame = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - t0) / duration);
      setShown(t < 1 ? start + (value - start) * dart(t) : value);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <span className="count-up">{format(shown)}</span>;
}

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

/** Вердикт проявляется из букв слева направо при смене текста; первый показ — без эффекта. */
export function Decrypt({ text }: { text: string }) {
  const [shown, setShown] = useState(text);
  const first = useRef(true);
  useEffect(() => {
    const duration = token("--dur-decrypt");
    if (first.current || !duration) {
      first.current = false;
      return setShown(text);
    }
    let frame = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - t0) / duration),
        fixed = Math.floor(text.length * dart(t));
      setShown(
        t < 1
          ? text.slice(0, fixed) +
              text
                .slice(fixed)
                .replace(
                  /\S/g,
                  () => GLYPHS[(Math.random() * GLYPHS.length) | 0],
                )
          : text,
      );
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text]);
  return (
    <span className="decrypt">
      <span className="visually-hidden">{text}</span>
      <span aria-hidden="true">{shown}</span>
    </span>
  );
}

/** Подсветка под курсором для карточек (только мышь; на тач-экранах ничего). */
export function useSpotlight(selector: string) {
  useEffect(() => {
    if (!matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    const move = (e: PointerEvent) => {
      const card = (e.target as Element | null)?.closest<HTMLElement>(selector);
      if (!card) return;
      const box = card.getBoundingClientRect();
      card.style.setProperty("--mx", e.clientX - box.left + "px");
      card.style.setProperty("--my", e.clientY - box.top + "px");
    };
    document.addEventListener("pointermove", move, { passive: true });
    return () => document.removeEventListener("pointermove", move);
  }, [selector]);
}
