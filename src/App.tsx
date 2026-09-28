import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
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
  MapPin,
  LoaderCircle,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import type { Data, Settings } from "./types";
import { api, count, money } from "./api";
import Fly from "./Fly";
const BrainView = lazy(() => import("./BrainView"));
import CityMap from "./CityMap";
import ApartmentCard from "./ApartmentCard";
import { ImportDialog, SettingsDialog } from "./Dialogs";

const views = [
  ["brain", "Fly brain", Brain],
  ["map", "Interest map", Map],
  ["learn", "Learning", Heart],
  ["duel", "Apartment duel", GitCompareArrows],
] as const;
export default function App() {
  const [data, setData] = useState<Data>(),
    [view, setView] = useState("brain"),
    [selectedId, setSelected] = useState(""),
    [dialog, setDialog] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [showExcluded, setShowExcluded] = useState(false),
    [sort, setSort] = useState("fly"),
    [pair, setPair] = useState<[string, string]>(["", ""]),
    [toast, setToast] = useState("");
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
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(t);
  }, [toast]);
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
      value === null ? "Rating removed" : "Your fly remembered your choice",
    ).catch(() => {});
  };
  const save = async (s: Settings) => {
    await mutate("/api/settings", "PUT", s, "Rules saved");
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
        "Choice saved",
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
  if (!data)
    return (
      <main className="boot">
        <img src="/fly.svg" alt="Fly Estate" />
        <h1>Fly Estate</h1>
        <p>{error || "Waking up a tiny brain…"}</p>
        {error ? (
          <button
            onClick={() => {
              setError("");
              load().catch((e) => setError(e.message));
            }}
          >
            Try again
          </button>
        ) : (
          <LoaderCircle className="spin" />
        )}
      </main>
    );
  const selected = data.listings.find((l) => l.id === selectedId),
    done = data.training.ratings + data.training.comparisons;
  const a = eligible.find((l) => l.id === pair[0]),
    b = eligible.find((l) => l.id === pair[1]);
  const selectedForBrain =
    selected && !selected.filter_reasons.length ? selected : eligible[0];
  return (
    <div className="app">
      <header className="app-header">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            setView("brain");
          }}
        >
          <img src="/fly.svg" alt="" />
          <span>
            fly<span className="brand-light">estate</span>
            <small>A LITTLE BRAIN. A PLACE TO CALL HOME.</small>
          </span>
        </a>
        <div className="header-right">
          <span className="location-chip">
            <MapPin size={15} />
            Limassol, Cyprus
          </span>
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
            className="icon-button"
            title="My rules"
            aria-label="My rules"
            onClick={() => setDialog("settings")}
          >
            <SlidersHorizontal size={19} />
          </button>
          <button className="primary" onClick={() => setDialog("import")}>
            <Plus size={17} />
            Add apartment
          </button>
        </div>
      </header>
      <main>
        <section className="intro">
          <div>
            <span className="eyebrow intro-eyebrow">
              <span className="live-dot" />
              YOUR PERSONAL APARTMENT FLY
            </span>
            <h1>
              Tiny brain.
              <br />
              Big apartment decision<span>.</span>
            </h1>
            <p>
              Show it what you like. Watch your fly
              <br className="desktop-break" />
              find its way to your next apartment.
            </p>
          </div>
          <div className="intro-stats">
            <div>
              <strong>{count(data.brain.neurons)}</strong>
              <span>neurons in a real connectome</span>
            </div>
            <div>
              <strong>
                {(data.brain.connections / 1e6).toFixed(2)} <small>M</small>
              </strong>
              <span>connections behind a tiny decision</span>
            </div>
            <span className="data-tag">
              FLYWIRE · RELEASE 783 <ArrowUpRight size={12} />
            </span>
          </div>
        </section>
        <section className="control-strip">
          <nav aria-label="Project sections">
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
          <div className="mode-switch" aria-label="Vision mode">
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
            fallback={<div className="empty-state">Loading the 3D brain…</div>}
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
              onSelect={setSelected}
              onIdeal={(p) =>
                save({ ...data.settings, ideal: p }).catch(() => {})
              }
            />
            <aside className="map-sidebar">
              <div className="side-heading">
                <span className="eyebrow">FINDING YOUR NEXT APARTMENT</span>
                <h3>
                  {data.training.ready
                    ? "Where your fly wants to go"
                    : "Your fly explores Limassol"}
                </h3>
                <p>
                  The green area is your preferred location. Drag its center to
                  update your preference.
                </p>
              </div>
              {selected ? (
                <ApartmentCard listing={selected} onRate={rate} busy={busy} />
              ) : (
                <div className="empty-stimulus">
                  <Fly />
                  <p>Select an apartment marker on the map.</p>
                </div>
              )}
              <div className="map-selection-list">
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
                <span className="eyebrow">YOUR TASTE → ITS PREFERENCES</span>
                <h2>
                  {data.training.ready
                    ? "Apartments your fly likes"
                    : "Show your fly what you like"}
                </h2>
                <p>
                  “Would visit”, “Maybe”, “Not for me” — every rating refines
                  the model.
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
                  <option value="fly">Fly interest</option>
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
                <Fly />
                <h3>
                  {data.listings.length
                    ? "No apartments match your rules"
                    : "Start with real apartments"}
                </h3>
                <p>
                  {data.listings.length
                    ? "Adjust your filters or add suitable listings."
                    : "Add listings with photos so your fly can learn your taste."}
                </p>
                <button
                  className="primary"
                  onClick={() =>
                    setDialog(data.listings.length ? "settings" : "import")
                  }
                >
                  {data.listings.length ? "Edit rules" : "Add apartments"}
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
            <span className="eyebrow">A OR B? YOUR FLY WILL REMEMBER.</span>
            <h2>Which apartment would you visit?</h2>
            <p>
              Compare two apartments. Your choices help it learn even when both
              look good.
            </p>
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
                <Fly />
                <h3>Two apartments needed</h3>
                <p>
                  Add at least two listings with photos that match your filters.
                </p>
                <button className="primary" onClick={() => setDialog("import")}>
                  Add apartments
                </button>
              </div>
            )}
          </section>
        )}
        <section className="training-strip">
          <div className="training-fly">
            <Fly />
          </div>
          <div>
            <span className="eyebrow">
              YOUR FLY{" "}
              {data.training.ready
                ? "IS LEARNING YOUR TASTE"
                : "IS GETTING TO KNOW YOU"}
            </span>
            <h3>
              {data.training.ready
                ? "Tiny decisions get better"
                : "A little of your taste brings it to life"}
            </h3>
            <p>
              {data.training.next} · {eligible.length} apartments with photos
              match your rules.
            </p>
          </div>
          <div className="training-progress">
            <div>
              <b>{done}</b>
              <small>ratings and comparisons</small>
            </div>
            <div className="progress-dots">
              {Array.from({ length: 10 }, (_, i) => (
                <i key={i} className={i < Math.min(done, 10) ? "filled" : ""} />
              ))}
            </div>
          </div>
          <button className="text-button" onClick={() => setView("learn")}>
            Teach your fly
            <ArrowRight size={17} />
          </button>
        </section>
        <footer>
          <span>
            flyestate <small>· an experiment with a real connectome</small>
          </span>
          <span>Photos → sensory inputs → FlyWire → your choice</span>
          <a href="https://codex.flywire.ai/" target="_blank" rel="noreferrer">
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
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}
