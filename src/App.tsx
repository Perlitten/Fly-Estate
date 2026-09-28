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
  ["brain", "Мозг мухи", Brain],
  ["map", "Карта интересов", Map],
  ["learn", "Обучение", Heart],
  ["duel", "Дуэль квартир", GitCompareArrows],
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
      value === null ? "Оценка убрана" : "Муха запомнила твой выбор",
    ).catch(() => {});
  };
  const save = async (s: Settings) => {
    await mutate("/api/settings", "PUT", s, "Правила сохранены");
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
        "Выбор сохранён",
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
        <p>{error || "Пробуждаю маленький мозг…"}</p>
        {error ? (
          <button
            onClick={() => {
              setError("");
              load().catch((e) => setError(e.message));
            }}
          >
            Попробовать ещё раз
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
            Лимассол, Кипр
          </span>
          <a
            className="github-link"
            href="https://github.com/Perlitten/Fly-Estate"
            target="_blank"
            rel="noreferrer"
          >
            Проект
            <ArrowUpRight size={15} />
          </a>
          <button
            className="icon-button"
            title="Мои правила"
            aria-label="Мои правила"
            onClick={() => setDialog("settings")}
          >
            <SlidersHorizontal size={19} />
          </button>
          <button className="primary" onClick={() => setDialog("import")}>
            <Plus size={17} />
            Добавить квартиру
          </button>
        </div>
      </header>
      <main>
        <section className="intro">
          <div>
            <span className="eyebrow intro-eyebrow">
              <span className="live-dot" />
              ПЕРСОНАЛЬНАЯ КВАРТИРНАЯ МУХА
            </span>
            <h1>
              Маленький мозг.
              <br />
              Большой квартирный вопрос<span>.</span>
            </h1>
            <p>
              Покажи, что тебе нравится. Наблюдай, как муха
              <br className="desktop-break" />
              находит свой путь к твоей следующей квартире.
            </p>
          </div>
          <div className="intro-stats">
            <div>
              <strong>{count(data.brain.neurons)}</strong>
              <span>нейронов в настоящем коннектоме</span>
            </div>
            <div>
              <strong>
                {(data.brain.connections / 1e6).toFixed(2).replace(".", ",")}{" "}
                <small>млн</small>
              </strong>
              <span>связей для маленького решения</span>
            </div>
            <span className="data-tag">
              FLYWIRE · RELEASE 783 <ArrowUpRight size={12} />
            </span>
          </div>
        </section>
        <section className="control-strip">
          <nav aria-label="Разделы проекта">
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
          <div className="mode-switch" aria-label="Режим зрения">
            <button
              disabled={busy}
              className={data.settings.mode === "pure" ? "active" : ""}
              title="Фото как сетка света и цвета; искусственное отображение на входы мозга"
              onClick={() =>
                save({ ...data.settings, mode: "pure" }).catch(() => {})
              }
            >
              Pure Fly
            </button>
            <button
              disabled={busy}
              className={data.settings.mode === "cyborg" ? "active" : ""}
              title="CLIP превращает фото в визуальные сигналы для мозга"
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
            fallback={<div className="empty-state">Загружаю 3D-мозг…</div>}
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
                <span className="eyebrow">МАРШРУТ К ТВОЕЙ КВАРТИРЕ</span>
                <h3>
                  {data.training.ready
                    ? "Куда тянется муха"
                    : "Муха изучает Лимассол"}
                </h3>
                <p>
                  Зелёная зона — желаемое место. Перетащи её центр, чтобы
                  изменить предпочтение.
                </p>
              </div>
              {selected ? (
                <ApartmentCard listing={selected} onRate={rate} busy={busy} />
              ) : (
                <div className="empty-stimulus">
                  <Fly />
                  <p>Выбери маркер квартиры на карте.</p>
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
                        {l.bedrooms} сп. · ≈ {l.prediction.distance ?? "—"} км
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
                <span className="eyebrow">ТВОЙ ВКУС → ЕЁ ПРЕДПОЧТЕНИЯ</span>
                <h2>
                  {data.training.ready
                    ? "Квартиры по вкусу твоей мухи"
                    : "Покажи мухе свой вкус"}
                </h2>
                <p>
                  «Посмотрел бы», «Может быть», «Не моё» — каждая оценка
                  уточняет модель.
                </p>
              </div>
              <div className="list-controls">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={showExcluded}
                    onChange={(e) => setShowExcluded(e.target.checked)}
                  />
                  Показать исключённые
                </label>
                <select
                  aria-label="Сортировка квартир"
                  value={sort}
                  onChange={(e) => setSort(e.target.value)}
                >
                  <option value="fly">По интересу мухи</option>
                  <option value="price">По цене</option>
                  <option value="distance">По расстоянию</option>
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
                    ? "Ни одна квартира не прошла правила"
                    : "Начнём с настоящих квартир"}
                </h3>
                <p>
                  {data.listings.length
                    ? "Измени фильтры или добавь подходящие объявления."
                    : "Добавь объявления с фото, чтобы муха смогла познакомиться с твоим вкусом."}
                </p>
                <button
                  className="primary"
                  onClick={() =>
                    setDialog(data.listings.length ? "settings" : "import")
                  }
                >
                  {data.listings.length
                    ? "Изменить правила"
                    : "Добавить квартиры"}
                  <ArrowRight size={17} />
                </button>
              </div>
            )}
            <p className="catalogue-note">
              Публичные снимки объявлений · доступность и цену уточняй по ссылке
              на источник. Дата добавления:{" "}
              {data.listings[0]?.captured_at?.slice(0, 10) || "—"}.
            </p>
          </section>
        )}
        {view === "duel" && (
          <section className="duel-section">
            <span className="eyebrow">А ИЛИ Б? МУХА ЗАПОМНИТ.</span>
            <h2>Куда бы ты пошёл на просмотр?</h2>
            <p>
              Сравни две квартиры. Это помогает учиться даже там, где обе
              хороши.
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
                      Выбираю A<Check size={17} />
                    </button>
                  </div>
                  <span className="versus">VS</span>
                  <div>
                    <span className="duel-letter">Б</span>
                    <ApartmentCard key={b.id} listing={b} />
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => compare(-1)}
                    >
                      Выбираю Б<Check size={17} />
                    </button>
                  </div>
                </div>
                <div className="duel-other">
                  <button disabled={busy} onClick={() => compare(0)}>
                    Примерно одинаково
                  </button>
                  <button disabled={busy} onClick={nextPair}>
                    Другая пара →
                  </button>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <Fly />
                <h3>Нужны две квартиры</h3>
                <p>
                  Добавь минимум два объявления с фото, которые проходят твои
                  фильтры.
                </p>
                <button className="primary" onClick={() => setDialog("import")}>
                  Добавить квартиры
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
              ТВОЯ МУХА{" "}
              {data.training.ready
                ? "УЖЕ ЛОВИТ ТВОЙ ВКУС"
                : "ПОКА ЗНАКОМИТСЯ С ТОБОЙ"}
            </span>
            <h3>
              {data.training.ready
                ? "Маленькие решения становятся точнее"
                : "Немного твоего вкуса — и она оживёт"}
            </h3>
            <p>
              {data.training.next} · {eligible.length} квартир с фото проходят
              правила.
            </p>
          </div>
          <div className="training-progress">
            <div>
              <b>{done}</b>
              <small>оценок и сравнений</small>
            </div>
            <div className="progress-dots">
              {Array.from({ length: 10 }, (_, i) => (
                <i key={i} className={i < Math.min(done, 10) ? "filled" : ""} />
              ))}
            </div>
          </div>
          <button className="text-button" onClick={() => setView("learn")}>
            Обучить муху
            <ArrowRight size={17} />
          </button>
        </section>
        <footer>
          <span>
            flyestate <small>· эксперимент с настоящим коннектомом</small>
          </span>
          <span>Фото → сенсорные входы → FlyWire → твой выбор</span>
          <a href="https://codex.flywire.ai/" target="_blank" rel="noreferrer">
            Исследовать FlyWire
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
