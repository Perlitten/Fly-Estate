import FlyLive from "./FlyLive";

/** Фирменный знак: та же муха, что в шапке, но статичная (цвета — .fly-mark в style.css). */
export default function Fly({
  className = "",
  size = 24,
}: {
  className?: string;
  size?: number;
}) {
  return <FlyLive still size={size} className={className} />;
}
