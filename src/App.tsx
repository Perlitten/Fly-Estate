import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Brain,
  Map,
  Heart,
  GitCompareArrows,
  Plus,
  SlidersHorizontal,
  ArrowUpRight,
  ArrowRight,
  Check,
  Sparkles,
  ChevronRight,
  LoaderCircle,
} from "lucide-react";
import type { Data, Settings } from "./types";
import { api, count, money } from "./api";
import Fly from "./Fly";
import FlyLive from "./FlyLive";
import { CountUp, useIndicator, useSpotlight } from "./effects";
const BrainView = lazy(() => import("./BrainView"));
import CityMap from "./CityMap";
import Preloader from "./Preloader";
import ApartmentCard from "./ApartmentCard";
import { ImportDialog, SettingsDialog } from "./Dialogs";
import MarketPanel, { useAgentSearch } from "./Market";

const views = [
  ["brain", "Agent's brain", Brain],
  ["map", "Area map", Map],
  ["learn", "Portfolio", Heart],
  ["duel", "Side by side", GitCompareArrows],
] as const;
export default function App() {
  const [data, setData] = useState<Data>(),
    [view, setView] = useState("brain"),
    [selectedId, setSelected] = useState(""),
    [dialog, setDialog] = useState(""),
    [busy, setBusy] = useState(false),
    [slow, setSlow] = useState(false),
    [error, setError] = useState(""),
    [showExcluded, setShowExcluded] = useState(false),
    [sort, setSort] = useState("fly"),
    [pair, setPair] = useState<[string, string]>(["", ""]),
    [toast, setToast] = useState(""),
    [scrolled, setScrolled] = useState(false),
    [booting, setBooting] = useState(true);
  const endBoot = useCallback(() => setBooting(false), []);
  const load = useCallback(async () => {
    const result = await api<Data>("/api/state");
    setData(result);
    setSelected((id) =>
      result.listings.some((x) => x.id === id && !x.filter_reasons.length)
        ? id
        : result.listings.find((x) => !x.filter_reasons.length && x.vision)
            ?.id || "",
    );
  }, []);
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);
  // The agent's Bazaraki search: market snapshot (read when the map opens) and import progress.
  const agent = useAgentSearch(view === "map", load);
  // A save that takes longer than a moment says why the buttons are waiting.
  useEffect(() => {
    if (!busy) return setSlow(false);
    const t = setTimeout(() => setSlow(true), 1500);
    return () => clearTimeout(t);
  }, [busy]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(t);
  }, [toast]);
  // Шапка ужимается после прокрутки; разные пороги, чтобы не мигала на границе.
  useEffect(() => {
    const check = () =>
      setScrolled((was) => (was ? scrollY > 4 : scrollY > 24));
    check();
    addEventListener("scroll", check, { passive: true });
    return () => removeEventListener("scroll", check);
  }, []);
  const mutate = async (
    url: string,
    method: string,
    body: unknown,
    message = "",
  ) => {
    setBusy(true);
    setError("");
    try {
      await api(url, method, body);
      await load();
      if (message) setToast(message);
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setBusy(false);
    }
  };
  const rate = (id: string, value: number | null) => {
    mutate(
      "/api/rating",
      "POST",
      { id, value },
      value === null ? "Removed from your file" : "Noted in your file",
    ).catch(() => {});
  };
  const save = async (s: Settings) => {
    await mutate("/api/settings", "PUT", s, "Brief updated");
  };
  const eligible = useMemo(
    () =>
      data?.listings.filter((l) => !l.filter_reasons.length && l.vision) || [],
    [data],
  );
  const pairs = useMemo(() => {
    const result: [string, string][] = [];
    for (let i = 0; i < eligible.length; i++)
      for (let j = i + 1; j < eligible.length; j++)
        result.push([eligible[i].id, eligible[j].id]);
    return result;
  }, [eligible]);
  const nextPair = useCallback(() => {
    const compared = new Set(
      data?.comparisons.map((x) => [x.a, x.b].sort().join("|")),
    );
    const next =
      pairs.find((x) => !compared.has([...x].sort().join("|"))) ||
      pairs.find((x) => x.join("|") !== pair.join("|")) ||
      pairs[0];
    setPair(next || ["", ""]);
  }, [data, pairs, pair]);
  useEffect(() => {
    if (
      eligible.length >= 2 &&
      (!eligible.some((x) => x.id === pair[0]) ||
        !eligible.some((x) => x.id === pair[1]))
    )
      setPair(pairs[0]);
  }, [eligible, pair, pairs]);
  const compare = async (choice: number) => {
    try {
      await mutate(
        "/api/compare",
        "POST",
        { a: pair[0], b: pair[1], choice },
        "Noted for the record",
      );
      const key = [...pair].sort().join("|");
      const compared = new Set([
        ...(data?.comparisons.map((x) => [x.a, x.b].sort().join("|")) || []),
        key,
      ]);
      setPair(
        pairs.find((x) => !compared.has([...x].sort().join("|"))) ||
          pairs.find((x) => x.join("|") !== pair.join("|")) ||
          pair,
      );
    } catch {
      /* Error displayed above */
    }
  };
  const sorted = useMemo(() => {
    let items =
      data?.listings.filter((l) => showExcluded || !l.filter_reasons.length) ||
      [];
    return [...items].sort((a, b) =>
      sort === "price"
        ? a.price - b.price
        : sort === "distance"
          ? (a.prediction.distance ?? 999) - (b.prediction.distance ?? 999)
          : b.prediction.probability - a.prediction.probability,
    );
  }, [data, showExcluded, sort]);
  const tabsRef = useRef<HTMLElement>(null),
    modeRef = useRef<HTMLDivElement>(null);
  useIndicator(tabsRef, `${view}|${!!data}|${data?.listings.length}`);
  useIndicator(modeRef, `${data?.settings.mode}|${!!data}`);
  useSpotlight(".apartment-card");
  const preloader = booting && (
    <Preloader
      ready={!!data}
      error={data ? "" : error}
      onRetry={() => {
        setError("");
        load().catch((e) => setError(e.message));
      }}
      onExit={endBoot}
    />
  );
  // Заставка стоит первым ребёнком фрагмента в обеих ветках — React сохраняет её состояние.
  if (!data) return <>{preloader}</>;
  const selected = data.listings.find((l) => l.id === selectedId),
    done = data.training.ratings + data.training.comparisons;
  const a = eligible.find((l) => l.id === pair[0]),
    b = eligible.find((l) => l.id === pair[1]);
  const brief = data.settings,
    briefTerms = [
      `${money(brief.budget)}–${count(brief.ceiling)}`,
      `${brief.min_bedrooms}+ bd`,
      `${+brief.radius.toFixed(1)} km`,
    ];
  const selectedForBrain =
    selected && !selected.filter_reasons.length ? selected : eligible[0];
  return (
    <>
      {preloader}
      <div className="app">
        <header className={"app-header" + (scrolled ? " scrolled" : "")}>
          <a
            className="brand"
            href="/"
            onClick={(e) => {
              e.preventDefault();
              setView("brain");
            }}
          >
            <FlyLive />
            <span>
              Fly Estate
              <small>RESIDENTIAL AGENT · CYPRUS</small>
            </span>
          </a>
          <div className="header-right">
            <a
              className="github-link"
              href="https://github.com/Perlitten/Fly-Estate"
              target="_blank"
              rel="noreferrer"
            >
              Project
              <ArrowUpRight size={15} />
            </a>
            <button
              className="brief-chip"
              title="Client brief"
              aria-label={`Client brief: ${briefTerms.join(", ")}`}
              onClick={() => setDialog("settings")}
            >
              <SlidersHorizontal size={16} />
              <span className="brief-label">Brief</span>
              <span className="brief-terms">
                {briefTerms.map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </span>
            </button>
            <button className="primary" onClick={() => setDialog("import")}>
              <Plus size={17} />
              Add listing
            </button>
          </div>
        </header>
        <main>
          <section className="intro">
            <h1 className="visually-hidden">Fly Estate</h1>
            <div className="intro-ledger">
              <p>
                Your agent searches Bazaraki and studies every photo. A few
                ratings brief it.
              </p>
              <div>
                <strong>
                  <CountUp
                    value={data.brain.neurons}
                    format={(v) => count(Math.round(v))}
                  />
                </strong>
                <span>neurons</span>
              </div>
              <div>
                <strong>
                  <CountUp
                    value={data.brain.connections / 1e6}
                    format={(v) => v.toFixed(2)}
                  />
                  <small>M</small>
                </strong>
                <span>connections</span>
              </div>
              <div>
                <strong>
                  <CountUp
                    value={data.listings.length}
                    format={(v) => String(Math.round(v))}
                  />
                </strong>
                <span>listings</span>
              </div>
              <span className="data-tag">
                FLYWIRE RELEASE 783 <ArrowUpRight size={12} />
              </span>
            </div>
          </section>
          <section className="control-strip">
            <nav aria-label="Project sections" ref={tabsRef}>
              {views.map(([id, label, Icon]) => (
                <button
                  key={id}
                  className={view === id ? "active" : ""}
                  onClick={() => setView(id)}
                >
                  <Icon size={17} />
                  {label}
                  {id === "learn" && <span>{data.listings.length}</span>}
                </button>
              ))}
            </nav>
            <div className="mode-switch" aria-label="Vision mode" ref={modeRef}>
              <button
                disabled={busy}
                className={data.settings.mode === "pure" ? "active" : ""}
                title="Photos as a grid of light and color; an artificial mapping to brain inputs"
                onClick={() =>
                  save({ ...data.settings, mode: "pure" }).catch(() => {})
                }
              >
                Pure Fly
              </button>
              <button
                disabled={busy}
                className={data.settings.mode === "cyborg" ? "active" : ""}
                title="CLIP turns photos into visual signals for the brain"
                onClick={() =>
                  save({ ...data.settings, mode: "cyborg" }).catch(() => {})
                }
              >
                <Sparkles size={13} />
                Cyborg Fly
              </button>
            </div>
          </section>
          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button onClick={() => setError("")}>×</button>
            </div>
          )}
          {view === "brain" && (
            <Suspense
              fallback={
                <div className="empty-state">Opening the 3D brain…</div>
              }
            >
              <BrainView
                data={data}
                selected={selectedForBrain}
                onSelect={setSelected}
                onRate={rate}
                busy={busy}
              />
            </Suspense>
          )}
          {view === "map" && (
            <div className="map-layout">
              <CityMap
                items={sorted}
                selected={selected}
                settings={data.settings}
                agent={agent}
                onSelect={setSelected}
                onIdeal={(p) =>
                  save({ ...data.settings, ideal: p }).catch(() => {})
                }
              />
              <aside className="map-sidebar">
                <div className="side-heading">
                  <span className="eyebrow">AREA SURVEY</span>
                  <h3>
                    {data.training.ready
                      ? "Where your agent is looking"
                      : "Your agent is surveying Cyprus"}
                  </h3>
                  <p>
                    The shaded circle is your preferred area. Drag the pin to
                    move it.
                  </p>
                </div>
                <MarketPanel agent={agent} settings={data.settings} />
                {selected ? (
                  <ApartmentCard listing={selected} onRate={rate} busy={busy} />
                ) : (
                  <div className="empty-stimulus">
                    <p>
                      {data.listings.length
                        ? "Select a listing on the map."
                        : "No listings on file yet. Search Bazaraki and your agent adds them here as it reads."}
                    </p>
                  </div>
                )}
                <div
                  className="map-selection-list"
                  hidden={!eligible.length}
                >
                  {eligible.slice(0, 8).map((l) => (
                    <button
                      className={l.id === selected?.id ? "selected" : ""}
                      key={l.id}
                      onClick={() => setSelected(l.id)}
                    >
                      <span>
                        {l.area}
                        <small>
                          {l.bedrooms} bed · ≈ {l.prediction.distance ?? "—"} km
                        </small>
                      </span>
                      <b>{money(l.price)}</b>
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </div>
              </aside>
            </div>
          )}
          {view === "learn" && (
            <section className="listings-section">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">PORTFOLIO</span>
                  <h2>
                    {data.training.ready
                      ? "Your shortlist"
                      : "Brief your agent"}
                  </h2>
                  <p>
                    “Would visit”, “Maybe”, “Not for me” — every rating goes on
                    file.
                  </p>
                </div>
                <div className="list-controls">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={showExcluded}
                      onChange={(e) => setShowExcluded(e.target.checked)}
                    />
                    Show excluded
                  </label>
                  <select
                    aria-label="Sort apartments"
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                  >
                    <option value="fly">Agent's interest</option>
                    <option value="price">Price</option>
                    <option value="distance">Distance</option>
                  </select>
                </div>
              </div>
              <div className="listing-grid">
                {sorted.map((l) => (
                  <ApartmentCard
                    key={l.id}
                    listing={l}
                    onSelect={(id) => {
                      setSelected(id);
                      setView("brain");
                    }}
                    onRate={rate}
                    busy={busy}
                  />
                ))}
              </div>
              {!sorted.length && (
                <div className="empty-state">
                  <h3>
                    {data.listings.length
                      ? "Nothing on file matches your brief"
                      : "No listings on file yet"}
                  </h3>
                  <p>
                    {data.listings.length
                      ? "Adjust the brief, or send your agent to Bazaraki from the area map."
                      : "Send your agent to Bazaraki from the area map. It reads each advert and studies every photo."}
                  </p>
                  <button
                    className="primary"
                    onClick={() =>
                      data.listings.length
                        ? setDialog("settings")
                        : setView("map")
                    }
                  >
                    {data.listings.length ? "Edit brief" : "Search Bazaraki"}
                    <ArrowRight size={17} />
                  </button>
                </div>
              )}
              <p className="catalogue-note">
                Public listing snapshots · check availability and prices at the
                source. Added on:{" "}
                {data.listings[0]?.captured_at?.slice(0, 10) || "—"}.
              </p>
            </section>
          )}
          {view === "duel" && (
            <section className="duel-section">
              <span className="eyebrow">SIDE BY SIDE · FOR THE RECORD</span>
              <h2>Which apartment would you visit?</h2>
              <p>Pick one. Your agent takes note, even when both look good.</p>
              {a && b ? (
                <>
                  <div className="duel-grid">
                    <div>
                      <span className="duel-letter">A</span>
                      <ApartmentCard key={a.id} listing={a} />
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => compare(1)}
                      >
                        Choose A<Check size={17} />
                      </button>
                    </div>
                    <span className="versus">VS</span>
                    <div>
                      <span className="duel-letter">B</span>
                      <ApartmentCard key={b.id} listing={b} />
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => compare(-1)}
                      >
                        Choose B<Check size={17} />
                      </button>
                    </div>
                  </div>
                  <div className="duel-other">
                    <button disabled={busy} onClick={() => compare(0)}>
                      About the same
                    </button>
                    <button disabled={busy} onClick={nextPair}>
                      Another pair →
                    </button>
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <h3>Two listings needed</h3>
                  <p>
                    Your agent needs two listings with photos that match your
                    brief. {eligible.length === 1 ? "One is on file." : ""}{" "}
                    Search Bazaraki from the area map.
                  </p>
                  <button className="primary" onClick={() => setView("map")}>
                    Open the area map
                    <ArrowRight size={17} />
                  </button>
                </div>
              )}
            </section>
          )}
          <section className="training-strip">
            <div className="training-fly">
              <Fly size={22} />
            </div>
            <div>
              <span className="eyebrow">
                CLIENT FILE · {data.training.ready ? "ACTIVE" : "OPENING"}
              </span>
              <h3>
                {data.training.ready
                  ? "Your agent knows your taste"
                  : "A few ratings, and your agent takes it from here"}
              </h3>
              <p>
                {data.training.next} · {eligible.length} apartments with photos
                match your rules.
              </p>
            </div>
            <div className="training-progress">
              <div>
                <b>
                  <CountUp value={done} format={(v) => String(Math.round(v))} />
                </b>
                <small>ratings and comparisons</small>
              </div>
              <div className="progress-dots">
                {Array.from({ length: 10 }, (_, i) => (
                  <i
                    key={i}
                    className={i < Math.min(done, 10) ? "filled" : ""}
                  />
                ))}
              </div>
            </div>
            <button className="text-button" onClick={() => setView("learn")}>
              Brief your agent
              <ArrowRight size={17} />
            </button>
          </section>
          <footer>
            <span>
              Fly Estate{" "}
              <small>· a research project on a real connectome</small>
            </span>
            <span>Photos → sensory inputs → FlyWire → your shortlist</span>
            <a
              href="https://codex.flywire.ai/"
              target="_blank"
              rel="noreferrer"
            >
              Explore FlyWire
              <ArrowUpRight size={13} />
            </a>
          </footer>
        </main>
        {dialog === "settings" && (
          <SettingsDialog
            data={data}
            onSave={save}
            onClose={() => setDialog("")}
          />
        )}
        {dialog === "import" && (
          <ImportDialog onDone={load} onClose={() => setDialog("")} />
        )}
        {slow && !toast && (
          <div className="toast waiting" role="status">
            <LoaderCircle className="spin" size={17} />
            Your agent is updating its view. The buttons return when it is done.
          </div>
        )}
        {toast && (
          <div className="toast" role="status">
            <Check size={17} />
            {toast}
          </div>
        )}
      </div>
    </>
  );
}
