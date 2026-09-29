# Fly Estate brand kit

Read this before any UI, copy, image or video work. Values live in [`src/tokens.css`](../src/tokens.css); the living version of this page is `/brand.html` (`pnpm dev`, then open `http://127.0.0.1:5176/brand.html`).

## Character

A fly, working as a professional residential agent. It is serious about the job: it inspects every photo, keeps a file on the client and writes short, correct notes. The humour comes only from the premise, never from the tone. We do not mock realtors, clients or the fly.

- **Is:** calm, precise, courteous, dry, quietly competent.
- **Is not:** a mascot, a meme, a tech demo, a disruptor, "smarter than your realtor".
- **The fly** appears as a small mark (the logo and the map marker). One exception, approved by the owner: the header mark (`src/FlyLive.tsx`) is alive at 30–36 px — now and then it grooms its front legs or gives a short buzz, then sits still for several seconds. Nowhere else: no large animated flies, no wing-beating elsewhere, no flying across the screen.

## Voice

| We write | We never write |
| --- | --- |
| Every listing. Personally inspected. | Smarter than your realtor! |
| Recommended for a viewing. | Buzz buzz, let's find a home 🪰 |
| Noted in your file. | Unlock the power of AI apartment search |
| Client brief · Portfolio · Side by side | Settings · Dashboard · Duel |
| Your agent is forming a view. | Model confidence: 0.63 |

Rules:

- Speak as an agency to its client: "your agent", "your file", "your brief". Short declaratives, full stops.
- Agency vocabulary for product nouns: brief (settings), file (ratings history), portfolio (listings), viewing (a positive verdict), for the record (comparisons).
- Science is stated plainly and precisely where it matters (BrainView, README): FlyWire release 783, MBON/CX outputs, neuron counts. Numbers are real, never rounded up for effect.
- No exclamation marks, no emoji, no puns on "fly" or "buzz".
- UI copy is English; product reports to the owner are Russian.

## Colour

One light system. Paper and forest carry the page; lime is the single accent.

| Role | Token | Use |
| --- | --- | --- |
| Page | `--paper` `#f6f7f2` | background |
| Surfaces | `--surface`, `--surface-2`, `--surface-3` | cards, inputs, hover |
| Lines | `--line`, `--line-strong` | dividers, borders |
| Text | `--ink`, `--ink-2`, `--muted`, `--subtle` | body → hints |
| Brand | `--forest` | primary buttons, the mark |
| Positive | `--moss`, `--leaf` | "recommended", map preference circle |
| Accent | `--lime` (+ `--lime-mid`, `--lime-soft`) | one highlight per screen: live state, selected, wings of the mark |
| Night stage | `--night`, `--night-2`, `--night-line`, `--night-text`, `--night-muted` | 3D brain, cover scrims |
| Warm | `--clay` (+ `--clay-muted`, `--clay-soft`, `--sand`) | "not recommended", warnings, price lines |

- Never write hex in component CSS. Use `var(--token)`; transparency via `color-mix(in srgb, var(--token) N%, transparent)`.
- In JS (Leaflet, canvas) read tokens with `token("moss")` from [`src/tokens.ts`](../src/tokens.ts). Canvas gets `rgba()`, not `color-mix`.
- **Data palette exception:** neuron group colours in `BrainView.tsx` stay as a separate categorical scale. They encode data, not brand, and must remain distinguishable on the night stage.
- Forbidden: purple-blue gradients, neon glow, glassmorphism, dark mode as a default.

## Type

- **Display:** Instrument Serif 400 (+ italic) — h1, h2, big numbers, prices on covers, the wordmark. Tracking −0.01em, line-height ≈ 1.
- **Text:** DM Sans Variable — everything else. Base 14 px, labels 10–11 px uppercase with `--track-label` (0.14em).
- **Mono:** `--font-mono` for code and token names only.
- Scale: `--fs-micro 10` · `xs 11` · `sm 12` · `base 14` · `md 16` · `lg 19` · `xl 24` · `2xl 30` · `3xl 40` · `display 60`. No sizes outside the scale.
- Italic serif marks the emphasised half of a headline ("Every listing. *Personally inspected.*"), in `--moss`.

## Form

- Radii `--r-xs … --r-pill`; cards use `--r-lg`, buttons `--r-md`.
- Borders before shadows. The only shadow is `--shadow-float` (popovers, the cover preview).
- Density: generous page margins, tight card interiors. Mobile gutter is 16 px, no horizontal scroll.

## Motion

The fly's own movement: a short, exact dart, then stillness.

