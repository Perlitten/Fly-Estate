import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Download, RotateCcw } from "lucide-react";
import type { Data, Listing } from "../types";
import { api, money } from "../api";
import { token } from "../tokens";
import Fly from "../Fly";

const colors = [
  ["paper", "Page background"],
  ["surface", "Cards, dialogs"],
  ["surface-2", "Tinted panels, active tab"],
  ["line", "Dividers"],
  ["ink", "Text"],
  ["muted", "Secondary text"],
  ["forest", "Primary action"],
  ["moss", "Accent text on light"],
  ["lime", "The one bright accent"],
  ["night", "Brain stage"],
  ["night-text", "Text on the stage"],
  ["clay", "Over budget, not recommended"],
] as const;
const sizes = [
  "display",
  "3xl",
  "2xl",
  "xl",
  "lg",
  "md",
  "base",
  "sm",
  "xs",
  "micro",
];
const formats = {
  square: [1080, 1080, "Post · 1080 × 1080"],
  portrait: [1080, 1350, "Portrait · 1080 × 1350"],
  og: [1200, 630, "Link preview · 1200 × 630"],
} as const;
type Format = keyof typeof formats;

/** #rrggbb из токена → rgba(): canvas не везде понимает color-mix. */
function alpha(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

function wrap(ctx: CanvasRenderingContext2D, text: string, width: number) {
  const lines: string[] = [];
  for (const paragraph of text.split("\n")) {
    let line = "";
    for (const word of paragraph.split(" ")) {
      const next = line ? line + " " + word : word;
      if (line && ctx.measureText(next).width > width) {
        lines.push(line);
        line = word;
      } else line = next;
    }
    lines.push(line);
  }
  return lines;
}

/** Обложка: фото без текста + векторные подписи в отдельной тёмной зоне. */
function Composer({ listings }: { listings: Listing[] }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [id, setId] = useState(""),
    [photo, setPhoto] = useState(0),
    [format, setFormat] = useState<Format>("portrait"),
    [zone, setZone] = useState(38),
    [scrim, setScrim] = useState(88),
    [headline, setHeadline] = useState("Every listing.\nPersonally inspected."),
    [showPrice, setShowPrice] = useState(true),
    [ready, setReady] = useState(0);
  const listing = listings.find((l) => l.id === id) || listings[0];
  const src = listing?.photos[Math.min(photo, listing.photos.length - 1)];
  const image = useMemo(() => {
    const img = new Image();
    img.onload = () => setReady((v) => v + 1);
    if (src) img.src = src;
    return img;
  }, [src]);
  const mark = useMemo(() => {
    const img = new Image();
    img.onload = () => setReady((v) => v + 1);
    img.src = "/fly.svg";
    return img;
  }, []);
  useEffect(() => {
    document.fonts.ready.then(() => setReady((v) => v + 1));
  }, []);
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const [W, H] = formats[format];
    c.width = W;
    c.height = H;
    const ctx = c.getContext("2d")!;
    const pad = Math.round(W * 0.065);
    const zoneH = Math.round((H * zone) / 100);
    ctx.fillStyle = token("night");
    ctx.fillRect(0, 0, W, H);
    if (image.complete && image.naturalWidth) {
      const s = Math.max(
        W / image.naturalWidth,
        (H - zoneH * 0.35) / image.naturalHeight,
      );
      const w = image.naturalWidth * s,
        h = image.naturalHeight * s;
      ctx.drawImage(image, (W - w) / 2, 0, w, h);
    }
    const g = ctx.createLinearGradient(0, H - zoneH * 1.35, 0, H - zoneH);
    const night = token("night");
    g.addColorStop(0, alpha(night, 0));
    g.addColorStop(1, alpha(night, scrim / 100));
    ctx.fillStyle = g;
    ctx.fillRect(0, H - zoneH * 1.35, W, zoneH * 0.35);
    ctx.fillStyle = alpha(night, scrim / 100);
    ctx.fillRect(0, H - zoneH, W, zoneH);

    const eyebrow = Math.round(W * 0.017);
    ctx.fillStyle = token("lime");
    ctx.font = `500 ${eyebrow}px "DM Sans Variable"`;
    ctx.letterSpacing = `${eyebrow * 0.14}px`;
    ctx.fillText("YOUR AGENT · ON DUTY", pad, H - zoneH + pad);
    ctx.letterSpacing = "0px";

    let size = Math.round(W * (format === "og" ? 0.06 : 0.082));
    ctx.font = `400 ${size}px "Instrument Serif"`;
    let lines = wrap(ctx, headline, W - pad * 2);
    const room = zoneH - pad * 2.6 - eyebrow * 2;
    while (lines.length * size * 1.02 > room && size > 24) {
      size -= 2;
      ctx.font = `400 ${size}px "Instrument Serif"`;
      lines = wrap(ctx, headline, W - pad * 2);
    }
    ctx.fillStyle = token("night-text");
    lines.forEach((line, i) =>
      ctx.fillText(
        line,
        pad,
        H - zoneH + pad + eyebrow * 1.6 + size * (i + 0.9),
      ),
    );

    const base = H - pad * 0.75;
    const ms = Math.round(W * 0.03);
    if (mark.complete) ctx.drawImage(mark, pad, base - ms * 0.8, ms, ms);
    ctx.font = `400 ${Math.round(W * 0.026)}px "Instrument Serif"`;
    ctx.fillStyle = token("night-text");
    ctx.fillText("Fly Estate", pad + ms * 1.3, base);
    if (showPrice && listing) {
      ctx.font = `500 ${Math.round(W * 0.018)}px "DM Sans Variable"`;
      ctx.fillStyle = token("night-muted");
      ctx.textAlign = "right";
      ctx.fillText(
        `${money(listing.price)} / month · ${listing.area}`,
        W - pad,
        base,
      );
      ctx.textAlign = "left";
    }
  }, [format, zone, scrim, headline, showPrice, image, mark, listing, ready]);

  const save = () => {
    canvas.current?.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `fly-estate-${format}-${listing?.id || "cover"}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
  };
  if (!listings.length)
    return (
      <p className="brand-note">
        No inspected listings with photos on file yet. Import listings to
        compose covers from real photos.
      </p>
    );
  return (
    <div className="composer">
      <div className="composer-controls">
        <label>
          Listing
          <select
            value={listing?.id}
            onChange={(e) => {
              setId(e.target.value);
              setPhoto(0);
            }}
          >
            {listings.map((l) => (
              <option key={l.id} value={l.id}>
                {money(l.price)} · {l.area} · {l.bedrooms} bed
              </option>
            ))}
          </select>
        </label>
        <label>
          Photo {photo + 1} / {listing?.photos.length}
          <input
            type="range"
            min={0}
            max={Math.max(0, (listing?.photos.length || 1) - 1)}
            value={photo}
            onChange={(e) => setPhoto(+e.target.value)}
          />
        </label>
        <label>
          Format
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as Format)}
          >
            {Object.entries(formats).map(([k, v]) => (
              <option key={k} value={k}>
                {v[2]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Text zone · {zone}%
          <input
            type="range"
            min={24}
            max={60}
            value={zone}
            onChange={(e) => setZone(+e.target.value)}
          />
        </label>
        <label>
          Scrim · {scrim}%
          <input
            type="range"
            min={40}
            max={100}
            value={scrim}
            onChange={(e) => setScrim(+e.target.value)}
          />
        </label>
        <label>
          Headline
          <textarea
            rows={3}
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
          />
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={showPrice}
            onChange={(e) => setShowPrice(e.target.checked)}
          />
          Price and area
        </label>
        <button className="brand-primary" onClick={save}>
          <Download size={16} />
          Save PNG
        </button>
        <small>
          The photo stays untouched; every word is drawn on top at export size.
        </small>
      </div>
      <canvas ref={canvas} className={`composer-canvas ${format}`} />
    </div>
  );
}

export default function Brand() {
  const [data, setData] = useState<Data>();
  const [failed, setFailed] = useState(false);
  const [duration, setDuration] = useState(240);
  const [replay, setReplay] = useState(0);
  useEffect(() => {
    api<Data>("/api/state")
      .then(setData)
      .catch(() => setFailed(true));
  }, []);
  const listings = useMemo(
    () =>
      data?.listings.filter(
        (l) => l.photos.length && !l.filter_reasons.length,
      ) || [],
    [data],
  );
  return (
    <main className="brand-page">
      <header>
        <a href="/" className="brand-back">
          <ArrowLeft size={15} /> Back to the agency
        </a>
        <span className="brand-wordmark">
          <Fly size={26} /> Fly Estate
        </span>
        <h1>
          Brand kit.
          <br />
          <em>Please read before generating.</em>
        </h1>
        <p>
          The rules live in <code>docs/BRAND_KIT.md</code>; values live in{" "}
          <code>src/tokens.css</code>. This page renders both.
        </p>
      </header>

      <section>
        <span className="brand-eyebrow">01 · CHARACTER</span>
        <h2>A fly, working as a professional agent.</h2>
        <div className="voice">
          <div>
            <b>We write</b>
            <p>“Every listing. Personally inspected.”</p>
            <p>“Recommended for a viewing.”</p>
            <p>“Noted in your file.”</p>
          </div>
          <div>
            <b>We never write</b>
            <p className="strike">“Smarter than your realtor!”</p>
            <p className="strike">“Buzz buzz, let’s find a home 🐝”</p>
            <p className="strike">“Unlock the power of AI apartment search”</p>
          </div>
        </div>
      </section>

      <section>
        <span className="brand-eyebrow">02 · COLOUR</span>
        <h2>Paper, forest, one lime.</h2>
        <div className="swatches">
          {colors.map(([name, role]) => (
            <div key={name}>
              <i style={{ background: `var(--${name})` }} />
              <b>--{name}</b>
              <small>{role}</small>
              <code>{token(name)}</code>
            </div>
          ))}
        </div>
      </section>

      <section>
        <span className="brand-eyebrow">03 · TYPE</span>
        <h2>Serif for the letterhead, sans for the paperwork.</h2>
        <div className="type-scale">
          {sizes.map((s) => (
            <div key={s}>
              <small>
                --fs-{s} · {token(`fs-${s}`)}
              </small>
              <span
                className={["display", "3xl", "2xl"].includes(s) ? "serif" : ""}
                style={{ fontSize: `var(--fs-${s})` }}
              >
                {s === "micro"
                  ? "CLIENT FILE · ACTIVE"
                  : "Recommended for a viewing"}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <span className="brand-eyebrow">04 · MOTION</span>
        <h2>A short dart, then stillness.</h2>
        <div className="motion-demo">
          <label>
            Dart duration · {duration} ms
            <input
              type="range"
              min={120}
              max={480}
              step={20}
              value={duration}
              onChange={(e) => setDuration(+e.target.value)}
            />
          </label>
          <button onClick={() => setReplay((v) => v + 1)}>
            <RotateCcw size={15} /> Replay
          </button>
          <div
            className="motion-cards"
            key={replay}
            style={{ ["--dur-move" as string]: `${duration}ms` }}
          >
            {["Portfolio", "Side by side", "Client file"].map((x, i) => (
              <div key={x} style={{ animationDelay: `${i * 30}ms` }}>
                {x}
              </div>
            ))}
          </div>
          <small>
            Tokens: --dur-quick 160 ms for hovers, --dur-move 240 ms for
            entrances, ease-dart. No springs, no bounces, no idle loops except
            the “on duty” dot.
          </small>
        </div>
      </section>

      <section>
        <span className="brand-eyebrow">05 · COVERS</span>
        <h2>Real photos, words on top.</h2>
        {data ? (
          <Composer listings={listings} />
        ) : (
          <p className="brand-note">
            {failed ? (
              <>
                Start the API (<code>pnpm dev</code>) and import listings to
                compose covers from real photos.
              </>
            ) : (
              "Your agent is fetching the file…"
            )}
          </p>
        )}
      </section>
    </main>
  );
}
