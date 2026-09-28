export default function Fly({
  className = "",
  size = 64,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <svg
      className={`fly ${className}`}
      width={size}
      height={size}
      viewBox="0 0 80 80"
      role="img"
      aria-label="Fly"
    >
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      >
        <path d="M29 40L15 32M29 46L13 47M30 51L20 64M51 40L65 32M51 46L67 47M50 51L60 64" />
        <ellipse
          className="wing left"
          cx="26"
          cy="29"
          rx="12"
          ry="20"
          transform="rotate(-28 26 29)"
          fill="#d6eca1"
        />
        <ellipse
          className="wing right"
          cx="54"
          cy="29"
          rx="12"
          ry="20"
          transform="rotate(28 54 29)"
          fill="#d6eca1"
        />
        <ellipse cx="40" cy="48" rx="10" ry="19" fill="currentColor" />
        <path d="M34 50h12M34 56h12" stroke="#d6eca1" />
        <circle cx="40" cy="28" r="11" fill="currentColor" />
        <circle cx="34" cy="25" r="4" fill="#d6eca1" />
        <circle cx="46" cy="25" r="4" fill="#d6eca1" />
      </g>
    </svg>
  );
}