- Durations: `--dur-instant 90ms` (press) · `--dur-quick 160ms` (hover, colour) · `--dur-move 240ms` (enter) · `--dur-settle 420ms` (large layout).
- Easing: `--ease-dart` for entering, `--ease-standard` for state, `--ease-exit` for leaving.
- Entering content: `dart-in` — opacity 0 → 1 and a 6 px (`--dart-distance`) rise. Lists stagger by 30 ms, capped at 210 ms.
- Press: `scale(.98)` for `--dur-instant`.
- Infinite animations: the live dot (`on-duty`, 2.4 s) and, only while a model job is actually running, the inspection pass over photo thumbnails (`--dur-scan`) and the progress sheen (`--dur-sheen`). They stop with the job. No looping decorations, parallax, or scroll-jacking.
- The header mark acts in episodes, not a loop: grooming (`--dur-groom 2600ms`) or a buzz (18 × `--dur-wingbeat 46ms`), started by the component after 3.5–8.5 s of stillness, or by hovering the brand link. Under reduced motion it stays still.
- `prefers-reduced-motion: reduce` zeroes every duration and distance in `tokens.css`; the live dot stops.
- All rules live in [`src/motion.css`](../src/motion.css).

## Effects

The agency's paperwork, animated: numbers settle, the verdict gets typed, the file slides across the desk. Code: [`src/effects.tsx`](../src/effects.tsx) + [`src/effects.css`](../src/effects.css).

- **One noticeable effect per screen.** Everything else is the standard `dart-in`.
- **Sliding indicator** under the active tab and the Pure/Cyborg switch (`useIndicator`, `--dur-move`, `--ease-dart`). The first placement is instant.
- **Count-up** for headline figures (`CountUp`, `--dur-count`, tabular numerals). The last frame is always the exact value.
- **Verdict decrypt**: when the verdict changes, letters settle left to right (`Decrypt`, `--dur-decrypt`). Screen readers get the final text only. Never on first render.
- **Card spotlight**: a soft `--lime-soft` light under the pointer on portfolio cards. Only for `(hover: hover) and (pointer: fine)`; photos are never tinted.
- **Letterhead header**: the header is sticky. At the top it is a letterhead with a rule inside the margins; after scrolling it condenses (68 → 54 px desktop, 60 → 52 px mobile), the caption folds away, the mark shrinks and the rule runs edge to edge. Paper at 88 % with a 4 px blur. A bottom margin makes up the lost height, so the page never jumps. Separate thresholds (24 px down, 4 px up) keep it from flickering.
- **Client brief chip** in the header: the search terms (target–ceiling, bedrooms, radius) stay in view and open the brief. On phones it is an icon only.
- **Paper grain**: a still noise layer at 3.5 % over the whole page. It never moves.
- Limits for anything added later: tilt ≤ 3°, magnetic pull ≤ 3 px, blur ≤ 4 px, no springs or overshoot.
- Not taken: WebGL backgrounds, glass and glow, custom cursors, idle shimmer, glitch text, scroll-jacking, playful bounces.
- Every duration comes from `tokens.css`; under reduced motion each effect shows its final state at once.

## Iconography

- Icons: `lucide-react`, 15–18 px, default stroke. Never emoji as icons.
- The mark: `public/fly.svg` / `src/Fly.tsx` — ink body, lime wings, static, 22–30 px in UI. The header uses the live variant `src/FlyLive.tsx` (same palette, clay eyes, 36 px desktop / 30 px mobile).

## Media (images, video, covers)

1. **Real photos first.** Listing photos, then stock (Unsplash, Pexels) for anything else. Generate only when neither exists.
2. **No text inside generated or edited images.** Every word, number and the mark is drawn on top as HTML/SVG/canvas — see the cover composer on `/brand.html`.
3. **Leave an empty zone** for text: calm, low-detail area at the bottom (or left) third. Prompts must say so explicitly.
4. Generated image style: natural daylight, Mediterranean interiors and streets, muted greens and warm stone, eye-level, no people looking at the camera, no fisheye, no HDR glow.
5. Produce 1–2 variants, review, then iterate. No blind batches.
6. Covers come from the composer (formats 1080², 1080×1350, 1200×630). Text zone 24–60 %, night scrim 40–100 %.

## References

| Reference | What we take |
| --- | --- |
| [堆友 / d.design](https://d.design) (Alibaba design community) | editorial calm, serif headlines against plain sans, generous whitespace |
| [Amicro](https://amicro.vercel.app) (MIT) | the small precise mark, restrained micro-interactions |
| [React Bits](https://reactbits.dev) (MIT + Commons Clause) | effect ideas — spotlight card, count-up, decrypted text — rewritten in short dart form, not copied |
| [21st.dev](https://21st.dev) | component anatomy: controls, sliders, segmented choices |
| Pinterest (boards: Mediterranean interiors, estate agency print) | photo mood and print-like layouts for covers |

## Anti-references

- Generic SaaS landing: gradient hero + three icon cards + CTA.
- Crypto/AI neon, dark glass, glowing particles.
- Cartoon insect mascots, bee/fly puns, stickers.
- Real-estate portals crammed with badges, red "HOT" labels and banners.

## Before shipping (checklist)

- [ ] Every colour and size comes from `tokens.css`; no stray hex in CSS.
- [ ] One accent per screen; hierarchy readable in three seconds.
- [ ] Copy passes the voice table: agency, deadpan, no emoji, no mockery.
- [ ] Motion uses the tokens and respects reduced motion.
- [ ] No text baked into images; empty zone respected.
- [ ] Checked at 390 px and desktop with a headless screenshot, actually looked at.
